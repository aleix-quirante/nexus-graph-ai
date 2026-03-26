import asyncio
import os
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from database import Neo4jClient

load_dotenv()

local_model = OpenAIModel(
    "qwen2.5:32b", base_url="http://localhost:11434/v1", api_key="ollama"
)


class CypherResponse(BaseModel):
    query: str = Field(
        ...,
        description="Consulta Cypher válida de solo lectura (MATCH, RETURN). NUNCA usar MERGE o CREATE.",
    )
    explanation: str = Field(
        ..., description="Explicación ejecutiva de 1 línea de lo que hace la consulta."
    )


cypher_agent = Agent(
    local_model,
    result_type=CypherResponse,
    system_prompt=(
        "Eres un Arquitecto de Datos B2B experto en Neo4j. "
        "Traduce preguntas de negocio a consultas Cypher exactas. "
        "Nuestro grafo tiene nodos con atributos (id, label, properties) y relaciones con atributos (type, properties). "
        "Limítate a consultas de extracción de datos."
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
        print(f"⚙️ Cypher Generado: {result.data.query}")
        print(f"📝 Razón: {result.data.explanation}")

        async with client.driver.session() as session:
            records = await session.run(result.data.query)
            data = await records.data()
            print("\n📊 RESULTADOS DETERMINISTAS:")
            import json

            print(json.dumps(data, indent=2, ensure_ascii=False))
    except Exception as e:
        print(f"❌ Error crítico en Retriever: {str(e)}")
    finally:
        await client.close()


if __name__ == "__main__":
    question = "¿Qué riesgos están asociados al contrato con CyberDyne?"
    asyncio.run(query_graph(question))
