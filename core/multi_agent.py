import os
import json
import hashlib
import asyncio
from typing import TypedDict, Dict, List, Protocol
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.aioredis import AsyncRedisSaver
import time
import hashlib
from redis.asyncio import Redis

# Create redis client
redis_client = Redis.from_url("redis://localhost:6379", decode_responses=True)


async def check_idempotency_key(data_props: dict, window_seconds: int = 3600) -> bool:
    # Genera una huella dactilar única utilizando una función hash sobre las propiedades de los datos y un timestamp de ventana temporal
    window_timestamp = int(time.time() / window_seconds)
    props_str = json.dumps(data_props, sort_keys=True)
    hash_input = f"{props_str}_{window_timestamp}".encode("utf-8")
    fingerprint = hashlib.sha256(hash_input).hexdigest()

    key = f"neo4j_idempotency:{fingerprint}"
    is_processed = await redis_client.get(key)
    if is_processed:
        return True

    await redis_client.setex(key, window_seconds, "1")
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
        completion = await self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            temperature=temperature,
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
        response = await self.model.generate_content_async(
            prompt,
            generation_config=genai.types.GenerationConfig(temperature=temperature),
        )
        return response.text


class CircuitBreakerRouter:
    def __init__(
        self, primary: LLMProvider, fallback: LLMProvider, timeout: float = 15.0
    ):
        self.primary = primary
        self.fallback = fallback
        self.timeout = timeout

    async def route_query(
        self, messages: List[Dict[str, str]], temperature: float = 0.7
    ) -> str:
        try:
            return await asyncio.wait_for(
                self.primary.generate(messages, temperature), timeout=self.timeout
            )
        except Exception as e:
            return await self.fallback.generate(messages, temperature)


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


def route_reasoning(state: AgentState) -> str:
    # Recursion is natively handled by LangGraph via recursion_limit.
    return "terminal_node"


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

    redis_connection = Redis.from_url("redis://localhost:6379")
    redis_saver = AsyncRedisSaver(redis_connection)
    app = workflow.compile(checkpointer=redis_saver)
    # The recursion_limit is set natively when invoking the graph
    # Example: app.invoke(state, config={"recursion_limit": 20})
    return app


app = build_graph()
