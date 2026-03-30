import os
from typing import Optional

from fastapi import FastAPI, HTTPException, UploadFile, File, Form
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from core.engine import GraphQueryEngine
from cli.ingest import extract_graph
from core.database import Neo4jClient
from core.schema_map import (
    get_mapped_label,
    PRIMARY_IDENTITY_PROPERTY,
    get_standard_rel,
)

app = FastAPI(
    title="NexusGraph API",
    description="API profesional para extracción y consulta de grafos de conocimiento",
    version="1.0.0",
)

# CORS configuration
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Adjust this in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class QueryRequest(BaseModel):
    question: str


class QueryResponse(BaseModel):
    answer: str


@app.post("/ingest")
async def ingest_data(
    text: Optional[str] = Form(None), file: Optional[UploadFile] = File(None)
):
    """
    Recibe un texto o un archivo y lanza el proceso de extracción a Neo4j.
    """
    if not text and not file:
        raise HTTPException(status_code=400, detail="Debe proporcionar 'text' o 'file'")

    content = ""
    if file:
        try:
            content_bytes = await file.read()
            content = content_bytes.decode("utf-8")
        except Exception as e:
            raise HTTPException(
                status_code=400, detail=f"Error leyendo el archivo: {str(e)}"
            )
    elif text:
        content = text

    if not content.strip():
        raise HTTPException(status_code=400, detail="El contenido provisto está vacío")

    try:
        print(f"🚀 Iniciando extracción agéntica DIRECTA vía API...")
        extraction = await extract_graph(content)
        print(
            f"✅ Extracción completada: {len(extraction.nodes)} nodos detectados originales."
        )

        # Limpieza e integración con schema_map
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
                id_map.get(rel.source_id, rel.source_id)
                .replace("'", "")
                .replace('"', "")
            )
            rel.target_id = (
                id_map.get(rel.target_id, rel.target_id)
                .replace("'", "")
                .replace('"', "")
            )

        uri = os.getenv("NEO4J_URI", "").strip().replace('"', "").replace("'", "")
        user = os.getenv("NEO4J_USER", "").strip().replace('"', "").replace("'", "")
        password = (
            os.getenv("NEO4J_PASSWORD", "").strip().replace('"', "").replace("'", "")
        )

        if not all([uri, user, password]):
            raise HTTPException(
                status_code=500,
                detail="Faltan credenciales de base de datos en el entorno.",
            )

        db = Neo4jClient(uri, user, password)
        try:
            db.check_connection()
            db.add_graph_data(extraction)
            return {
                "status": "success",
                "message": "Grafo inyectado en Neo4j con éxito.",
                "nodes_extracted": len(extraction.nodes),
            }
        finally:
            db.close()

    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error en el proceso de ingesta: {str(e)}"
        )


@app.post("/query", response_model=QueryResponse)
async def query_graph(request: QueryRequest):
    """
    Recibe una pregunta, usa 'GraphQueryEngine' y devuelve la respuesta del LLM en JSON.
    """
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="La pregunta no puede estar vacía")

    engine = GraphQueryEngine()
    try:
        answer = await engine.query(request.question)
        if not answer:
            answer = "No se pudo generar una respuesta basada en los datos actuales."
        return {"answer": answer}
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Error consultando el grafo: {str(e)}"
        )
    finally:
        engine.close()


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("api:app", host="0.0.0.0", port=8000, reload=True)
