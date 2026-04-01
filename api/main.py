import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Callable

from dotenv import load_dotenv
from fastapi import FastAPI, Depends, Request, Response
from neo4j import AsyncGraphDatabase, AsyncDriver
from pydantic_settings import BaseSettings, SettingsConfigDict

from core.observability import setup_telemetry

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Telemetry early
setup_telemetry("nexus-api")

load_dotenv(override=True)


class Settings(BaseSettings):
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str

    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )


settings = Settings()


class Database:
    driver: AsyncDriver | None = None


db = Database()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    db.driver = AsyncGraphDatabase.driver(
        settings.neo4j_uri, auth=(settings.neo4j_user, settings.neo4j_password)
    )

    # Simple check on startup
    try:
        await db.driver.verify_connectivity()
        from api.mcp import set_mcp_db_driver

        set_mcp_db_driver(db.driver)
        logger.info("✅ [NEXUS CORE] Conexión a Neo4j establecida con éxito.")
    except Exception as e:
        logger.error(f"❌ [NEXUS CORE] Failed to connect to Neo4j on startup: {e}")

    yield

    if db.driver:
        await db.driver.close()


app = FastAPI(lifespan=lifespan, title="Nexus Graph AI Enterprise")


@app.middleware("http")
async def add_correlation_id(request: Request, call_next: Callable) -> Response:
    correlation_id = request.headers.get("X-Correlation-ID", str(uuid.uuid4()))
    request.state.correlation_id = correlation_id
    response = await call_next(request)
    response.headers["X-Correlation-ID"] = correlation_id
    return response


@app.middleware("http")
async def track_llm_latency(request: Request, call_next: Callable) -> Response:
    start_time = time.perf_counter()
    response = await call_next(request)
    process_time = time.perf_counter() - start_time
    # Simplified LLM latency/TTFT tracking logic for demonstration
    # In a real scenario, this would intercept specific LLM calls or rely on
    # specific headers/state set during the request handling.
    response.headers["X-Process-Time"] = str(process_time)
    logger.info(
        f"Request {request.url.path} processed in {process_time:.4f}s. "
        f"Correlation ID: {getattr(request.state, 'correlation_id', 'unknown')}"
    )
    return response


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
