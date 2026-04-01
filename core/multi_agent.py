from typing import TypedDict, Annotated, Any, Dict, List
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from core.security_guardrails import SecurityEnforcer, SecurityGuardrailViolation
from openai import AsyncOpenAI
import hashlib
import json

# Cliente de OpenAI configurado para apuntar a tu Ollama local
# Así no tienes que instalar librerías nuevas, usamos la que ya tienes.
llm_client = AsyncOpenAI(base_url="http://localhost:11434/v1", api_key="ollama")


class ContextEntry(TypedDict):
    content: str
    role: str
    signature: str


class AgentState(TypedDict):
    """
    Estado del grafo que incluye el budget de razonamiento.
    """

    query: str
    response: str
    step_count: int
    history: List[ContextEntry]


def validate_and_hash_context(role: str, content: str) -> str:
    """Genera una firma criptográfica para el contexto para evitar envenenamiento."""
    context_data = json.dumps(
        {"role": role, "content": content}, sort_keys=True
    ).encode("utf-8")
    return hashlib.sha256(context_data).hexdigest()


class DataConsistencyError(Exception):
    """Exception raised when history context hashing validation fails."""

    pass


async def reasoning_agent(state: AgentState) -> Dict[str, Any]:
    """
    Agente de razonamiento conectado a Qwen 3 30B en Ollama local.
    """
    current_step = state.get("step_count", 0) + 1

    if current_step > 3:
        # Salida forzada temprana para prevenir agotamiento de tokens.
        return {
            "step_count": current_step,
            "response": "Límite de razonamiento excedido",
        }

    history = state.get("history", [])

    # Validación de integridad del historial
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

    # Llamada real al LLM local (Ollama con Qwen 3 30B)
    try:
        messages = [
            {"role": "system", "content": "Eres un asistente experto y conciso."}
        ] + valid_messages
        completion = await llm_client.chat.completions.create(
            model="qwen3:30b",
            messages=messages,
            temperature=0.7,
        )
        respuesta_real = completion.choices[0].message.content

        response_signature = validate_and_hash_context("assistant", respuesta_real)
        history.append(
            {
                "role": "assistant",
                "content": respuesta_real,
                "signature": response_signature,
            }
        )

    except Exception as e:
        respuesta_real = f"Error conectando con Ollama: {str(e)}. ¿Está encendido?"

    return {"step_count": current_step, "response": respuesta_real, "history": history}


def route_reasoning(state: AgentState) -> str:
    """
    Enrutador. Como Ollama ya dio respuesta, vamos directo a la salida.
    """
    # Límite de seguridad
    if state.get("step_count", 0) > 3:
        return "terminal_node"

    # Como es un chat simple, terminamos el ciclo y vamos a seguridad
    return "terminal_node"


async def terminal_node(state: AgentState) -> Dict[str, Any]:
    """
    Nodo terminal que obliga la ejecución de SecurityEnforcer.
    """
    response_to_validate = state.get("response", "")

    # Si la respuesta es el límite excedido, se emite tal cual.
    if response_to_validate == "Límite de razonamiento excedido":
        return {"response": response_to_validate}

    enforcer = SecurityEnforcer()
    try:
        validated_output = await enforcer.validate_llm_output(response_to_validate)
        return {"response": validated_output}
    except SecurityGuardrailViolation as e:
        return {"response": f"Bloqueado por seguridad: {str(e)}"}


def build_graph() -> Any:
    """
    Compila el StateGraph con MemorySaver.
    """
    workflow = StateGraph(AgentState)

    workflow.add_node("reasoning_agent", reasoning_agent)
    workflow.add_node("terminal_node", terminal_node)

    workflow.add_edge(START, "reasoning_agent")
    workflow.add_conditional_edges("reasoning_agent", route_reasoning)
    workflow.add_edge("terminal_node", END)

    memory_saver = MemorySaver()
    app = workflow.compile(checkpointer=memory_saver)
    return app


# Exponer la aplicación compilada
app = build_graph()
