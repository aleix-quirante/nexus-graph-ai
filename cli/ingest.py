import json
import logging
from collections.abc import Generator
from typing import Any

from confluent_kafka import Producer

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DocumentProducer:
    def __init__(self, broker: str = "localhost:9092"):
        self.producer = Producer({"bootstrap.servers": broker})
        self.topic = "document_chunks"

    def delivery_report(self, err: Any, msg: Any) -> None:
        """Called once for each message produced to indicate delivery result."""
        if err is not None:
            logger.error(f"Message delivery failed: {err}")
        else:
            logger.info(f"Message delivered to {msg.topic()} [{msg.partition()}]")

    def _chunk_text(
        self, text: str, chunk_size: int = 150
    ) -> Generator[str, None, None]:
        words = text.split()
        for i in range(0, len(words), chunk_size):
            yield " ".join(words[i : i + chunk_size])

    def ingest_document(self, text: str) -> None:
        """Ingests a text document by chunking it and sending to Redpanda."""
        for chunk in self._chunk_text(text):
            payload = json.dumps({"content": chunk})
            try:
                # Produce the chunk
                self.producer.produce(
                    self.topic, payload.encode("utf-8"), callback=self.delivery_report
                )
                # Poll to serve delivery reports
                self.producer.poll(0)
            except Exception as e:
                logger.error(f"Exception during produce: {e}")

        # Wait for any outstanding messages to be delivered
        self.producer.flush()
