import asyncio
import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from database import Neo4jClient

load_dotenv()


class CypherResponse(BaseModel):
    query: str = Field(
        ...,
        description="Consulta Cypher válida de solo lectura (MATCH, RETURN). NUNCA usar MERGE o CREATE.",
    )
    explanation: str = Field(
        ..., description="Explicación ejecutiva de 1 línea de lo que hace la consulta."
    )


cypher_agent = Agent(
    "openai:qwen2.5:32b",
    output_type=CypherResponse,
    system_prompt=(
        "Eres un Arquitecto de Datos B2B experto en Neo4j. "
        "Traduce preguntas de negocio a consultas Cypher exactas. "
        "Usa SOLO este mapa de datos EXACTO:\n"
        "- Nodos:\n"
        "  * EMPRESA {id, nombre}\n"
        "  * CONTRATO {id, monto, fecha_firma}\n"
        "  * RIESGO {id, descripcion}\n"
        "- Relaciones:\n"
        "  * (EMPRESA)-[:FIRMO_CONTRATO]->(CONTRATO)\n"
        "  * (CONTRATO)-[:CONTIENE_RIESGO]->(RIESGO)\n"
        "Usa solo las etiquetas en MAYÚSCULAS y las propiedades listadas. No inventes esquemas ni uses n.properties, accede a los atributos directamente. "
        "Limítate a consultas de extracción de datos."
    ),
)


answer_agent = Agent(
    "openai:qwen2.5:32b",
    system_prompt=(
        "Eres un analista de datos B2B experto. "
        "Usa los datos JSON obtenidos de la base de datos para responder a la pregunta del usuario. "
        "Si los datos están vacíos, indica que no se encontró información relevante."
    ),
)


async def query_graph(user_question: str):
    client = Neo4jClient(
        os.getenv("NEO4J_URI"), os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")
    )
    try:
        print(f"🧠 Analizando intención corporativa: '{user_question}'")
        result = await cypher_agent.run(
            f"Pregunta del usuario: {user_question}. Genera el Cypher."
        )
        print(f"⚙️ Cypher Generado: {result.output.query}")
        print(f"📝 Razón: {result.output.explanation}")

        with client.driver.session() as session:
            records = session.run(result.output.query)
            data = records.data()
            print("\n📊 RESULTADOS DETERMINISTAS:")
            import json

            print(json.dumps(data, indent=2, ensure_ascii=False))

            print("\n🤖 SINTETIZANDO RESPUESTA FINAL...")
            final_response = await answer_agent.run(
                f"Pregunta del usuario: {user_question}\n\nDatos de la DB: {json.dumps(data, ensure_ascii=False)}"
            )
            print(f"\n✨ RESPUESTA:\n{final_response.output}")
    except Exception as e:
        print(f"❌ Error crítico en Retriever: {str(e)}")
        import traceback

        traceback.print_exc()
    finally:
        client.close()


if __name__ == "__main__":
    question = "¿Qué empresas firmaron el contrato y qué riesgo hay?"
    asyncio.run(query_graph(question))
