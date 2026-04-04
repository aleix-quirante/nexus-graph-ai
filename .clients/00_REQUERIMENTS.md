# MISSION: Fase 1 - Cirugía de Vulnerabilidades Críticas

## Objetivo
He leído el archivo `CURRENT_STATE.md`. Antes de construir la parte vectorial de GraphRAG, debemos estabilizar los cimientos. Tu objetivo es arreglar las 5 vulnerabilidades CRÍTICAS listadas en la Sección B del reporte.

## Restricciones
- NO toques nada de los componentes ausentes (Vector Embeddings, Traversal). Eso lo haremos en la Fase 2.
- Aplica STRICT MODE en todos los modelos de Pydantic (`extra="forbid"`, tipado explícito).
- Arregla la configuración de credenciales (`neo4j_password`).
- Arregla la validación de la versión de Pydantic en `pyproject.toml`.
- Añade el Circuit Breaker al SLM Guard (Fail-Closed agresivo).
- Añade Idempotency Keys en el Ingestion Worker.

## Entrega
Genera un archivo `PLAN.md` con los pasos exactos y casillas `[ ]` para auditar y modificar los archivos correspondientes a estos 5 problemas.