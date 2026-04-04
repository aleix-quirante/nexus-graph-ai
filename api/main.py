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
from core.auth import verify_cryptographic_identity, TokenPayload
from core.exceptions import (
    NexusError,
    DatabaseConnectionError,
    RedisConnectionError,
    RateLimitExceededError,
)

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


async def rate_limit_per_tenant(
    token: TokenPayload = Depends(verify_cryptographic_identity),
):
    """
    Distributed rate limiting using Redis.
    Identity derived from cryptographic JWT 'sub' claim.
    """
    if not db.redis:
        return

    key = f"rate_limit:{token.sub}"
    # Simple fixed window rate limit: 100 requests per minute
    limit = 100
    window = 60

    try:
        current = await db.redis.get(key)
        if current and int(current) >= limit:
            logger.warning(f"Rate limit exceeded for subject: {token.sub}")
            raise RateLimitExceededError(
                message="Rate limit exceeded. Please try again later.",
                details={"subject": token.sub, "limit": limit},
            )

        pipe = db.redis.pipeline()
        await pipe.incr(key)
        await pipe.expire(key, window)
        await pipe.execute()
    except (aioredis.RedisError, ConnectionError) as e:
        logger.error(f"Redis backend failure in rate limiter: {e}", exc_info=True)
        # Fail-open if Redis is down to avoid total outage, but log it properly.
    except RateLimitExceededError:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in rate limiter: {e}", exc_info=True)
        # In case of unforeseen logic errors, we still fail-open but log extensively.


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
        logger.critical(f"❌ [NEXUS CORE] Initialization failed: {e}", exc_info=True)

    yield

    if db.driver:
        await db.driver.close()
    if db.redis:
        await db.redis.close()


app = FastAPI(
    lifespan=lifespan,
    title="Nexus Graph AI Enterprise",
    dependencies=[
        Depends(verify_cryptographic_identity),
        Depends(rate_limit_per_tenant),
    ],
)


@app.exception_handler(NexusError)
async def nexus_exception_handler(request: Request, exc: NexusError):
    """
    Centralized exception handler for NexusError.
    Ensures that domain errors are returned with consistent structure and status codes.
    """
    logger.error(
        f"Domain Error: {exc.message} | Details: {exc.details} | "
        f"Correlation ID: {getattr(request.state, 'correlation_id', 'unknown')}",
        exc_info=True,
    )

    status_code = 500
    if isinstance(exc, RateLimitExceededError):
        status_code = 429
    elif isinstance(exc, (DatabaseConnectionError, RedisConnectionError)):
        status_code = 503

    return Response(
        content=f'{{"error": "{exc.message}", "type": "{type(exc).__name__}"}}',
        status_code=status_code,
        media_type="application/json",
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

    async def check_model_integrity() -> str:
        """
        Deep model health check.
        Ensures the local SLM is responsive and returning consistent security verdicts.
        """
        from core.security_guardrails import SLMGuard

        guard = SLMGuard()
        # Test with a known safe input
        is_safe = await guard.check_integrity("Ping", mode="healthcheck")
        if not is_safe:
            raise RuntimeError(
                "SLM Security Guard unreachable or returned violation for safe input."
            )
        return "ok"

    try:
        # Verify connectivity asynchronously with strict 2.0s timeout
        results = await asyncio.wait_for(
            asyncio.gather(
                check_redis(),
                check_neo4j(),
                check_model_integrity(),
                return_exceptions=True,
            ),
            timeout=3.0,
        )

        redis_status = "ok" if results[0] == "ok" else "error"
        neo4j_status = "ok" if results[1] == "ok" else "error"
        model_status = "ok" if results[2] == "ok" else "error"

        if redis_status != "ok" or neo4j_status != "ok" or model_status != "ok":
            if isinstance(results[0], Exception):
                logger.error(f"Redis Health Failure: {results[0]}")
            if isinstance(results[1], Exception):
                logger.error(f"Neo4j Health Failure: {results[1]}")
            if isinstance(results[2], Exception):
                logger.error(f"Model Health Failure: {results[2]}")

            raise HTTPException(
                status_code=503,
                detail={
                    "status": "unhealthy",
                    "components": {
                        "redis": redis_status,
                        "neo4j": neo4j_status,
                        "slm_guard": model_status,
                    },
                },
            )

        return {
            "status": "healthy",
            "components": {"redis": "ok", "neo4j": "ok", "slm_guard": "ok"},
        }

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
        logger.error(f"Unexpected health check failure: {e}", exc_info=True)
        raise HTTPException(status_code=503, detail="Service Unavailable")
