import sys
import asyncio
import os
import json
import glob
from dotenv import load_dotenv
from openai import AsyncOpenAI
from pydantic import ValidationError
import fitz  # PyMuPDF

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


def clean_pdf_text(text: str) -> str:
    # Remove weird line breaks but keep paragraph structure mostly
    # Replace multiple spaces or newlines
    lines = text.split("\n")
    cleaned_lines = [line.strip() for line in lines if line.strip()]
    return " ".join(cleaned_lines)


def get_files_to_process(path: str) -> list[str]:
    files = []
    if os.path.isfile(path):
        if path.lower().endswith((".txt", ".pdf")):
            files.append(path)
    elif os.path.isdir(path):
        for ext in ("*.txt", "*.pdf"):
            files.extend(glob.glob(os.path.join(path, f"**/{ext}"), recursive=True))
    return files


def extract_text_from_file(file_path: str) -> str:
    if file_path.lower().endswith(".pdf"):
        text = ""
        with fitz.open(file_path) as doc:
            for page in doc:
                text += page.get_text()
        return clean_pdf_text(text)
    else:
        with open(file_path, "r", encoding="utf-8") as f:
            return f.read().strip()


def chunk_text(text: str, max_words=2000) -> list[str]:
    words = text.split()
    chunks = []
    for i in range(0, len(words), max_words):
        chunks.append(" ".join(words[i : i + max_words]))
    return chunks


def process_extraction_results(extraction: GraphExtraction):
    id_map = {}
    for node in extraction.nodes:
        old_id = node.id
        raw_name = str(node.properties.get("nombre", old_id))
        clean_name = raw_name.replace("'", "").replace('"', "")
        new_id = clean_name
        id_map[old_id] = new_id

        node.id = new_id
        node.properties[PRIMARY_IDENTITY_PROPERTY] = new_id
        node.properties["nombre"] = new_id
        node.label = get_mapped_label(node.label)

    for rel in extraction.relationships:
        rel.type = get_standard_rel(rel.type)
        rel.source_id = (
            id_map.get(rel.source_id, rel.source_id).replace("'", "").replace('"', "")
        )
        rel.target_id = (
            id_map.get(rel.target_id, rel.target_id).replace("'", "").replace('"', "")
        )

    return extraction


async def process_file(file_path: str, db: Neo4jClient):
    print(f"Procesando [{os.path.basename(file_path)}]...")
    try:
        raw_text = extract_text_from_file(file_path)
        if not raw_text:
            print(
                f"⚠️ El archivo {os.path.basename(file_path)} está vacío o no se pudo extraer texto."
            )
            return

        chunks = chunk_text(raw_text, max_words=2000)
        total_nodes = 0

        for idx, chunk in enumerate(chunks):
            if len(chunks) > 1:
                print(f"  -> Procesando chunk {idx + 1}/{len(chunks)}...")

            extraction = await extract_graph(chunk)
            extraction = process_extraction_results(extraction)
            total_nodes += len(extraction.nodes)

            if len(extraction.nodes) > 0 or len(extraction.relationships) > 0:
                db.add_graph_data(extraction)

        print(
            f"Procesando [{os.path.basename(file_path)}]... [{total_nodes}] entidades extraídas"
        )

    except Exception as e:
        print(f"❌ Error procesando {os.path.basename(file_path)}: {str(e)}")


async def main():
    try:
        path = None
        if len(sys.argv) > 1:
            path = sys.argv[1]
        else:
            print("❌ ERROR: Se requiere proporcionar un archivo o carpeta.")
            print("Uso: python cli/ingest.py <archivo_o_carpeta>")
            return

        files_to_process = get_files_to_process(path)
        if not files_to_process:
            print(
                f"⚠️ No se encontraron archivos .txt o .pdf en la ruta especificada: {path}"
            )
            return

        print(
            f"🚀 Iniciando extracción agéntica DIRECTA en {len(files_to_process)} archivo(s)..."
        )

        load_dotenv(override=True)
        uri = os.getenv("NEO4J_URI", "").strip().replace('"', "").replace("'", "")
        user = os.getenv("NEO4J_USER", "").strip().replace('"', "").replace("'", "")
        password = (
            os.getenv("NEO4J_PASSWORD", "").strip().replace('"', "").replace("'", "")
        )

        if not all([uri, user, password]):
            print(
                "❌ ERROR: Faltan variables en el .env. Revísalo y guarda los cambios."
            )
            return

        db = Neo4jClient(uri, user, password)

        try:
            db.check_connection()
            for file_path in files_to_process:
                await process_file(file_path, db)
            print("💎 Grafo inyectado en Neo4j Aura con éxito.")
        finally:
            db.close()

    except Exception as e:
        print(f"❌ Error en el Pipeline: {str(e)}")


if __name__ == "__main__":
    asyncio.run(main())
