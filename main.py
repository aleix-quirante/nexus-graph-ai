import asyncio
import os
import json
from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import ValidationError
from database import Neo4jClient
from schemas import GraphExtraction

load_dotenv()

# Cliente apuntando a tu Ollama local (variables en .env o hardcoded localmente)
client = AsyncOpenAI(
    base_url=os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1"),
    api_key=os.getenv("OPENAI_API_KEY", "ollama-local"),
)


async def extract_graph(text: str) -> GraphExtraction:
    system_prompt = (
        "Eres un Arquitecto de Datos B2B. Extrae entidades y relaciones del texto.\n"
        "Debes responder ÚNICAMENTE con un JSON válido que coincida exactamente con este esquema:\n"
        f"{GraphExtraction.model_json_schema()}"
    )

    response = await client.chat.completions.create(
        model="qwen2.5:32b",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"Texto a analizar: {text}"},
        ],
        response_format={"type": "json_object"},
        temperature=0.0,
    )

    raw_json = response.choices[0].message.content
    try:
        # Validación estricta con Pydantic
        return GraphExtraction.model_validate_json(raw_json)
    except ValidationError as e:
        raise ValueError(
            f"Ollama devolvió un JSON malformado: {e}\nJSON crudo: {raw_json}"
        )


async def main():
    load_dotenv(override=True)

    uri = os.getenv("NEO4J_URI", "").strip()
    user = os.getenv("NEO4J_USER", "").strip()
    password = os.getenv("NEO4J_PASSWORD", "").strip()

    if not all([uri, user, password]):
        print("❌ ERROR: Faltan variables de entorno. Revisa el archivo .env")
        return

    db = Neo4jClient(uri, user, password)

    try:
        raw_text = "TechCorp firmó un contrato de 5M con CyberDyne el 20/03/2026. Riesgo detectado: cláusula de rescisión unilateral."
        print(f"🚀 Iniciando extracción agéntica DIRECTA en {uri}...")

        extraction = await extract_graph(raw_text)

        print(f"✅ Extracción completada: {len(extraction.nodes)} nodos detectados.")
        await db.add_graph_data(extraction)
        print("💎 Grafo inyectado en Neo4j Aura con éxito.")
    except Exception as e:
        print(f"❌ Error en el Pipeline: {str(e)}")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
