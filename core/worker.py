import json
import logging
from typing import Optional, Dict, Any
from pydantic import ValidationError
from pydantic_ai import Agent

from openinference.instrumentation.openai import OpenAIInstrumentor
from openinference.instrumentation.dspy import DSPyInstrumentor
from core.observability import setup_observability

setup_observability()
OpenAIInstrumentor().instrument()

from core.schemas import GraphExtraction

logger = logging.getLogger(__name__)

# Initialize the Pydantic AI agent with the desired model
# Since we want it to extract GraphExtraction using tool calling naturally,
# we use the result_type parameter.
agent = Agent(
    model="openai:gpt-4o",  # or any capable model, dummy for now
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
            # We rely on Pydantic AI's native structured output capabilities
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
    Consumer loop that listens to the Redpanda 'document_chunks' topic.
    This is a simplified mock implementation.
    """
    # Mocking Redpanda consumer setup
    logger.info("Starting Redpanda consumer for topic 'document_chunks'...")

    # In a real scenario, this would be an actual consumer loop:
    # consumer = KafkaConsumer('document_chunks', bootstrap_servers='localhost:9092')
    # for message in consumer:
    #     content = message.value.decode('utf-8')
    #     try:
    #         graph_data = await process_message_with_recovery(content)
    #         if graph_data:
    #             insert_to_neo4j(graph_data)
    #     except Exception as e:
    #         logger.error(f"Failed to process message: {e}")
    pass
