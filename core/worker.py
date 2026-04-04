import hashlib
import json
import logging

import redis.asyncio as redis
from openinference.instrumentation.openai import OpenAIInstrumentor
from pydantic import ValidationError
from pydantic_ai import Agent

from core.observability import setup_telemetry

# Initialize Telemetry early
setup_telemetry("nexus-worker")
OpenAIInstrumentor().instrument()

from confluent_kafka import Consumer, KafkaError

from core.concurrency import OntologyLockManager
from core.config import settings
from core.database import Neo4jRepository
from core.exceptions import AIError, DatabaseTransactionError
from core.schemas import GraphExtraction

logger = logging.getLogger(__name__)

# Initialize the real Neo4j Repository
neo4j_repo = Neo4jRepository(
    uri=settings.NEO4J_URI,
    user=settings.NEO4J_USER,
    password=settings.NEO4J_PASSWORD,
)

# Initialize Lock Manager for global fencing tokens
lock_manager = OntologyLockManager(redis_url=settings.REDIS_URL)

# Initialize Redis client for idempotency tracking
redis_client: redis.Redis | None = None

# Initialize the Pydantic AI agent with the desired model
agent = Agent(
    model="openai:gpt-4o",
    result_type=GraphExtraction,
    system_prompt="Extract entities and relationships from the provided document chunk.",
)


def compute_content_hash(content: str) -> str:
    """
    Compute SHA-256 hash of content for idempotency tracking.
    Ensures deterministic duplicate detection across distributed workers.
    """
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


async def get_redis_client() -> redis.Redis:
    """
    Lazy initialization of Redis client for idempotency.
    Reuses connection across worker lifecycle.
    """
    global redis_client
    if redis_client is None:
        redis_client = redis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return redis_client


async def is_content_processed(content_hash: str) -> bool:
    """
    Check if content has already been processed using Redis.
    Returns True if duplicate, False if new content.
    """
    client = await get_redis_client()
    try:
        exists = await client.exists(f"processed:{content_hash}")
        return bool(exists)
    except Exception as e:
        logger.error(f"Redis idempotency check failed: {e}", exc_info=True)
        # Fail-open: If Redis is down, allow processing to continue
        return False


async def mark_content_processed(content_hash: str, ttl: int = 86400) -> None:
    """
    Mark content as processed in Redis with TTL (default 24 hours).
    Prevents duplicate processing across distributed workers.
    """
    client = await get_redis_client()
    try:
        await client.setex(f"processed:{content_hash}", ttl, "1")
        logger.info(f"Content marked as processed: {content_hash[:16]}...")
    except Exception as e:
        logger.error(f"Failed to mark content as processed: {e}", exc_info=True)
        # Non-critical: Continue even if Redis write fails


async def insert_to_neo4j(graph_data: GraphExtraction) -> None:
    """
    Asynchronously persists graph data to Neo4j using the Enterprise repository.
    Handles fencing tokens to ensure transaction integrity.
    """
    # Use global lock manager to get a monotonic fencing token across the cluster
    async with lock_manager.acquire_node_lock("global_ingest") as fencing_token:
        try:
            await neo4j_repo.add_graph_data(graph_data, fencing_token)
            logger.info(
                f"Successfully persisted {len(graph_data.nodes)} nodes and {len(graph_data.relationships)} rels with token {fencing_token}."
            )
        except Exception as e:
            logger.error(f"Failed to insert graph data: {e}", exc_info=True)
            raise DatabaseTransactionError(f"Worker failed to persist graph: {e}")


async def process_message_with_recovery(
    content: str, max_retries: int = 3
) -> GraphExtraction | None:
    """
    Process a message using Pydantic AI with an auto-recovery loop for format hallucinations.
    """
    prompt = content
    for attempt in range(max_retries):
        try:
            result = await agent.run(prompt)
            return result.data
        except ValidationError as e:
            logger.warning(f"Validation error on attempt {attempt + 1}: {e}")
            if attempt == max_retries - 1:
                logger.error("Max retries reached. Failing.")
                raise e

            # Inject error context as direct feedback for the next attempt
            error_details = e.json()
            prompt = (
                f"Previous extraction failed schema validation with the following errors:\n"
                f"{error_details}\n\n"
                f"Please correct the errors and try again. Original content:\n{content}"
            )
        except Exception as e:
            logger.error(f"Unexpected error in AI processing: {e}", exc_info=True)
            raise AIError(f"AI agent failed: {e}")

    return None


async def consume_document_chunks() -> None:
    """
    Consumer loop that listens to the Redpanda 'document_chunks' topic using confluent-kafka.
    Optimized for durability with manual offset commits, backpressure management, and idempotency.
    """
    logger.info("Starting confluent-kafka consumer for topic 'document_chunks'...")
    conf = {
        "bootstrap.servers": "localhost:9092",
        "group.id": "graph_extraction_group",
        "auto.offset.reset": "earliest",
        "enable.auto.commit": False,  # Manual commit for durability
        "session.timeout.ms": 6000,
    }
    consumer = Consumer(conf)
    consumer.subscribe(["document_chunks"])

    try:
        while True:
            # Backpressure management: short poll interval allows for processing time
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                else:
                    logger.error(f"Consumer error: {msg.error()}")
                    break

            content_dict = json.loads(msg.value().decode("utf-8"))
            content = content_dict.get("content", "")

            try:
                # Idempotency check: Compute content hash
                content_hash = compute_content_hash(content)

                # Check if already processed
                if await is_content_processed(content_hash):
                    logger.info(
                        f"Duplicate content detected (hash: {content_hash[:16]}...), skipping processing"
                    )
                    # Commit offset even for duplicates to avoid reprocessing
                    consumer.commit(asynchronous=False)
                    continue

                # Process new content
                graph_data = await process_message_with_recovery(content)
                if graph_data:
                    await insert_to_neo4j(graph_data)

                    # Mark as processed after successful insertion
                    await mark_content_processed(content_hash)

                # Commit offset after successful processing
                consumer.commit(asynchronous=False)
            except Exception as e:
                logger.error(f"Failed to process message: {e}", exc_info=True)
                # For enterprise grade, we could send to a Dead Letter Queue (DLQ) here
    finally:
        consumer.close()
        await neo4j_repo.close()
        # Close Redis connection
        if redis_client:
            await redis_client.close()
