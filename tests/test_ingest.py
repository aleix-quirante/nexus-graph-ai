import os
import tempfile
import json
from unittest.mock import MagicMock, patch
import pytest

from cli.ingest import DocumentProducer


@pytest.fixture
def mock_producer():
    with patch("cli.ingest.Producer") as mock:
        # Create a magic mock for the instance
        instance_mock = MagicMock()
        mock.return_value = instance_mock
        yield instance_mock


@pytest.fixture
def temp_document():
    # Create a document with exactly 10,000 words
    fd, path = tempfile.mkstemp(suffix=".txt", text=True)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for i in range(10000):
                f.write(f"word{i} ")
        yield path
    finally:
        os.remove(path)


def test_document_producer_success(mock_producer, temp_document):
    """
    Test that DocumentProducer processes exactly 10,000 words into chunks
    and publishes them without memory leaks or exceptions.
    """
    # Initialize producer
    broker_url = "dummy:9092"
    topic = "document_chunks"
    chunk_size = 1000
    expected_chunks = 10000 // chunk_size  # 10 chunks

    with DocumentProducer(broker_url=broker_url, topic=topic) as producer:
        # Act
        result_chunks = producer.process_file(
            temp_document, chunk_size_words=chunk_size
        )

        # Assert total chunks returned
        assert result_chunks == expected_chunks

        # Assert producer methods were called correctly
        assert mock_producer.produce.call_count == expected_chunks

        # Verify the arguments of the produce calls
        for i, call_args in enumerate(mock_producer.produce.call_args_list):
            kwargs = call_args[1]
            assert kwargs["topic"] == topic

            payload = json.loads(kwargs["value"].decode("utf-8"))
            assert payload["chunk_index"] == i
            assert payload["file_name"] == os.path.basename(temp_document)
            assert len(payload["text"].split()) == chunk_size

            assert "on_delivery" in kwargs

        mock_producer.flush.assert_called_once()


def test_document_producer_connection_retry():
    with patch("cli.ingest.Producer") as mock_prod_class:
        mock_prod_class.side_effect = Exception("Connection Failed")

        with pytest.raises(ConnectionError) as exc_info:
            DocumentProducer(broker_url="dummy:9092", max_retries=3, base_backoff=0.01)

        assert "Failed to connect to Kafka broker" in str(exc_info.value)
        assert mock_prod_class.call_count == 3
