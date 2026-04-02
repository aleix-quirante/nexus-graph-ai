import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Callable

from dotenv import load_dotenv
import asyncio
from fastapi import FastAPI, Depends, Request, Response, HTTPException
import redis.asyncio as aioredis
from neo4j import AsyncGraphDatabase, AsyncDriver

from core.observability import setup_telemetry
from core.config import settings

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
    db.driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
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
    try:
        redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

        async def check_redis():
            await redis_client.setex("health_check", 5, "ok")

        async def check_neo4j():
            if db.driver is None:
                raise Exception("Neo4j driver not initialized")
            async with db.driver.session() as session:
                result = await session.run("RETURN 1")
                await result.single()

        await asyncio.wait_for(
            asyncio.gather(check_redis(), check_neo4j()), timeout=1.0
        )
        return {"status": "ok", "system": "Nexus Graph AI Core"}
    except Exception as e:
        logger.error(f"Health check failed: {e}")
        raise HTTPException(status_code=503, detail="Service Unavailable")
    finally:
        await redis_client.aclose()
