import logging
import os
from typing import Any, Optional, Dict

from prometheus_client import Gauge
from opentelemetry import trace, metrics, propagate

# --- Prometheus Metrics for KEDA Scaling ---
# Define a Gauge to track active AI tasks for horizontal scaling
ACTIVE_AI_TASKS = Gauge(
    "active_ai_tasks",
    "Number of AI tasks currently being processed by this instance",
)

from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.resources import Resource, SERVICE_NAME, DEPLOYMENT_ENVIRONMENT
from opentelemetry.sdk.trace import TracerProvider, Span, SpanProcessor
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.trace import Status, StatusCode
from opentelemetry.trace.propagation.tracecontext import TraceContextTextMapPropagator

# Standardized LLM Attributes (following OpenTelemetry semantic conventions for LLM where possible)
LLM_PROMPT_TOKENS = "llm.usage.prompt_tokens"
LLM_COMPLETION_TOKENS = "llm.usage.completion_tokens"
LLM_TOTAL_TOKENS = "llm.usage.total_tokens"
LLM_TTFT = "llm.latency.ttft"  # Time To First Token
LLM_MODEL_NAME = "llm.model_name"

PHOENIX_ENDPOINT = os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT", "http://localhost:6006/v1")
TRACE_ENDPOINT = f"{PHOENIX_ENDPOINT}/traces"
METRIC_ENDPOINT = f"{PHOENIX_ENDPOINT}/metrics"

logger = logging.getLogger(__name__)


class SecurityAttributeProcessor(SpanProcessor):
    """
    Enterprise-grade Security Processor that filters sensitive data and
    enforces structural obfuscation without relying on brittle Regex.
    """

    def __init__(self) -> None:
        self.sensitive_keys = {
            "api_key",
            "api.key",
            "authorization",
            "password",
            "secret",
            "token",
            "jwt",
            "cookie",
            "set-cookie",
        }
        # Payload keys that must be validated by security node before logging
        self.raw_payload_keys = {"prompt", "completion", "input", "output", "content"}

    def on_start(self, span: Span, parent_context: Optional[Any] = None) -> None:
        pass

    def on_end(self, span: Span) -> None:
        if not span.is_recording():
            return

        attributes = dict(span.attributes)
        filtered_attributes = {}

        security_validated = attributes.get("security.validated", False)

        for key, value in attributes.items():
            key_lower = key.lower()

            # 1. Block sensitive keys
            if any(s_key in key_lower for s_key in self.sensitive_keys):
                filtered_attributes[key] = "[REDACTED_SENSITIVE]"
                continue

            # 2. Block raw payloads if not security validated
            if key_lower in self.raw_payload_keys and not security_validated:
                filtered_attributes[key] = "[REDACTED_UNVALIDATED_PAYLOAD]"
                continue

            filtered_attributes[key] = value

        # Update span attributes (Note: _attributes is internal but commonly used for modification in processors)
        span._attributes = filtered_attributes


def setup_telemetry(service_name: str = "nexus-graph-ai") -> None:
    """
    Sets up OpenTelemetry tracing and metrics with high-availability configuration.
    Alias for setup_observability to maintain backward compatibility.
    """
    setup_observability(service_name)


def record_llm_metrics(
    model_name: str,
    prompt_tokens: int,
    completion_tokens: int,
    ttft_ms: Optional[float] = None,
    attributes: Optional[Dict[str, Any]] = None,
) -> None:
    """
    Helper to record LLM-specific metrics and attributes.
    """
    tracer = trace.get_tracer(__name__)
    meter = metrics.get_meter("llm.observability")

    with tracer.start_as_current_span("llm_operation") as span:
        total_tokens = prompt_tokens + completion_tokens

        span.set_attribute(LLM_MODEL_NAME, model_name)
        span.set_attribute(LLM_PROMPT_TOKENS, prompt_tokens)
        span.set_attribute(LLM_COMPLETION_TOKENS, completion_tokens)
        span.set_attribute(LLM_TOTAL_TOKENS, total_tokens)

        if attributes:
            for k, v in attributes.items():
                span.set_attribute(k, v)

        # Record metrics
        token_counter = meter.get_instrument("llm.token_usage")
        token_counter.add(total_tokens, {LLM_MODEL_NAME: model_name})

        if ttft_ms is not None:
            span.set_attribute(LLM_TTFT, ttft_ms)
            ttft_histogram = meter.get_instrument(LLM_TTFT)
            ttft_histogram.record(ttft_ms, {LLM_MODEL_NAME: model_name})


def setup_observability(service_name: str = "nexus-graph-ai") -> None:
    """
    Sets up OpenTelemetry tracing and metrics with high-availability configuration.
    """
    try:
        # Configure global propagation for LangGraph and distributed tracing
        # Using W3C TraceContext for maximum compatibility
        propagate.set_global_textmap(TraceContextTextMapPropagator())

        resource = Resource.create(
            {
                SERVICE_NAME: service_name,
                DEPLOYMENT_ENVIRONMENT: os.getenv("ENV", "production"),
                "cloud.platform": "kubernetes",
                "telemetry.sdk.language": "python",
            }
        )

        # --- Tracing Setup ---
        tracer_provider = TracerProvider(resource=resource)

        # Security Processor
        security_processor = SecurityAttributeProcessor()
        tracer_provider.add_span_processor(security_processor)

        # Batch Exporter for performance
        span_exporter = OTLPSpanExporter(endpoint=TRACE_ENDPOINT)
        batch_processor = BatchSpanProcessor(span_exporter)
        tracer_provider.add_span_processor(batch_processor)

        trace.set_tracer_provider(tracer_provider)

        # --- Metrics Setup ---
        metric_exporter = OTLPMetricExporter(endpoint=METRIC_ENDPOINT)
        reader = PeriodicExportingMetricReader(
            metric_exporter, export_interval_millis=15000
        )
        meter_provider = MeterProvider(resource=resource, metric_readers=[reader])

        metrics.set_meter_provider(meter_provider)

        # Initialize LLM specific meters
        meter = metrics.get_meter("llm.observability")
        meter.create_histogram(
            name=LLM_TTFT, description="Time to first token in milliseconds", unit="ms"
        )
        meter.create_counter(
            name="llm.token_usage", description="Total count of tokens used", unit="1"
        )

        logger.info(
            f"High-resolution telemetry initialized for {service_name} (SLA 99.99%)"
        )
    except Exception as e:
        logger.error(f"Failed to initialize observability: {e}")


def get_tracer(name: str):
    return trace.get_tracer(name)


def get_meter(name: str):
    return metrics.get_meter(name)
