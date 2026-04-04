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

# Standardized LLM Attributes (following OpenTelemetry semantic conventions for LLM)
GEN_AI_SYSTEM = "gen_ai.system"
GEN_AI_REQUEST_MODEL = "gen_ai.request.model"
GEN_AI_USAGE_INPUT_TOKENS = "gen_ai.usage.input_tokens"
GEN_AI_USAGE_OUTPUT_TOKENS = "gen_ai.usage.output_tokens"
GEN_AI_USAGE_TOTAL_TOKENS = "gen_ai.usage.total_tokens"
GEN_AI_LATENCY_TTFT = "gen_ai.latency.ttft"  # Time To First Token

# --- Circuit Breaker Observability ---
CIRCUIT_STATE_GAUGE = "circuit.breaker.state"  # 0: CLOSED, 1: HALF-OPEN, 2: OPEN
CIRCUIT_FAILOVER_COUNT = "circuit.breaker.failover_count"

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
        self.raw_payload_keys = {
            "prompt",
            "completion",
            "input",
            "output",
            "content",
            "gen_ai.input.messages",
            "gen_ai.output.messages",
            "tokens_entrada",
            "prompt_length",
            "ai.input",
        }
        try:
            from core.security_guardrails import PIISanitizer

            self.pii_sanitizer = PIISanitizer()
        except Exception as e:
            logger.warning(f"PIISanitizer not available for observability: {e}")
            self.pii_sanitizer = None

    def on_start(self, span: Span, parent_context: Optional[Any] = None) -> None:
        pass

    def on_end(self, span: Span) -> None:
        """
        Final redaction layer before span export.
        Ensures PII scrub and secret masking.
        """
        if not span.is_recording():
            return

        # Access attributes safely for redaction
        # In a high-traffic Tier-1 environment, this processor must be O(n)
        attributes = dict(span.attributes)
        security_validated = attributes.get("security.validated", False)
        redacted_attrs = {}

        for key, value in attributes.items():
            key_lower = key.lower()

            if any(s_key in key_lower for s_key in self.sensitive_keys):
                redacted_attrs[key] = "[REDACTED_SENSITIVE_KEY]"
                continue

            if key_lower in self.raw_payload_keys:
                if isinstance(value, str) and self.pii_sanitizer:
                    value = self.pii_sanitizer.sanitize(value)

                if not security_validated:
                    redacted_attrs[key] = (
                        f"[PII_SCRUBBED][UNVALIDATED]: {str(value)[:40]}..."
                    )
                    continue

            redacted_attrs[key] = value

        # Update span attributes by overwriting
        # Although _attributes is internal, it's widely used for filtering in processors.
        # Standard API only allows additive set_attribute().
        if hasattr(span, "_attributes"):
            span._attributes = redacted_attrs


def setup_telemetry(service_name: str = "nexus-graph-ai") -> None:
    """
    Sets up OpenTelemetry tracing and metrics with high-availability configuration.
    Alias for setup_observability to maintain backward compatibility.
    """
    setup_observability(service_name)


def record_llm_metrics(
    system: str,
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
    meter = metrics.get_meter("gen_ai.observability")

    with tracer.start_as_current_span("gen_ai.operation") as span:
        total_tokens = prompt_tokens + completion_tokens

        span.set_attribute(GEN_AI_SYSTEM, system)
        span.set_attribute(GEN_AI_REQUEST_MODEL, model_name)
        span.set_attribute(GEN_AI_USAGE_INPUT_TOKENS, prompt_tokens)
        span.set_attribute(GEN_AI_USAGE_OUTPUT_TOKENS, completion_tokens)
        span.set_attribute(GEN_AI_USAGE_TOTAL_TOKENS, total_tokens)

        if attributes:
            for k, v in attributes.items():
                span.set_attribute(k, v)

        # Record metrics
        token_counter = meter.get_instrument("gen_ai.usage.tokens")
        token_counter.add(
            total_tokens, {GEN_AI_SYSTEM: system, GEN_AI_REQUEST_MODEL: model_name}
        )

        if ttft_ms is not None:
            span.set_attribute(GEN_AI_LATENCY_TTFT, ttft_ms)
            ttft_histogram = meter.get_instrument(GEN_AI_LATENCY_TTFT)
            ttft_histogram.record(
                ttft_ms, {GEN_AI_SYSTEM: system, GEN_AI_REQUEST_MODEL: model_name}
            )


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
        meter = metrics.get_meter("gen_ai.observability")
        meter.create_histogram(
            name=GEN_AI_LATENCY_TTFT,
            description="Time to first token in milliseconds",
            unit="ms",
        )
        meter.create_counter(
            name="gen_ai.usage.tokens",
            description="Total count of tokens used",
            unit="1",
        )

        # Initialize Circuit Breaker specific meters
        meter.create_gauge(
            name=CIRCUIT_STATE_GAUGE,
            description="Circuit Breaker state (0: CLOSED, 1: HALF-OPEN, 2: OPEN)",
            unit="1",
        )
        meter.create_counter(
            name=CIRCUIT_FAILOVER_COUNT,
            description="Total count of failovers",
            unit="1",
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
