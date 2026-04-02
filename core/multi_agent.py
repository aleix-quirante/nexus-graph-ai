import os
import json
import hashlib
import asyncio
import logging
from typing import TypedDict, Dict, List, Protocol, Optional, Any
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.aioredis import AsyncRedisSaver
import time
from redis.asyncio import Redis
from circuitbreaker import CircuitBreaker, CircuitBreakerState

from core.observability import (
    get_meter,
    record_llm_metrics,
    CIRCUIT_STATE_GAUGE,
    CIRCUIT_FAILOVER_COUNT,
)
from core.pii_sanitizer import pii_sanitizer_instance

logger = logging.getLogger(__name__)


class LLMREBreaker(CircuitBreaker):
    """
    Enterprise-grade Circuit Breaker for LLM failover.
    Tracks state transitions and reports to OpenTelemetry.
    """

    FAILURE_THRESHOLD = 3
    RECOVERY_TIMEOUT = 60  # seconds

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("failure_threshold", self.FAILURE_THRESHOLD)
        kwargs.setdefault("recovery_timeout", self.RECOVERY_TIMEOUT)
        kwargs.setdefault("name", "llm_primary_breaker")
        super().__init__(*args, **kwargs)
        self._meter = get_meter("gen_ai.resilience")
        self._state_map = {
            CircuitBreakerState.CLOSED: 0,
            CircuitBreakerState.HALF_OPEN: 1,
            CircuitBreakerState.OPEN: 2,
        }
        # Initialize instruments
        self._state_gauge = self._meter.create_gauge(
            name=CIRCUIT_STATE_GAUGE,
            description="Circuit Breaker state (0: CLOSED, 1: HALF-OPEN, 2: OPEN)",
            unit="1",
        )
        self._failover_counter = self._meter.create_counter(
            name=CIRCUIT_FAILOVER_COUNT,
            description="Total count of failovers",
            unit="1",
        )

    def on_state_change(self, old_state, new_state):
        logger.warning(
            f"CIRCUIT BREAKER STATE CHANGE: {old_state.name} -> {new_state.name}"
        )

        # Update OTel metrics
        try:
            state_value = self._state_map.get(new_state, 0)
            self._state_gauge.set(state_value)

            # Track failover count when entering OPEN state
            if new_state == CircuitBreakerState.OPEN:
                self._failover_counter.add(
                    1, {"target": "gemini-pro", "reason": "threshold_reached"}
                )
        except Exception as e:
            logger.error(f"Failed to record metric: {e}")


# Create redis client using centralized settings
from core.config import settings

redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)


async def check_idempotency_key(data_props: dict, window_seconds: int = 86400) -> bool:
    """
    Enterprise-grade idempotency using a cryptographic hash of the content.
    Prevents duplicate mutations across distributed nodes for 24 hours.
    """
    props_str = json.dumps(data_props, sort_keys=True)
    fingerprint = hashlib.sha256(props_str.encode("utf-8")).hexdigest()

    key = f"nexus_idempotency:{fingerprint}"

    # Atomic Check-and-Set using a Redis pipeline
    async with redis_client.pipeline(transaction=True) as pipe:
        await pipe.get(key)
        await pipe.setex(key, window_seconds, "1")
        results = await pipe.execute()

        is_processed = results[0]
        if is_processed:
            logger.info(
                f"Duplicate request detected for fingerprint: {fingerprint[:8]}"
            )
            return True
        return False


# ... rest remains unchanged but I'll patch the whole file ...

from openai import AsyncOpenAI
import google.generativeai as genai

from core.security_guardrails import SecurityEnforcer, SecurityGuardrailViolation


class LLMProvider(Protocol):
    async def generate(
        self, messages: List[Dict[str, str]], temperature: float = 0.7
    ) -> str: ...


class OllamaProvider(LLMProvider):
    def __init__(self, base_url: str = "http://localhost:11434/v1"):
        self.client = AsyncOpenAI(base_url=base_url, api_key="ollama")
        self.model = "llama3"

    async def generate(
        self, messages: List[Dict[str, str]], temperature: float = 0.7
    ) -> str:
        start_time = time.time()
        completion = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
        )
        ttft = (time.time() - start_time) * 1000

        usage = getattr(completion, "usage", None)
        if usage:
            record_llm_metrics(
                system="ollama",
                model_name=self.model,
                prompt_tokens=usage.prompt_tokens,
                completion_tokens=usage.completion_tokens,
                ttft_ms=ttft,
            )

        return completion.choices[0].message.content


class GeminiProvider(LLMProvider):
    def __init__(self):
        genai.configure(api_key=os.environ.get("GEMINI_API_KEY", "default"))
        self.model = genai.GenerativeModel("gemini-pro")

    async def generate(
        self, messages: List[Dict[str, str]], temperature: float = 0.7
    ) -> str:
        prompt = "\n".join([f"{m['role']}: {m['content']}" for m in messages])
        start_time = time.time()
        response = await self.model.generate_content_async(
            prompt,
            generation_config=genai.types.GenerationConfig(temperature=temperature),
        )
        ttft = (time.time() - start_time) * 1000

        usage = getattr(response, "usage_metadata", None)
        if usage:
            record_llm_metrics(
                system="google",
                model_name="gemini-pro",
                prompt_tokens=usage.prompt_token_count,
                completion_tokens=usage.candidates_token_count,
                ttft_ms=ttft,
            )

        return response.text


class CircuitBreakerRouter:
    def __init__(
        self, primary: LLMProvider, fallback: LLMProvider, timeout: float = 15.0
    ):
        self.primary = primary
        self.fallback = fallback
        self.timeout = timeout
        self.breaker = LLMREBreaker(
            name="llm_primary_breaker",
            failure_threshold=3,
            recovery_timeout=60,
        )

    async def route_query(
        self, messages: List[Dict[str, str]], temperature: float = 0.7
    ) -> str:
        """
        Routes the LLM query using an enterprise-grade Circuit Breaker pattern.
        If the primary local provider fails 3 times, redirects to cloud fallback (Gemini Pro).
        Recovery (HALF-OPEN) begins after 60s cooldown.
        """
        try:
            # The circuit breaker context manager handles failures and state transitions.
            # It raises circuitbreaker.CircuitBreakerError if the state is OPEN.
            with self.breaker:
                return await asyncio.wait_for(
                    self.primary.generate(messages, temperature), timeout=self.timeout
                )
        except Exception as e:
            # Log the incident and trigger failover to cloud provider
            logger.warning(
                f"Failover triggered to Gemini Pro. Reason: {type(e).__name__} ({str(e)}). "
                f"Breaker state: {self.breaker.state}"
            )
            # ALERTA ZERO-TRUST: Sanitización obligatoria antes de salir a la nube
            safe_messages = [
                {**m, "content": pii_sanitizer_instance.sanitize_prompt(m["content"])}
                for m in messages
            ]
            return await self.fallback.generate(safe_messages, temperature)


class SpecializedGeminiEnforcer(SecurityEnforcer):
    def __init__(self, provider: LLMProvider):
        self.provider = provider

    async def validate_llm_output(self, output: str) -> str:
        prompt = (
            "You are a strict security guardrail system. Analyze the following text "
            "for toxicity, confidential information (PII/PHI), or malicious intent. "
            "Respond ONLY with '1' if any of these are present (violation), or '0' if the text is safe. "
            "Evaluate the semantic context to resist evasion tactics like Leetspeak, obfuscation, or Base64."
        )
        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": output},
        ]

        judge_response = await self.provider.generate(messages, temperature=0.0)

        if "1" in judge_response:
            raise SecurityGuardrailViolation(
                "Semantic security violation detected by SLM Judge"
            )
        return output


class ContextEntry(TypedDict):
    content: str
    role: str
    signature: str


class ExtractedEntity(TypedDict):
    key: str
    value: str


class AgentState(TypedDict):
    messages: List[str]
    current_node: str
    extracted_entities: List[ExtractedEntity]
    query: str
    response: str
    history: List[ContextEntry]


def validate_and_hash_context(role: str, content: str) -> str:
    context_data = json.dumps(
        {"role": role, "content": content}, sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(context_data).hexdigest()


class DataConsistencyError(Exception):
    pass


# Dependency Injection setup
ollama_provider = OllamaProvider()
gemini_provider = GeminiProvider()
router = CircuitBreakerRouter(primary=ollama_provider, fallback=gemini_provider)
security_enforcer = SpecializedGeminiEnforcer(provider=gemini_provider)


async def reasoning_agent(state: AgentState) -> Dict[str, List[ContextEntry] | str]:
    history = state.get("history", [])
    valid_messages = []

    for entry in history:
        expected_sig = validate_and_hash_context(entry["role"], entry["content"])
        if expected_sig == entry["signature"]:
            valid_messages.append({"role": entry["role"], "content": entry["content"]})
        else:
            raise DataConsistencyError(
                f"Context integrity validation failed for role: {entry['role']}"
            )

    current_query = state.get("query", "")
    query_signature = validate_and_hash_context("user", current_query)

    new_entry: ContextEntry = {
        "role": "user",
        "content": current_query,
        "signature": query_signature,
    }

    history.append(new_entry)
    valid_messages.append({"role": "user", "content": current_query})

    messages = [
        {"role": "system", "content": "Eres un asistente experto y conciso."}
    ] + valid_messages

    respuesta_real = await router.route_query(messages, temperature=0.7)

    response_signature = validate_and_hash_context("assistant", respuesta_real)
    history.append(
        {
            "role": "assistant",
            "content": respuesta_real,
            "signature": response_signature,
        }
    )

    return {"response": respuesta_real, "history": history}


async def route_reasoning(state: AgentState) -> str:
    """
    Evaluador determinista y por IA del estado de terminación.
    Sustituye la heurística amateur de longitud por un juicio semántico.
    """
    response = state.get("response", "")
    query = state.get("query", "")

    if not response:
        return "reasoning_agent"

    # 1. Condición Determinista (Fast-path): Búsqueda de marcadores de finalización
    markers = ["FINAL_ANSWER", "CONCLUSIÓN", "[[FIN]]", "SOLUCIÓN:"]
    if any(m in response.upper() for m in markers):
        logger.info("Terminación detectada por marcador determinista.")
        return "terminal_node"

    # 2. LLM Judge Ligero: Evaluación semántica de suficiencia
    judge_messages = [
        {
            "role": "system",
            "content": "Eres un Juez de Terminación. Responde 'TERMINAR' si la respuesta del asistente resuelve la duda del usuario por completo. Responde 'CONTINUAR' si se necesita más investigación o razonamiento. Responde solo con una palabra.",
        },
        {"role": "user", "content": f"Usuario: {query}\nAsistente: {response}"},
    ]

    try:
        # Reutilizamos el router con circuit breaker para el juicio
        veredicto = await router.route_query(judge_messages, temperature=0.0)
        if "TERMINAR" in veredicto.upper():
            logger.info("Terminación decidida por LLM Judge.")
            return "terminal_node"
    except Exception as e:
        logger.error(f"Error en LLM Judge: {e}. Aplicando fallback de seguridad.")
        # Fallback conservador: si el juez falla, solo terminamos si la respuesta es sustancial
        if len(response) > 100:
            return "terminal_node"

    return "reasoning_agent"


async def terminal_node(state: AgentState) -> Dict[str, str]:
    response_to_validate = state.get("response", "")

    try:
        validated_output = await security_enforcer.validate_llm_output(
            response_to_validate
        )
        return {"response": validated_output}
    except SecurityGuardrailViolation as e:
        return {"response": f"Bloqueado por seguridad: {str(e)}"}


def build_graph() -> StateGraph:
    workflow = StateGraph(AgentState)
    workflow.add_node("reasoning_agent", reasoning_agent)
    workflow.add_node("terminal_node", terminal_node)
    workflow.add_edge(START, "reasoning_agent")
    workflow.add_conditional_edges("reasoning_agent", route_reasoning)
    workflow.add_edge("terminal_node", END)

    redis_connection = Redis.from_url(settings.REDIS_URL)
    redis_saver = AsyncRedisSaver(redis_connection)
    app = workflow.compile(checkpointer=redis_saver)
    # The recursion_limit is set natively when invoking the graph
    # Example: app.invoke(state, config={"recursion_limit": 20})
    return app


app = build_graph()
