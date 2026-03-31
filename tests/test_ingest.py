import json
import pytest
from unittest.mock import MagicMock, patch
from cli.ingest import DocumentProducer


@pytest.fixture
def mock_producer():
    with patch("cli.ingest.Producer") as MockProducer:
        mock = MagicMock()
        MockProducer.return_value = mock
        yield mock


def test_chunking_and_ingestion(mock_producer):
    # Initialize the producer using the mocked Producer
    producer = DocumentProducer()

    # Create a text with exactly 300 words
    word_list = [f"word{i}" for i in range(300)]
    text = " ".join(word_list)

    # Ingest the document
    producer.ingest_document(text)

    # Verify that produce was called exactly twice (300 words / 150 chunk_size)
    assert mock_producer.produce.call_count == 2

    call_args_list = mock_producer.produce.call_args_list

    # Verify the payload of the first call
    first_chunk_words = " ".join(word_list[:150])
    expected_payload_1 = json.dumps({"content": first_chunk_words}).encode("utf-8")
    assert call_args_list[0][0][1] == expected_payload_1

    # Verify the payload of the second call
    second_chunk_words = " ".join(word_list[150:])
    expected_payload_2 = json.dumps({"content": second_chunk_words}).encode("utf-8")
    assert call_args_list[1][0][1] == expected_payload_2

    # Ensure flush is called at the end
    mock_producer.flush.assert_called_once()
