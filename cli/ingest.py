import sys
import os
import json
import logging
import time
from typing import Generator, Any, Dict, Optional
from confluent_kafka import Producer, KafkaError

logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


class DocumentProducer:
    """
    Produces document chunks to a Kafka/Redpanda topic.
    """

    def __init__(
        self,
        broker_url: str,
        topic: str = "document_chunks",
        max_retries: int = 5,
        base_backoff: float = 1.0,
    ):
        self.broker_url = broker_url
        self.topic = topic
        self.max_retries = max_retries
        self.base_backoff = base_backoff
        self.producer = self._connect()

    def _connect(self) -> Producer:
        conf = {
            "bootstrap.servers": self.broker_url,
            "client.id": "document-producer",
            "acks": "all",
            "retries": 3,
            "retry.backoff.ms": 500,
        }
        for attempt in range(self.max_retries):
            try:
                producer = Producer(conf)
                # Test connection conceptually (confluent-kafka connects asynchronously)
                return producer
            except Exception as e:
                logger.error(f"Connection attempt {attempt + 1} failed: {e}")
                if attempt == self.max_retries - 1:
                    raise ConnectionError(
                        f"Failed to connect to Kafka broker at {self.broker_url} after {self.max_retries} attempts."
                    ) from e
                time.sleep(self.base_backoff * (2**attempt))

        raise ConnectionError("Failed to initialize Kafka producer.")

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        if self.producer:
            logger.info("Flushing producer...")
            self.producer.flush()

    def _delivery_callback(self, err: Optional[KafkaError], msg: Any):
        """
        Optional per-message delivery callback (triggered by poll() or flush())
        when a message has been successfully delivered or permanently failed delivery.
        """
        if err is not None:
            logger.error(f"Message delivery failed: {err}")
        else:
            logger.debug(
                f"Message delivered to {msg.topic()} [{msg.partition()}] at offset {msg.offset()}"
            )

    def _read_chunks(
        self, file_path: str, chunk_size_words: int = 1000
    ) -> Generator[str, None, None]:
        """
        Reads a file iteratively and yields chunks of text based on word count.
        """
        try:
            with open(file_path, "r", encoding="utf-8") as f:
                current_chunk = []
                current_words = 0
                for line in f:
                    words = line.split()
                    for word in words:
                        current_chunk.append(word)
                        current_words += 1
                        if current_words >= chunk_size_words:
                            yield " ".join(current_chunk)
                            current_chunk = []
                            current_words = 0
                if current_chunk:
                    yield " ".join(current_chunk)
        except Exception as e:
            logger.error(f"Error reading file {file_path}: {e}")
            raise

    def process_file(self, file_path: str, chunk_size_words: int = 1000):
        """
        Processes a file, chunks it, and publishes to Kafka.
        """
        logger.info(f"Processing file: {file_path}")
        chunk_count = 0
        for chunk_text in self._read_chunks(file_path, chunk_size_words):
            payload = {
                "file_name": os.path.basename(file_path),
                "chunk_index": chunk_count,
                "text": chunk_text,
                "timestamp": time.time(),
            }
            try:
                serialized_payload = json.dumps(payload).encode("utf-8")
                self.producer.produce(
                    topic=self.topic,
                    value=serialized_payload,
                    on_delivery=self._delivery_callback,
                )
                self.producer.poll(0)  # Serve delivery callback queue
                chunk_count += 1
            except Exception as e:
                logger.error(f"Error publishing chunk {chunk_count}: {e}")
                raise

        self.producer.flush()
        logger.info(f"Successfully processed {chunk_count} chunks from {file_path}")
        return chunk_count


def main():
    if len(sys.argv) < 2:
        print("Usage: python cli/ingest.py <file_path>")
        sys.exit(1)

    file_path = sys.argv[1]
    broker_url = os.environ.get("KAFKA_BROKER_URL", "localhost:9092")

    try:
        with DocumentProducer(broker_url=broker_url) as producer:
            producer.process_file(file_path)
    except Exception as e:
        logger.error(f"Ingestion failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
