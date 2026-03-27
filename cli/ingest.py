import sys
import asyncio
import os
import json
from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import ValidationError
import sys
import os

# Ensure the root directory is in the path to import core correctly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.database import Neo4jClient
from schemas import GraphExtraction

load_dotenv(override=True)

# Cliente apuntando a tu Ollama local (variables en .env o hardcoded localmente)
client = AsyncOpenAI(
    base_url=os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1"),
    api_key=os.getenv("OPENAI_API_KEY", "ollama-local"),
)


async def extract_graph(text: str) -> GraphExtraction:
    system_prompt = (
        "Eres un Arquitecto de Datos B2B. Extrae entidades y relaciones del texto.\n"
        "Asegúrate de crear etiquetas nuevas como EMPLEADO, EQUIPO, LICENCIA si el texto lo requiere.\n"
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
    try:
        if len(sys.argv) > 1:
            with open(sys.argv[1], "r", encoding="utf-8") as f:
                raw_text = f.read()
        else:
            raw_text = "TechCorp firmó un contrato de 5M con CyberDyne el 20/03/2026. Riesgo detectado: cláusula de rescisión unilateral."
        print("🚀 Iniciando extracción agéntica DIRECTA...")

        extraction = await extract_graph(raw_text)

        print(f"✅ Extracción completada: {len(extraction.nodes)} nodos detectados.")

        # 1. Forzamos la recarga ignorando lo que haya en la memoria de la terminal
        load_dotenv(override=True)

        # 2. Capturamos y LIMPIAMOS (strip) cualquier espacio invisible
        uri = os.getenv("NEO4J_URI", "").strip().replace('"', "").replace("'", "")
        user = os.getenv("NEO4J_USER", "").strip().replace('"', "").replace("'", "")
        password = (
            os.getenv("NEO4J_PASSWORD", "").strip().replace('"', "").replace("'", "")
        )

        # 3. Validación de seguridad
        if not all([uri, user, password]):
            print(
                "❌ ERROR: Faltan variables en el .env. Revísalo y guarda los cambios."
            )
            return

        print(f"DEBUG: URI='{uri}' | USER='{user}' | PASS_LEN={len(password)}")
        print(
            f"DEBUG FINAL: Intentando inyectar en {uri} con pass de {len(password)} caracteres."
        )

        db = Neo4jClient(uri, user, password)

        try:
            db.check_connection()
            db.add_graph_data(extraction)
            print("💎 Grafo inyectado en Neo4j Aura con éxito.")
        finally:
            db.close()
    except Exception as e:
        print(f"❌ Error en el Pipeline: {str(e)}")


if __name__ == "__main__":
    asyncio.run(main())
