# Nexus Graph AI 🌌

![Version](https://img.shields.io/badge/versión-3.0.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/licencia-MIT-green)

Nexus Graph AI es una plataforma de vanguardia que combina Bases de Datos Orientadas a Grafos e Inteligencia Artificial para proporcionar conocimiento relacional profundo y capacidades inteligentes de consulta de datos. Construido bajo los estándares de la **Arquitectura de Referencia Empresa 2026** y aplicando el patrón de diseño **Dynamic Schema-First Graph Extraction** con **Inyección de Dependencias**.

## 🏗️ Arquitectura de Referencia

Nuestra arquitectura está diseñada para ofrecer escalabilidad extrema, modularidad y procesamiento enfocado en IA. Recientemente, el proyecto ha evolucionado para incluir streaming de eventos, observabilidad avanzada y una capa de API robusta:

- **Repository Pattern & DI**: Desacoplamiento de la base de datos mediante el protocolo abstracto `GraphRepository` (implementado en `Neo4jRepository`). Las dependencias se inyectan en tiempo de ejecución, facilitando el testing aislado.
- **Ontología Dinámica y Auto-Recovery**: Validación estricta de grafos utilizando Pydantic. Si el LLM genera estructuras inválidas, un bucle automático de recuperación (`max_retries`) solicita auto-corrección.
- **Event-Driven Ingestion (Redpanda)**: El pipeline de ingesta ahora soporta particionado de documentos asíncrono y encolamiento a través de un productor de Redpanda, permitiendo procesar grandes volúmenes de texto de manera distribuida.
- **Observabilidad Integral (Arize Phoenix)**: Instrumentación completa con **OpenTelemetry** y **OpenInference**. Trazas detalladas de llamadas a la API, workers de procesamiento y peticiones al LLM son enviadas a una instancia local de Arize Phoenix, garantizando visibilidad total sobre el rendimiento y los flujos de IA.
- **API REST & MCP Scaffolding**: Un servidor **FastAPI** expone el core funcional (ej. health checks, descubrimiento MCP), conectándose a Neo4j mediante inyección de dependencias para un ciclo de vida seguro.

## 📂 Estructura del Proyecto

```text
nexus-graph-ai/
├── api/                # Capa de servicios REST
│   └── main.py         # Servidor FastAPI con endpoints y setup de telemetría
├── core/               # Motor principal y dominio
│   ├── database.py     # Implementación del GraphRepository y Neo4jRepository
│   ├── engine.py       # Lógica Multi-Agente
│   ├── observability.py# Configuración de OpenTelemetry y exportación a Arize Phoenix
│   ├── ontology.py     # Ontología Dinámica y validación de esquemas
│   ├── schema_map.py   # Diccionario central de mapeo
│   └── worker.py       # Procesamiento de tareas e instrumentación OpenInference
├── cli/                # Comandos ejecutables
│   ├── ingest.py       # Productor de Redpanda y chunking asíncrono de documentos
│   └── ask.py          # CLI para consultas interactivas
├── tests/              # Pruebas automatizadas (Pytest)
├── .devcontainer/      # Configuración de Dev Containers para VS Code
└── ...
```

## ✨ Características Principales

- **Dynamic Schema-First Extraction**: Validación de entidades y relaciones contra un esquema dinámico antes de persistir en Neo4j.
- **Procesamiento Asíncrono y Streaming**: Uso de Redpanda para ingesta asíncrona y particionamiento de documentos.
- **Observabilidad IA**: Trazas de OpenTelemetry enviadas a Arize Phoenix para monitorear prompts, latencia y ejecución de agentes.
- **Prevención de Cartesian Products**: Inyecciones seguras y atómicas en Neo4j.
- **Desarrollo Consistente**: Soporte para **Dev Containers**, garantizando un entorno de desarrollo reproducible para todo el equipo.

## 📋 Requisitos Previos

- Python 3.11+
- Base de Datos Neo4j (AuraDB o local, ver. 5+)
- Acceso a un LLM (OpenAI API o Local via Ollama)
- Docker (Para Dev Containers, Redpanda y Arize Phoenix)

## 🚀 Instalación y Entorno Local

Puedes utilizar el entorno **Dev Container** incluido abriendo el proyecto en VS Code y seleccionando "Reopen in Container". Alternativamente, para una instalación manual:

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
   Asegúrate de tener corriendo instancias de Neo4j, Redpanda (puerto 9092) y Arize Phoenix (puerto 6006 para trazas OTLP).

5. **Configuración de Entorno:**
   Copia el archivo `.env.example` a `.env` y configura tus variables:
   ```env
   NEO4J_URI=bolt://localhost:7687
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=tu_password
   OPENAI_API_KEY=tu_api_key_o_ollama
   OPENAI_BASE_URL=http://localhost:11434/v1
   ```

## 💻 Uso

### 1. Iniciar el Servidor API (FastAPI)
La API expone endpoints de salud e integración MCP, instrumentados con OpenTelemetry:
```bash
fastapi dev api/main.py
```

### 2. Ingestar Datos (Redpanda & Async Chunking)
Para particionar un documento y enviarlo a la cola de procesamiento asíncrono:
```bash
python cli/ingest.py data/negocio.txt
```

### 3. Consulta de un solo uso (One-shot)
```bash
python cli/ask.py "¿Qué proyectos están en riesgo?"
```

### 4. Aplicación Web (Streamlit)
Levanta la interfaz web interactiva para explorar el grafo:
```bash
streamlit run app.py
```

## 💻 Pruebas Unitarias (Pytest)

Las pruebas están completamente aisladas utilizando mocks robustos para evitar interactuar con bases de datos reales.
```bash
PYTHONPATH=. pytest tests/
```

## 🤝 Contribución

Seguimos estrictamente las directrices de tipado y modularidad definidas en nuestros estándares Empresa 2026. Por favor, asegúrate de que todo pase las pruebas de `pytest`, mantenga la inyección de dependencias y el patrón **Repository**. Las validaciones deben ejecutarse a través de `ValidationPipeline` y los esquemas en `core/ontology.py`.

## 📄 Licencia

Este proyecto está bajo la Licencia MIT.
