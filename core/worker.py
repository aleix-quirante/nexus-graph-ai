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

logger = logging.getLogger(__name__)

# Initialize the Pydantic AI agent with the desired model
agent = Agent(
    model="openai:gpt-4o",
    result_type=GraphExtraction,
    system_prompt="Extract entities and relationships from the provided document chunk.",
)


def insert_to_neo4j(graph_data: GraphExtraction) -> None:
    """
    Dummy function to simulate persistence to Neo4j.
    """
    logger.info(
        f"Successfully inserted {len(graph_data.nodes)} nodes and {len(graph_data.relationships)} relationships to Neo4j."
    )


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
    """
    logger.info("Starting confluent-kafka consumer for topic 'document_chunks'...")
    conf = {
        "bootstrap.servers": "localhost:9092",
        "group.id": "graph_extraction_group",
        "auto.offset.reset": "earliest",
    }
    consumer = Consumer(conf)
    consumer.subscribe(["document_chunks"])

    try:
        while True:
            msg = consumer.poll(timeout=1.0)
            if msg is None:
                continue
            if msg.error():
                if msg.error().code() == KafkaError._PARTITION_EOF:
                    continue
                else:
                    logger.error(f"Consumer error: {msg.error()}")
                    break

            content = msg.value().decode("utf-8")
            try:
                graph_data = await process_message_with_recovery(content)
                if graph_data:
                    insert_to_neo4j(graph_data)
            except Exception as e:
                logger.error(f"Failed to process message: {e}")
    finally:
        consumer.close()
