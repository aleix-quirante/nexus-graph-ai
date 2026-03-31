import logging
import re
from typing import Any

from opentelemetry import trace
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor, SpanExporter
from opentelemetry.sdk.trace import Span

PHOENIX_ENDPOINT = "http://localhost:6006/v1/traces"

logger = logging.getLogger(__name__)


class ObfuscatingSpanProcessor(BatchSpanProcessor):
    def __init__(self, exporter: SpanExporter, *args: Any, **kwargs: Any) -> None:
        super().__init__(exporter, *args, **kwargs)

    def _obfuscate_value(self, value: Any) -> Any:
        if not isinstance(value, str):
            return value

        # Obfuscate Authorization headers, Bearer tokens, API keys
        obfuscated = re.sub(
            r"(?i)(bearer|api[_\-]?key|secret|token|password|auth(?:orization)?)\s*[:=]\s*[^\s,\"\']+",
            r"\1: ***REDACTED***",
            value,
        )
        # Obfuscate potential PII like emails
        obfuscated = re.sub(
            r"[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+",
            "***REDACTED_EMAIL***",
            obfuscated,
        )
        return obfuscated

    def on_end(self, span: Span) -> None:
        if hasattr(span, "attributes") and span.attributes:
            new_attributes = {}
            for k, v in span.attributes.items():
                if isinstance(v, str):
                    new_attributes[k] = self._obfuscate_value(v)
                elif isinstance(v, list) and all(isinstance(i, str) for i in v):
                    new_attributes[k] = [self._obfuscate_value(i) for i in v]
                else:
                    new_attributes[k] = v
            # In OpenTelemetry Python, attributes are stored in a BoundedAttributes object.
            # We can update it carefully or recreate it, but for our requirements:
            span._attributes = new_attributes

        super().on_end(span)


def setup_telemetry(service_name: str) -> None:
    try:
        resource = Resource.create({"service.name": service_name})
        provider = TracerProvider(resource=resource)

        exporter = OTLPSpanExporter(endpoint=PHOENIX_ENDPOINT)
        processor = ObfuscatingSpanProcessor(exporter)

        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)
        logger.info(f"OpenTelemetry successfully initialized for {service_name}")
    except Exception as e:
        logger.error(f"Failed to initialize OpenTelemetry for {service_name}: {e}")


def setup_observability() -> None:
    setup_telemetry("nexus-graph-ai")
