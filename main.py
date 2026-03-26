import asyncio
import os
from dotenv import load_dotenv
from database import Neo4jClient
from pydantic_ai import Agent

# Asumimos que creamos este archivo para los modelos de datos
from schemas import GraphExtraction

load_dotenv()

# 1. Definición del Agente Extractor (El "Cerebro")
# En 2026, este agente es el que factura los $5,000
extractor_agent = Agent(
    "google-gla:gemini-3.1-flash",
    result_type=GraphExtraction,
    system_prompt=(
        "Eres un experto en Análisis de Riesgos Corporativos. "
        "Tu misión es transformar texto legal en un Grafo de Conocimiento. "
        "Identifica EMPRESAS, CONTRATOS y RIESGOS. Define relaciones claras."
    ),
)


async def main():
    client = Neo4jClient(
        os.getenv("NEO4J_URI"), os.getenv("NEO4J_USER"), os.getenv("NEO4J_PASSWORD")
    )

    try:
        # SIMULACIÓN DE DATA REAL (Aquí podrías leer un PDF)
        raw_text = "TechCorp firmó un contrato de 5M con CyberDyne el 20/03/2026. Riesgo detectado: cláusula de rescisión unilateral."

        print("🚀 Iniciando extracción agéntica...")
        # El agente razona y devuelve un objeto validado por Pydantic
        result = await extractor_agent.run(raw_text)

        print(f"✅ Extracción completada: {len(result.data.nodes)} nodos detectados.")

        # Inserción real en Neo4j Aura
        await client.add_graph_data(result.data)
        print("💎 Grafo actualizado en la nube con éxito.")

    except Exception as e:
        print(f"❌ Error en el Pipeline: {str(e)}")
    finally:
        await client.close()


if __name__ == "__main__":
    asyncio.run(main())
