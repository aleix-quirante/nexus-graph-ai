import asyncio
from typing import Optional, Literal, Dict, Any, List
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext

# Nota: En un entorno real, configuraríamos los modelos usando variables de entorno o configuración.
# Para este ejemplo, utilizamos identificadores de modelos de OpenAI.
# Optimizamos el coste y la latencia usando un modelo más rápido/barato para tareas sencillas.

# --- Modelos de Datos (Pydantic Schemas) ---


class RouteDecision(BaseModel):
    """Decisión estructurada tomada por el Agente Enrutador."""

    complexity: Literal["trivial", "cypher_read", "complex_reasoning"] = Field(
        description="La complejidad evaluada de la consulta."
    )
    reasoning: str = Field(
        description="Breve justificación de la decisión de enrutamiento."
    )
    extracted_entities: List[str] = Field(
        default_factory=list,
        description="Entidades clave extraídas de la consulta para asistir a los agentes especializados.",
    )


class CypherQuery(BaseModel):
    """Salida estructurada del Especialista en Cypher."""

    query: str = Field(description="La consulta Cypher generada para Neo4j.")
    explanation: str = Field(
        description="Explicación detallada de lo que hace la consulta y por qué se estructuró así."
    )


class ReasoningStep(BaseModel):
    """Un paso individual dentro del proceso de razonamiento complejo."""

    step_number: int
    hypothesis: str = Field(description="Hipótesis o idea evaluada en este paso.")
    action_required: Literal["search_db", "ask_user", "synthesize", "conclude"] = Field(
        description="La acción que este paso requiere para avanzar."
    )
    partial_conclusion: Optional[str] = Field(
        default=None, description="Conclusión parcial derivada de este paso."
    )


class ComplexReasoningResult(BaseModel):
    """Resultado final del Especialista en Razonamiento Iterativo."""

    steps_taken: List[ReasoningStep] = Field(
        description="Historial de los pasos de razonamiento tomados para llegar a la respuesta."
    )
    final_answer: str = Field(
        description="La respuesta final sintetizada para el usuario."
    )


# --- Definición de Agentes ---

# 1. Agente Enrutador (Router Agent)
# Utiliza un modelo rápido (ej. gpt-4o-mini) para minimizar latencia y coste.
router_agent = Agent(
    "openai:gpt-4o-mini",
    result_type=RouteDecision,
    system_prompt=(
        "Eres un enrutador inteligente para un sistema de base de datos de grafos basado en IA. "
        "Tu objetivo es analizar la consulta del usuario, extraer entidades clave y determinar la complejidad "
        "para derivarla al especialista adecuado.\n\n"
        "Categorías:\n"
        "- 'trivial': Saludos, preguntas genéricas o fuera del dominio que no requieren consultar la base de datos.\n"
        "- 'cypher_read': Preguntas directas sobre datos que pueden responderse generando y ejecutando una consulta Cypher de lectura (MATCH).\n"
        "- 'complex_reasoning': Preguntas ambiguas, analíticas, comparativas o de múltiples pasos que requieren evaluación iterativa y razonamiento profundo."
    ),
)

# 2. Agente Especialista en Cypher
# Modelo rápido/intermedio especializado en sintaxis de grafos.
cypher_specialist = Agent(
    "openai:gpt-4o-mini",
    result_type=CypherQuery,
    system_prompt=(
        "Eres un ingeniero experto en bases de datos de grafos Neo4j y lenguaje Cypher. "
        "Tu tarea es convertir requerimientos en lenguaje natural en consultas Cypher precisas y optimizadas. "
        "Genera ÚNICAMENTE consultas de lectura (MATCH, RETURN, WITH, WHERE). "
        "Asegúrate de que la sintaxis sea correcta y de explicar brevemente la lógica de tu consulta."
    ),
)

# 3. Agente Especialista en Razonamiento Iterativo
# Utiliza un modelo más potente (ej. gpt-4o) para manejar la ambigüedad y el análisis profundo.
reasoning_specialist = Agent(
    "openai:gpt-4o",
    result_type=ComplexReasoningResult,
    system_prompt=(
        "Eres un analista de datos avanzado y agente de razonamiento iterativo. "
        "Resuelves problemas complejos y ambiguos dividiéndolos en pasos lógicos. "
        "Para cada problema, debes formular hipótesis, determinar las acciones necesarias (como consultar la BD o sintetizar información) "
        "y finalmente proporcionar una respuesta completa y fundamentada. Tu salida debe reflejar estrictamente cada paso de tu proceso cognitivo."
    ),
)

# --- Orquestador del Sistema ---


class MultiAgentSystem:
    """Clase principal que coordina el flujo de los agentes."""

    async def process_query(self, user_query: str) -> Dict[str, Any]:
        """
        Punto de entrada asíncrono. Evalúa la consulta y la delega al agente correspondiente.
        """
        print(f"\n[Sistema] Analizando consulta: '{user_query}'")

        # 1. Enrutamiento (Baja latencia y coste)
        # Ejecutamos de forma asíncrona usando Pydantic-AI
        route_result = await router_agent.run(user_query)
        decision: RouteDecision = route_result.data

        print(
            f"[Router] Decisión: {decision.complexity.upper()} | Entidades: {decision.extracted_entities}"
        )
        print(f"[Router] Razonamiento: {decision.reasoning}")

        # 2. Delegación al Especialista
        if decision.complexity == "trivial":
            # Resolución inmediata, sin coste adicional de modelos pesados
            return {
                "status": "success",
                "specialist": "none",
                "response": "Esta es una consulta trivial. Soy un asistente de IA especializado en análisis de grafos. ¿En qué puedo ayudarte con los datos?",
            }

        elif decision.complexity == "cypher_read":
            print("[Sistema] Delegando al Especialista en Cypher...")
            # Enriquecemos el contexto con las entidades extraídas por el router
            enriched_prompt = (
                f"Entidades identificadas: {', '.join(decision.extracted_entities)}\n"
                f"Consulta del usuario: {user_query}"
            )
            cypher_result = await cypher_specialist.run(enriched_prompt)
            cypher_data: CypherQuery = cypher_result.data
            return {
                "status": "success",
                "specialist": "cypher",
                "query": cypher_data.query,
                "explanation": cypher_data.explanation,
            }

        elif decision.complexity == "complex_reasoning":
            print(
                "[Sistema] Delegando al Especialista en Razonamiento Iterativo (Modelo Pesado)..."
            )
            reasoning_result = await reasoning_specialist.run(user_query)
            reasoning_data: ComplexReasoningResult = reasoning_result.data
            return {
                "status": "success",
                "specialist": "reasoning",
                "steps": [step.model_dump() for step in reasoning_data.steps_taken],
                "final_answer": reasoning_data.final_answer,
            }


# --- Ejecución de Prueba ---


async def main():
    system = MultiAgentSystem()

    # Batería de pruebas demostrando la optimización y enrutamiento
    test_queries = [
        "Hola, buenas tardes.",
        "¿Cuáles son los nombres y correos de todos los empleados en el departamento de 'Ventas'?",
        "Considerando el rendimiento del último trimestre y la estructura jerárquica, ¿qué departamento tiene mayor riesgo de cuello de botella y por qué?",
    ]

    for q in test_queries:
        print("-" * 60)
        try:
            # Descomentar la siguiente línea para ejecutar contra una API real con Pydantic-AI
            # response = await system.process_query(q)
            # print(f"Resultado final:\n{response}")
            pass
        except Exception as e:
            print(
                f"Error durante la ejecución (requiere API KEY de OpenAI válida): {e}"
            )


if __name__ == "__main__":
    asyncio.run(main())
