from typing import TypedDict, Annotated, Any, Dict
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.memory import MemorySaver
from core.security_guardrails import SecurityEnforcer, SecurityGuardrailViolation


class AgentState(TypedDict):
    """
    Estado del grafo que incluye el budget de razonamiento.
    """

    query: str
    response: str
    step_count: int


async def reasoning_agent(state: AgentState) -> Dict[str, Any]:
    """
    Agente de razonamiento con patrón Depth Budget.
    """
    current_step = state.get("step_count", 0) + 1

    if current_step > 3:
        # Salida forzada temprana para prevenir agotamiento de tokens.
        return {
            "step_count": current_step,
            "response": "Límite de razonamiento excedido",
        }

    # Simulación de la lógica de razonamiento del LLM
    simulated_response = (
        f"Respuesta generada en el paso {current_step} para: {state.get('query', '')}"
    )

    return {"step_count": current_step, "response": simulated_response}


def route_reasoning(state: AgentState) -> str:
    """
    Enrutador para simular ciclos o finalizar.
    """
    if state.get("step_count", 0) > 3:
        return "terminal_node"

    # Lógica de ejemplo para forzar ciclos y probar el budget
    if "ciclo" in state.get("query", "").lower():
        return "reasoning_agent"

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
