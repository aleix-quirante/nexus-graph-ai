# Nexus Graph AI 🌌

![Version](https://img.shields.io/badge/versión-3.0.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/licencia-MIT-green)

Nexus Graph AI es una plataforma de vanguardia que combina Bases de Datos Orientadas a Grafos e Inteligencia Artificial para proporcionar conocimiento relacional profundo y capacidades inteligentes de consulta de datos. Construido bajo los estándares de la **Arquitectura de Referencia Empresa 2026** y aplicando el patrón de diseño **Dynamic Schema-First Graph Extraction** con **Inyección de Dependencias**.

## 🏗️ Arquitectura de Referencia

Nuestra arquitectura está diseñada para ofrecer escalabilidad extrema, modularidad y procesamiento enfocado en IA. Recientemente, el proyecto ha evolucionado para incluir streaming de eventos, observabilidad avanzada, una capa de API robusta, control de concurrencia avanzado y enrutamiento inteligente:

- **Repository Pattern & DI**: Desacoplamiento de la base de datos mediante el protocolo abstracto `GraphRepository` (implementado en `Neo4jRepository`). Las dependencias se inyectan en tiempo de ejecución, facilitando el testing aislado.
- **Ontología Dinámica y Auto-Recovery**: Validación estricta de grafos utilizando Pydantic. Si el LLM genera estructuras inválidas, un bucle automático de recuperación (`max_retries`) solicita auto-corrección.
- **Campos de Validez Temporal en la Ontología**: Soporte añadido para esquemas de ontología con campos de validez temporal (`valid_from`, `valid_until`), permitiendo la evolución histórica y seguimiento de datos en el tiempo en el modelo de conocimiento.
- **Enrutamiento de Inferencia y Extracción (LangGraph)**: Integración profunda de **LangGraph** para orquestar y enrutar inteligentemente el flujo de extracción de entidades y relaciones, además de dirigir consultas de inferencia hacia agentes especializados, mejorando la modularidad y gestión de estado.
- **Control de Concurrencia Distribuida (Redis)**: Implementación de un `OntologyLockManager` respaldado por **Redis** para prevenir condiciones de carrera y asegurar operaciones thread-safe durante la actualización concurrente del esquema de la ontología y el grafo.
- **Event-Driven Ingestion (Redpanda)**: El pipeline de ingesta soporta particionado de documentos asíncrono y encolamiento a través de un productor de Redpanda, permitiendo procesar grandes volúmenes de texto de manera distribuida.
- **Observabilidad Integral (Arize Phoenix)**: Instrumentación completa con **OpenTelemetry** y **OpenInference**. Trazas detalladas de llamadas a la API, workers de procesamiento y peticiones al LLM son enviadas a una instancia local de Arize Phoenix.
- **API REST & MCP Scaffolding**: Un servidor **FastAPI** expone el core funcional conectándose a Neo4j mediante inyección de dependencias.

## 📂 Estructura del Proyecto

```text
nexus-graph-ai/
├── api/                # Capa de servicios REST y MCP
│   ├── main.py         # Servidor FastAPI
│   └── mcp.py          # Definición de herramientas MCP
├── core/               # Motor principal y dominio
│   ├── database.py     # Implementación del GraphRepository
│   ├── engine.py       # Lógica Multi-Agente
│   ├── observability.py# OpenTelemetry y Arize Phoenix
│   ├── ontology.py     # Ontología Dinámica (Validez Temporal) y OntologyLockManager
│   ├── router.py       # Enrutamiento de LangGraph
│   └── schema_map.py   # Diccionario central de mapeo
├── cli/                # Comandos ejecutables
│   ├── ingest.py       # Productor de Redpanda
│   └── ask.py          # CLI para consultas
├── tests/              # Pruebas automatizadas (Pytest)
│   ├── test_router.py      # Suite de pruebas para el enrutador LangGraph
│   ├── test_concurrency.py # Suite de pruebas para OntologyLockManager y concurrencia
│   ├── test_api.py         # Pruebas de integración API
│   └── ...
├── .devcontainer/      # Configuración de Dev Containers para VS Code
└── ...
```

## ✨ Características Principales

- **Dynamic Schema-First Extraction**: Validación de entidades y relaciones contra un esquema dinámico antes de persistir en Neo4j, ahora con soporte de validez temporal.
- **Orquestación con LangGraph**: Flujos de trabajo de extracción e inferencia dirigidos por grafos de estado.
- **Procesamiento Asíncrono y Streaming**: Uso de Redpanda para ingesta asíncrona.
- **Manejo Seguro de Concurrencia**: `OntologyLockManager` con Redis para bloqueos distribuidos seguros.
- **Observabilidad IA**: Trazas de OpenTelemetry enviadas a Arize Phoenix.

## 🛠️ Herramientas de Calidad y Dependencias Core

Recientemente se han incorporado nuevas herramientas obligatorias para asegurar la calidad y mantenibilidad del código:

**Dependencias Principales:**
- **Dependency Injector**: Utilizado para implementar el patrón de Inyección de Dependencias, desacoplando los componentes del sistema.
- **Pydantic-Settings**: Gestión robusta y tipada de las variables de entorno y configuración.
- **Tenacity**: Manejo avanzado de reintentos (retries) para hacer el sistema más resiliente ante fallos de red o de los LLMs.

**Dependencias de Desarrollo:**
- **Ruff**: Linter extremadamente rápido escrito en Rust para mantener un estilo de código limpio y consistente.
- **Mypy (Strict Mode)**: Chequeo estático de tipos configurado en modo estricto (`strict = true`) para garantizar la seguridad de tipos en toda la base de código.

## ⚙️ Comandos Estandarizados (Makefile)

El proyecto utiliza un `Makefile` para estandarizar las tareas de desarrollo más comunes. Los comandos disponibles son:

- `make install`: Instala el proyecto y sus dependencias (incluyendo las de desarrollo) en modo editable (`pip install -e ".[dev]"`).
- `make lint`: Ejecuta **Ruff** para el análisis estático del código.
- `make typecheck`: Ejecuta **Mypy** en modo estricto para la validación estática de tipos.
- `make test`: Ejecuta la suite de pruebas con **Pytest**.
- `make all`: Ejecuta secuencialmente las tareas de calidad: `lint`, `typecheck` y `test`.

## 📋 Requisitos Previos

- Python 3.11+
- Base de Datos Neo4j (AuraDB o local, ver. 5+)
- Redis (Para el control de concurrencia y bloqueos distribuidos)
- Acceso a un LLM (OpenAI API o Local via Ollama)
- Docker (Para Dev Containers, Redpanda, Redis y Arize Phoenix)

## 🚀 Instalación y Entorno Local

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/tu-organizacion/nexus-graph-ai.git
   cd nexus-graph-ai
   ```

2. **Crear y activar entorno virtual:**
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   ```

3. **Instalar dependencias necesarias:**
   ```bash
   pip install -r requirements.txt
   ```

4. **Infraestructura Local (Docker):**
   Asegúrate de tener corriendo instancias de Neo4j, Redpanda (puerto 9092), Redis (puerto 6379) y Arize Phoenix (puerto 6006).

5. **Configuración de Entorno:**
   ```env
   NEO4J_URI=bolt://localhost:7687
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=tu_password
   REDIS_URL=redis://localhost:6379
   OPENAI_API_KEY=tu_api_key_o_ollama
   OPENAI_BASE_URL=http://localhost:11434/v1
   ```

## 💻 Uso

### 1. Iniciar el Servidor API (FastAPI)
```bash
fastapi dev api/main.py
```

### 2. Ingestar Datos (Redpanda & Async Chunking)
```bash
python cli/ingest.py data/negocio.txt
```

### 3. Consulta de un solo uso (One-shot)
```bash
python cli/ask.py "¿Qué proyectos están en riesgo?"
```

## 💻 Pruebas Unitarias (Pytest)

Las pruebas están completamente aisladas utilizando mocks robustos para evitar interactuar con bases de datos reales. Recientemente se han incluido suites de pruebas completas para concurrencia (`test_concurrency.py`) y para el enrutador (`test_router.py`).
```bash
PYTHONPATH=. pytest tests/
```

## 🤝 Contribución

Seguimos estrictamente las directrices de tipado y modularidad definidas en nuestros estándares Empresa 2026. Por favor, asegúrate de que todo pase las pruebas de `pytest`, mantenga la inyección de dependencias y el patrón **Repository**. Las validaciones deben ejecutarse a través de `ValidationPipeline` y los esquemas en `core/ontology.py`.

## 📄 Licencia

Este proyecto está bajo la Licencia MIT.
