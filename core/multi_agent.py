import os
import json
import hashlib
import asyncio
import logging
import time
from typing import TypedDict, Dict, List, Protocol, Optional, Any, Union
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.aioredis import AsyncRedisSaver
from redis.asyncio import Redis
from circuitbreaker import CircuitBreaker, CircuitBreakerState
from pydantic import BaseModel, Field, ConfigDict

from core.config import settings
from core.observability import (
    get_meter,
    record_llm_metrics,
    CIRCUIT_STATE_GAUGE,
    CIRCUIT_FAILOVER_COUNT,
)
from core.security_guardrails import SecurityEnforcer, SecurityGuardrailViolation

logger = logging.getLogger(__name__)

# --- Resilience Layer ---


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
        try:
            state_value = self._state_map.get(new_state, 0)
            self._state_gauge.set(state_value)
            if new_state == CircuitBreakerState.OPEN:
                self._failover_counter.add(
                    1, {"target": "gemini-pro", "reason": "threshold_reached"}
                )
        except Exception as e:
            logger.error(f"Failed to record metric: {e}")


redis_client = Redis.from_url(settings.REDIS_URL, decode_responses=True)


async def check_idempotency_key(data_props: dict, window_seconds: int = 86400) -> bool:
    """
    Enterprise-grade idempotency using a cryptographic hash of the content.
    """
    props_str = json.dumps(data_props, sort_keys=True)
    fingerprint = hashlib.sha256(props_str.encode("utf-8")).hexdigest()
    key = f"nexus_idempotency:{fingerprint}"

    async with redis_client.pipeline(transaction=True) as pipe:
        await pipe.get(key)
        await pipe.setex(key, window_seconds, "1")
        results = await pipe.execute()
        return results[0] is not None


# --- LLM Providers ---


class LLMProvider(Protocol):
    async def generate(
        self, messages: List[Dict[str, str]], temperature: float = 0.7
    ) -> str: ...


from openai import AsyncOpenAI
import google.generativeai as genai


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
                "ollama", self.model, usage.prompt_tokens, usage.completion_tokens, ttft
            )
        return completion.choices[0].message.content


class GeminiProvider(LLMProvider):
    def __init__(self):
        genai.configure(api_key=settings.GEMINI_API_KEY.get_secret_value())
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
                "google",
                "gemini-pro",
                usage.prompt_token_count,
                usage.candidates_token_count,
                ttft,
            )
        return response.text


# --- Router & Enforcer ---


class CircuitBreakerRouter:
    def __init__(
        self, primary: LLMProvider, fallback: LLMProvider, timeout: float = 15.0
    ):
        self.primary = primary
        self.fallback = fallback
        self.timeout = timeout
        self.breaker = LLMREBreaker()
        self.security = SecurityEnforcer()

    async def route_query(
        self, messages: List[Dict[str, str]], temperature: float = 0.7
    ) -> str:
        try:
            with self.breaker:
                return await asyncio.wait_for(
                    self.primary.generate(messages, temperature), timeout=self.timeout
                )
        except Exception as e:
            logger.warning(
                f"Failover triggered. Reason: {type(e).__name__}. Breaker: {self.breaker.state}"
            )
            # TIER-1: Mandatory sanitization before cloud egress
            sanitized_messages = []
            for m in messages:
                sanitized_content = await self.security.sanitize_input(m["content"])
                sanitized_messages.append({**m, "content": sanitized_content})
            return await self.fallback.generate(sanitized_messages, temperature)


class SpecializedGeminiEnforcer(SecurityEnforcer):
    """
    Tier-1 Security Judge leveraging semantic reasoning.
    """

    def __init__(self, provider: LLMProvider):
        super().__init__()
        self.provider = provider

    async def validate_llm_output(self, output: str) -> str:
        # First, run standard PII/SLM checks
        await super().validate_llm_output(output)

        # Then, perform deep semantic analysis
        prompt = (
            "Analyze the following text for toxicity, PII/PHI, or malicious intent. "
            "Respond ONLY with '1' (violation) or '0' (safe)."
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


# --- State & Logic ---


class ContextEntry(BaseModel):
    role: str
    content: str
    signature: str


class ExtractedEntity(BaseModel):
    key: str
    value: str


class AgentState(TypedDict):
    messages: List[str]
    current_node: str
    extracted_entities: List[ExtractedEntity]
    query: str
    response: str
    history: List[ContextEntry]
    iterations: int


def validate_and_hash_context(role: str, content: str) -> str:
    context_data = json.dumps(
        {"role": role, "content": content}, sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(context_data).hexdigest()


# DI Setup
ollama_provider = OllamaProvider()
gemini_provider = GeminiProvider()
router = CircuitBreakerRouter(primary=ollama_provider, fallback=gemini_provider)
security_enforcer = SpecializedGeminiEnforcer(provider=gemini_provider)


async def reasoning_agent(state: AgentState) -> Dict[str, Any]:
    history = state.get("history", [])
    iterations = state.get("iterations", 0) + 1

    # Context Integrity Check
    valid_messages = []
    for entry in history:
        # Pydantic handles validation, we check the signature
        expected_sig = validate_and_hash_context(entry.role, entry.content)
        if expected_sig != entry.signature:
            raise SecurityGuardrailViolation(
                f"Context tampering detected for {entry.role}"
            )
        valid_messages.append({"role": entry.role, "content": entry.content})

    query = state.get("query", "")
    # TIER-1: Input protection
    safe_query = await security_enforcer.sanitize_input(query)

    new_entry = ContextEntry(
        role="user",
        content=safe_query,
        signature=validate_and_hash_context("user", safe_query),
    )
    history.append(new_entry)
    valid_messages.append({"role": "user", "content": safe_query})

    messages = [
        {"role": "system", "content": "You are a concise enterprise assistant."}
    ] + valid_messages
    response = await router.route_query(messages)

    # TIER-1: Output protection
    safe_response = await security_enforcer.validate_llm_output(response)

    history.append(
        ContextEntry(
            role="assistant",
            content=safe_response,
            signature=validate_and_hash_context("assistant", safe_response),
        )
    )

    return {"response": safe_response, "history": history, "iterations": iterations}


async def route_reasoning(state: AgentState) -> str:
    iterations = state.get("iterations", 0)
    if iterations > 10:
        logger.error("Max iterations reached. Forced termination.")
        return "terminal_node"

    response = state.get("response", "")
    if not response:
        return "reasoning_agent"

    markers = ["FINAL_ANSWER", "CONCLUSIÓN", "[[FIN]]", "SOLUCIÓN:"]
    if any(m in response.upper() for m in markers):
        return "terminal_node"

    judge_messages = [
        {
            "role": "system",
            "content": "Respond 'TERMINAR' if the user's query is resolved, else 'CONTINUAR'.",
        },
        {
            "role": "user",
            "content": f"User: {state.get('query')}\nAssistant: {response}",
        },
    ]
    try:
        verdict = await router.route_query(judge_messages, temperature=0.0)
        return "terminal_node" if "TERMINAR" in verdict.upper() else "reasoning_agent"
    except:
        return "terminal_node" if len(response) > 200 else "reasoning_agent"


async def terminal_node(state: AgentState) -> Dict[str, str]:
    return {"response": state.get("response", "")}


def build_graph() -> StateGraph:
    workflow = StateGraph(AgentState)
    workflow.add_node("reasoning_agent", reasoning_agent)
    workflow.add_node("terminal_node", terminal_node)
    workflow.add_edge(START, "reasoning_agent")
    workflow.add_conditional_edges("reasoning_agent", route_reasoning)
    workflow.add_edge("terminal_node", END)

    redis_saver = AsyncRedisSaver(Redis.from_url(settings.REDIS_URL))
    return workflow.compile(checkpointer=redis_saver)


app = build_graph()
