import os
import json
import traceback
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from core.database import Neo4jClient


class CypherResponse(BaseModel):
    query: str = Field(
        ...,
        description="Consulta Cypher válida de solo lectura (MATCH, RETURN). NUNCA usar MERGE o CREATE.",
    )
    explanation: str = Field(
        ..., description="Explicación ejecutiva de 1 línea de lo que hace la consulta."
    )


class GraphQueryEngine:
    def __init__(self):
        load_dotenv(override=True)
        self.client = Neo4jClient(
            os.getenv("NEO4J_URI", ""),
            os.getenv("NEO4J_USER", ""),
            os.getenv("NEO4J_PASSWORD", ""),
        )
        self.answer_agent = Agent(
            "openai:qwen2.5:32b",
            system_prompt=(
                "Eres un analista de datos B2B experto. "
                "Usa los datos JSON obtenidos de la base de datos para responder a la pregunta del usuario. "
                "Si los datos están vacíos, indica que no se encontró información relevante. "
                "SIEMPRE debes responder en el mismo idioma en el que se te hace la pregunta."
            ),
        )

    async def query(self, user_question: str):
        try:
            schema = self.client.get_schema_snapshot()

            cypher_agent = Agent(
                "openai:qwen2.5:32b",
                output_type=CypherResponse,
                system_prompt=(
                    "Eres un experto en Cypher. El esquema actual de la base de datos es:\n"
                    f"Nodos detectados: {schema['labels']}\n"
                    f"Relaciones detectadas: {schema['relationships']}\n"
                    f"Propiedades disponibles: {schema['properties']}\n"
                    "Genera la consulta basada estrictamente en este esquema. Usa solo estas etiquetas en MAYÚSCULAS."
                ),
            )

            print(f"🧠 Analizando intención corporativa: '{user_question}'")
            result = await cypher_agent.run(
                f"Pregunta del usuario: {user_question}. Genera el Cypher."
            )
            # Support both .data and .output based on pydantic-ai version
            cypher_data = getattr(result, "data", getattr(result, "output", None))

            if not cypher_data:
                print("❌ No se pudo extraer la consulta Cypher.")
                return

            print(f"⚙️ Cypher Generado: {cypher_data.query}")
            print(f"📝 Razón: {cypher_data.explanation}")

            with self.client.driver.session() as session:
                records = session.run(cypher_data.query)
                data = records.data()
                print("\n📊 RESULTADOS DETERMINISTAS:")
                print(json.dumps(data, indent=2, ensure_ascii=False))

                print("\n🤖 SINTETIZANDO RESPUESTA FINAL...")
                final_response = await self.answer_agent.run(
                    f"Pregunta del usuario: {user_question}\n\nDatos de la DB: {json.dumps(data, ensure_ascii=False)}"
                )

                answer_data = getattr(
                    final_response, "data", getattr(final_response, "output", "")
                )
                print(f"\n✨ RESPUESTA:\n{answer_data}")
                return answer_data
        except Exception as e:
            print(f"❌ Error crítico en Engine: {str(e)}")
            traceback.print_exc()
            return f"Error: {str(e)}"

    def close(self):
        self.client.close()
