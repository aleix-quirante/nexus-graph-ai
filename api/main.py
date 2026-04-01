import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator
import os
from dotenv import load_dotenv

from fastapi import FastAPI, Depends
from neo4j import AsyncGraphDatabase, AsyncDriver

from core.observability import setup_telemetry

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Telemetry early
setup_telemetry("nexus-api")

load_dotenv(override=True)


class Database:
    driver: AsyncDriver | None = None


db = Database()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")

    db.driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    # Simple check on startup
    try:
        await db.driver.verify_connectivity()
        from api.mcp import set_mcp_db_driver

        set_mcp_db_driver(db.driver)
        print("✅ [NEXUS CORE] Conexión a Neo4j establecida con éxito.")
    except Exception as e:
        print(f"❌ [NEXUS CORE] Failed to connect to Neo4j on startup: {e}")

    yield

    if db.driver:
        await db.driver.close()


app = FastAPI(lifespan=lifespan, title="Nexus Graph AI Enterprise")

from api.mcp import mcp_router

app.include_router(mcp_router, prefix="/mcp")

try:
    from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor

    FastAPIInstrumentor.instrument_app(app)
    logger.info("FastAPI successfully instrumented with OpenTelemetry")
except ImportError as e:
    logger.warning(
        f"Failed to import FastAPIInstrumentor: {e}. Running without FastAPI instrumentation."
    )
except Exception as e:
    logger.warning(
        f"Failed to instrument FastAPI: {e}. Running without FastAPI instrumentation."
    )


async def get_db_driver() -> AsyncGenerator[AsyncDriver, None]:
    if db.driver is None:
        raise RuntimeError("Database driver not initialized")
    yield db.driver


@app.get("/health", tags=["System"])
async def health_check() -> dict[str, str]:
    return {"status": "ok", "system": "Nexus Graph AI Core"}
