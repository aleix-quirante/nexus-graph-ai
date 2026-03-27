import sys
import asyncio
import os
import json
from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import ValidationError

# Ensure the root directory is in the path to import core correctly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.database import Neo4jClient
from core.schema_map import (
    get_mapped_label,
    PRIMARY_IDENTITY_PROPERTY,
    SCHEMA_MAP,
    get_standard_rel,
)
from schemas import GraphExtraction

load_dotenv(override=True)

# Cliente apuntando a tu Ollama local (variables en .env o hardcoded localmente)
client = AsyncOpenAI(
    base_url=os.getenv("OPENAI_BASE_URL", "http://localhost:11434/v1"),
    api_key=os.getenv("OPENAI_API_KEY", "ollama-local"),
)


async def extract_graph(text: str) -> GraphExtraction:
    valid_labels = ", ".join(list(SCHEMA_MAP["labels"].keys()))
    valid_rels = ", ".join(list(SCHEMA_MAP["relationships"].keys()))

    system_prompt = (
        "Eres un Arquitecto de Datos B2B. Extrae entidades y relaciones del texto.\n"
        "Extrae de forma agresiva: Personas, Empresas, Pedidos, Productos, Riesgos y Montos. Si ves un nombre propio, es un nodo. Si ves una cifra de dinero (presupuesto, coste, etc.), métela obligatoriamente como propiedad (ej. 'monto') dentro del nodo del PEDIDO o PROYECTO correspondiente.\n"
        "PROHIBIDO usar etiquetas de una sola letra como 'e'.\n"
        f"Obligatoriamente usa etiquetas completas y descriptivas basadas en este esquema de nodos: {valid_labels}.\n"
        f"Obligatoriamente usa tipos de relaciones basados en este esquema de relaciones: {valid_rels}.\n"
        "Si el texto menciona términos como 'empresa', 'cliente', 'proveedor', mapealos a 'EMPRESA'.\n"
        "Si menciona 'pedido', 'vigas', 'material', mapealos a 'PEDIDO'.\n"
        "Asegúrate de crear etiquetas nuevas como EMPLEADO, EQUIPO, LICENCIA si el texto lo requiere, pero prioriza el esquema proporcionado.\n"
        "Asegúrate de mapear las relaciones a los tipos estándar permitidos.\n"
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
        # Extract json between { and }
        start_idx = raw_json.find("{")
        end_idx = raw_json.rfind("}")
        if start_idx != -1 and end_idx != -1 and end_idx >= start_idx:
            raw_json = raw_json[start_idx : end_idx + 1]

        # Validación estricta con Pydantic
        return GraphExtraction.model_validate_json(raw_json)
    except ValidationError as e:
        raise ValueError(
            f"Ollama devolvió un JSON malformado: {e}\nJSON crudo: {raw_json}"
        )


async def main():
    try:
        if len(sys.argv) > 1:
            file_path = sys.argv[1]
            with open(file_path, "r", encoding="utf-8") as f:
                raw_text = f.read().strip()

            if not raw_text:
                raise ValueError("El archivo está vacío o solo contiene espacios.")
        else:
            raw_text = "TechCorp firmó un contrato de 5M con CyberDyne el 20/03/2026. Riesgo detectado: cláusula de rescisión unilateral."

        print(f"Texto a procesar:\n{raw_text}\n")
        print("🚀 Iniciando extracción agéntica DIRECTA...")

        extraction = await extract_graph(raw_text)

        print(
            f"✅ Extracción completada: {len(extraction.nodes)} nodos detectados originales."
        )

        # Limpieza e integración con schema_map
        id_map = {}
        for node in extraction.nodes:
            old_id = node.id

            # Obtener el nombre, priorizando la propiedad 'nombre' o usando el id
            raw_name = str(node.properties.get("nombre", old_id))

            # Limpiar comillas simples o dobles
            clean_name = raw_name.replace("'", "").replace('"', "")

            # El valor del nombre se guarda SIEMPRE en la propiedad id (PRIMARY_IDENTITY_PROPERTY)
            # y, por redundancia, también en nombre
            new_id = clean_name
            id_map[old_id] = new_id

            node.id = new_id
            node.properties[PRIMARY_IDENTITY_PROPERTY] = new_id
            node.properties["nombre"] = new_id

            # Mapear a la etiqueta correcta
            node.label = get_mapped_label(node.label)

        for rel in extraction.relationships:
            # Mapear a la relación correcta
            rel.type = get_standard_rel(rel.type)

            # Actualizar IDs en relaciones y limpiar comillas
            rel.source_id = (
                id_map.get(rel.source_id, rel.source_id)
                .replace("'", "")
                .replace('"', "")
            )
            rel.target_id = (
                id_map.get(rel.target_id, rel.target_id)
                .replace("'", "")
                .replace('"', "")
            )

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
