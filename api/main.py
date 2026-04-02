import logging
import os
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncGenerator, Callable, Any, Optional

from dotenv import load_dotenv
import asyncio
from fastapi import FastAPI, Depends, Request, Response, HTTPException, status
import redis.asyncio as aioredis
from neo4j import AsyncGraphDatabase, AsyncDriver

from prometheus_client import generate_latest, CONTENT_TYPE_LATEST
from core.observability import setup_telemetry, ACTIVE_AI_TASKS
from core.config import settings

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Initialize Telemetry early
setup_telemetry("nexus-api")

load_dotenv(override=True)


class Database:
    driver: AsyncDriver | None = None
    redis: aioredis.Redis | None = None


db = Database()


class ZeroTrustSecurity:
    """
    Implements a strict security perimeter for the API.
    Expects mTLS and Tenant identification to be handled by the API Gateway (Kong/Tyk).
    """

    @staticmethod
    async def verify_mtls(request: Request):
        # API Gateway (Kong) set this header after successful mTLS termination
        client_verify = request.headers.get("X-SSL-Client-Verify")
        if client_verify != "SUCCESS":
            logger.warning("mTLS verification failed or header missing.")
            raise HTTPException(
                status_code=status.HTTP_403_FOR_REQUEST_FORBIDDEN,
                detail="mTLS termination required at Gateway level.",
            )

    @staticmethod
    async def get_tenant_id(request: Request) -> str:
        tenant_id = request.headers.get("X-Tenant-ID")
        if not tenant_id:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Tenant identification missing.",
            )
        return tenant_id


async def rate_limit_per_tenant(
    request: Request, tenant_id: str = Depends(ZeroTrustSecurity.get_tenant_id)
):
    """
    Distributed rate limiting using Redis.
    Limits requests and token consumption (simulated).
    """
    if not db.redis:
        return

    key = f"rate_limit:{tenant_id}"
    # Simple fixed window rate limit: 100 requests per minute
    limit = 100
    window = 60

    try:
        current = await db.redis.get(key)
        if current and int(current) >= limit:
            logger.warning(f"Rate limit exceeded for tenant: {tenant_id}")
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail="Rate limit exceeded. Please try again later.",
            )

        pipe = db.redis.pipeline()
        await pipe.incr(key)
        await pipe.expire(key, window)
        await pipe.execute()
    except Exception as e:
        if isinstance(e, HTTPException):
            raise e
        logger.error(f"Rate limiter error: {e}")
        # Fail-open if Redis is down to avoid total outage, but log it.


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    db.driver = AsyncGraphDatabase.driver(
        settings.NEO4J_URI, auth=(settings.NEO4J_USER, settings.NEO4J_PASSWORD)
    )
    db.redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)

    # Simple check on startup
    try:
        await db.driver.verify_connectivity()
        await db.redis.ping()
        from api.mcp import set_mcp_db_driver

        set_mcp_db_driver(db.driver)
        logger.info("✅ [NEXUS CORE] Connections to Neo4j and Redis established.")
    except Exception as e:
        logger.error(f"❌ [NEXUS CORE] Initialization failed: {e}")

    yield

    if db.driver:
        await db.driver.close()
    if db.redis:
        await db.redis.close()


app = FastAPI(
    lifespan=lifespan,
    title="Nexus Graph AI Enterprise",
    dependencies=[
        Depends(ZeroTrustSecurity.verify_mtls),
        Depends(rate_limit_per_tenant),
    ],
)


@app.middleware("http")
async def track_active_ai_tasks(request: Request, call_next: Callable) -> Response:
    """
    KEDA scaling middleware: increments active_ai_tasks gauge at start,
    decrements on completion (success or fail).
    """
    is_ai_path = request.url.path.startswith("/mcp") or request.url.path.startswith(
        "/ask"
    )

    if is_ai_path:
        ACTIVE_AI_TASKS.inc()
        try:
            return await call_next(request)
        finally:
            ACTIVE_AI_TASKS.dec()
    return await call_next(request)


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


@app.get("/metrics", tags=["System"])
async def metrics() -> Response:
    """
    Expose metrics for Prometheus/KEDA scraping.
    """
    return Response(content=generate_latest(), media_type=CONTENT_TYPE_LATEST)


@app.get("/health", tags=["System"])
async def health_check() -> dict[str, Any]:
    """
    Asynchronous deep health check verifying connectivity to Redis and Neo4j.
    Enforces a strict 2.0s timeout to prevent resource exhaustion.
    """

    async def check_redis() -> str:
        if db.redis is None:
            raise RuntimeError("Redis client not initialized")
        await db.redis.ping()
        return "ok"

    async def check_neo4j() -> str:
        if db.driver is None:
            raise RuntimeError("Neo4j driver not initialized")
        async with db.driver.session() as session:
            result = await session.run("RETURN 1")
            await result.single()
        return "ok"

    try:
        # Verify connectivity asynchronously with strict 2.0s timeout
        results = await asyncio.wait_for(
            asyncio.gather(check_redis(), check_neo4j(), return_exceptions=True),
            timeout=2.0,
        )

        redis_status = "ok" if results[0] == "ok" else "error"
        neo4j_status = "ok" if results[1] == "ok" else "error"

        if redis_status != "ok" or neo4j_status != "ok":
            if isinstance(results[0], Exception):
                logger.error(f"Redis Health Failure: {results[0]}")
            if isinstance(results[1], Exception):
                logger.error(f"Neo4j Health Failure: {results[1]}")

            raise HTTPException(
                status_code=503,
                detail={
                    "status": "unhealthy",
                    "components": {"redis": redis_status, "neo4j": neo4j_status},
                },
            )

        return {"status": "healthy", "components": {"redis": "ok", "neo4j": "ok"}}

    except asyncio.TimeoutError:
        logger.error("Health check timed out after 2.0 seconds")
        raise HTTPException(
            status_code=503,
            detail={
                "status": "unhealthy",
                "reason": "Health check timeout",
                "components": {"redis": "timeout", "neo4j": "timeout"},
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected health check failure: {e}")
        raise HTTPException(status_code=503, detail="Service Unavailable")
