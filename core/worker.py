import json
import logging
from typing import Optional, Dict, Any
from pydantic import ValidationError
from pydantic_ai import Agent

from openinference.instrumentation.openai import OpenAIInstrumentor
from openinference.instrumentation.dspy import DSPyInstrumentor
from core.observability import setup_telemetry

# Initialize Telemetry early
setup_telemetry("nexus-worker")
OpenAIInstrumentor().instrument()

from core.schemas import GraphExtraction
from confluent_kafka import Consumer, KafkaError
from core.database import Neo4jRepository
from core.config import settings

logger = logging.getLogger(__name__)

# Initialize the real Neo4j Repository
neo4j_repo = Neo4jRepository(
    uri=settings.NEO4J_URI,
    user=settings.NEO4J_USER,
    password=settings.NEO4J_PASSWORD,
)

# Initialize the Pydantic AI agent with the desired model
agent = Agent(
    model="openai:gpt-4o",
    result_type=GraphExtraction,
    system_prompt="Extract entities and relationships from the provided document chunk.",
)


async def insert_to_neo4j(graph_data: GraphExtraction) -> None:
    """
    Asynchronously persists graph data to Neo4j using the Enterprise repository.
    Handles fencing tokens to ensure transaction integrity.
    """
    import time

    # Use a high-resolution timestamp as a fencing token for idempotency
    fencing_token = int(time.time() * 1000)
    try:
        await neo4j_repo.add_graph_data(graph_data, fencing_token)
        logger.info(
            f"Successfully persisted {len(graph_data.nodes)} nodes and {len(graph_data.relationships)} rels."
        )
    except Exception as e:
        logger.error(f"Failed to insert graph data: {e}")
        raise


async def process_message_with_recovery(
    content: str, max_retries: int = 3
) -> Optional[GraphExtraction]:
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
            logger.error(f"Unexpected error: {e}")
            raise e

    return None


async def consume_document_chunks() -> None:
    """
    Consumer loop that listens to the Redpanda 'document_chunks' topic using confluent-kafka.
    Optimized for durability with manual offset commits and backpressure management.
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
                graph_data = await process_message_with_recovery(content)
                if graph_data:
                    await insert_to_neo4j(graph_data)

                # Commit offset after successful processing
                consumer.commit(asynchronous=False)
            except Exception as e:
                logger.error(f"Failed to process message: {e}")
                # For enterprise grade, we could send to a Dead Letter Queue (DLQ) here
    finally:
        consumer.close()
        await neo4j_repo.close()
