import asyncio
import os
from dotenv import load_dotenv
from database import Neo4jClient
from pydantic_ai import Agent
from pydantic_ai.models.openai import OpenAIModel
from schemas import GraphExtraction

load_dotenv()

local_model = OpenAIModel(
    "qwen2.5:32b", base_url="http://localhost:11434/v1", api_key="ollama"
)

extractor_agent = Agent[GraphExtraction](
    local_model,
    system_prompt=(
        "Eres un arquitecto de datos especializado en Análisis de Riesgos Corporativos. "
        "Transforma el texto legal en un Grafo de Conocimiento determinista. "
        "Asegúrate de que los 'source_id' y 'target_id' de las relaciones apunten exactamente a los 'id' de los nodos creados."
    ),
)


async def main():
    client = Neo4jClient(
        os.getenv("NEO4J_URI"), os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")
    )

    try:
        raw_text = "TechCorp firmó un contrato de 5M con CyberDyne el 20/03/2026. Riesgo detectado: cláusula de rescisión unilateral."

        print("🚀 Iniciando extracción agéntica...")
        result = await extractor_agent.run(raw_text)

        print(
            f"✅ Extracción completada: {len(result.data.nodes)} nodos, {len(result.data.relationships)} relaciones."
        )

        await client.add_graph_data(result.data)
        print("💎 Grafo inyectado en Neo4j Aura con éxito.")

    except Exception as e:
        print(f"❌ Error en el Pipeline: {str(e)}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
