import pytest
from unittest.mock import MagicMock, patch
from opentelemetry.sdk.trace import Span
from core.observability import (
    setup_observability,
    ObfuscatingSpanProcessor,
    PHOENIX_ENDPOINT,
)


def test_setup_observability():
    with patch("core.observability.trace") as mock_trace:
        setup_observability()
        assert mock_trace.set_tracer_provider.called
        provider = mock_trace.set_tracer_provider.call_args[0][0]
        processors = provider._active_span_processor._span_processors
        assert len(processors) > 0
        processor = processors[0]
        assert isinstance(processor, ObfuscatingSpanProcessor)
        assert processor.span_exporter._endpoint == PHOENIX_ENDPOINT


def test_obfuscation_logic():
    mock_exporter = MagicMock()
    processor = ObfuscatingSpanProcessor(mock_exporter)

    mock_span = MagicMock(spec=Span)
    mock_span.attributes = {
        "user.email": "test@example.com",
        "auth.header": "Bearer valid_token_123",
        "db.password": "password=secret",
        "safe.data": "no sensitive info here",
    }

    processor.on_end(mock_span)

    assert mock_span._attributes["user.email"] == "***REDACTED_EMAIL***"
    assert mock_span._attributes["auth.header"] == "Bearer ***REDACTED***"
    assert "password= ***REDACTED***" in mock_span._attributes["db.password"]
    assert mock_span._attributes["safe.data"] == "no sensitive info here"
