import asyncio
from typing import Optional, Literal, Dict, Any, List
from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
import re

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
        description="Historial de los pasos de razonamiento tomados para llegar a la respuesta.",
        max_length=10,  # Limitar número de pasos de razonamiento (OWASP LLM04:2025 DoS prevention)
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
        "IMPORTANTE: No superes el límite de 10 pasos de razonamiento bajo ninguna circunstancia."
    ),
)

# --- Orquestador del Sistema ---


class MultiAgentSystem:
    """Clase principal que coordina el flujo de los agentes con enfoque Zero-Trust."""

    MAX_QUERY_LENGTH = 1000  # Prevenir agotamiento de recursos o exploits largos

    def sanitize_input(self, user_query: str) -> str:
        """
        Input Sanitization: Prevenir secuestro de prompts, limpiar caracteres invisibles,
        limitar longitud y prevenir DoS (LLM04).
        """
        if not user_query or not isinstance(user_query, str):
            raise ValueError("Invalid query format.")

        # Limitar tamaño de entrada
        if len(user_query) > self.MAX_QUERY_LENGTH:
            raise ValueError(
                f"Query exceeds maximum allowed length of {self.MAX_QUERY_LENGTH} characters."
            )

        # Limpiar caracteres de control o inusuales (básica sanitización)
        sanitized = re.sub(r"[\x00-\x1F\x7F]", "", user_query)
        return sanitized

    async def process_query(self, user_query: str) -> Dict[str, Any]:
        """
        Punto de entrada asíncrono. Evalúa la consulta y la delega al agente correspondiente.
        """
        print(f"\n[Sistema] Analizando consulta original...")

        try:
            # 0. Zero-Trust: Input Sanitization
            safe_query = self.sanitize_input(user_query)
        except ValueError as e:
            return {"status": "error", "message": str(e)}

        # Envolvemos el input del usuario en delimitadores seguros para Context Validation y prevención de Prompt Injection
        secure_prompt = (
            f"--- USER INPUT BEGIN ---\n{safe_query}\n--- USER INPUT END ---"
        )

        # 1. Enrutamiento (Baja latencia y coste)
        # Ejecutamos de forma asíncrona usando Pydantic-AI
        route_result = await router_agent.run(secure_prompt)
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
            # Enriquecemos el contexto con las entidades extraídas por el router y mantenemos los delimitadores seguros
            enriched_prompt = (
                f"Entidades identificadas: {', '.join(decision.extracted_entities)}\n"
                f"Consulta del usuario para generar Cypher:\n"
                f"--- USER INPUT BEGIN ---\n{safe_query}\n--- USER INPUT END ---"
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
            # Pasamos la consulta con delimitadores seguros al agente de razonamiento
            reasoning_result = await reasoning_specialist.run(secure_prompt)
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
