# Nexus Graph AI 🌌

![Version](https://img.shields.io/badge/versión-3.0.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/licencia-MIT-green)

Nexus Graph AI es una plataforma de vanguardia que combina Bases de Datos Orientadas a Grafos e Inteligencia Artificial para proporcionar conocimiento relacional profundo y capacidades inteligentes de consulta de datos. Construido bajo los estándares de la **Arquitectura de Referencia Empresa 2026** y aplicando el patrón de diseño **Dynamic Schema-First Graph Extraction** con **Inyección de Dependencias**.

## 🏗️ Arquitectura de Referencia (Dynamic Schema-First & Repository Pattern)

Nuestra arquitectura está diseñada para ofrecer escalabilidad extrema, modularidad y procesamiento enfocado en IA. A diferencia de los sistemas RAG tradicionales, Nexus Graph AI obliga a los modelos generativos a adherirse estrictamente a una topología de Grafo de Conocimiento predefinida de forma dinámica, eliminando alucinaciones y estandarizando las relaciones a gran escala.

Recientemente hemos transicionado hacia una arquitectura más robusta:
- **Repository Pattern**: Se ha sustituido el acoplamiento directo de `Neo4jClient` por el protocolo abstracto `GraphRepository` implementado mediante `Neo4jRepository` en `core/database.py`.
- **Inyección de Dependencias**: Funciones críticas de orquestación y procesamiento asíncrono (como en `cli/ingest.py`) ahora reciben instancias inyectadas del cliente de base de datos (`GraphRepository`) y de IA (`AsyncOpenAI`), eliminando el estado global y maximizando la testabilidad.
- **Ontología Dinámica**: Un sistema de inyección de esquemas dinámicos utilizando modelos de dominio de Pydantic (`core/ontology.py`) que sincronizan automáticamente con Neo4j e incluyen un pipeline estricto de validación (autorecovery de LLM).

## 📂 Estructura del Proyecto

```text
nexus-graph-ai/
├── core/               # Motor principal
│   ├── database.py     # Implementación del GraphRepository Protocol y Neo4jRepository
│   ├── engine.py       # Lógica Multi-Agente (Traducción NLP a Cypher con Reglas Críticas)
│   ├── ontology.py     # Ontología Dinámica, Registro de Esquemas y ValidationPipeline
│   └── schema_map.py   # Diccionario Central compatibilizado dinámicamente
├── cli/                # Comandos ejecutables
│   ├── ingest.py       # Pipeline de inyección de datos (Inyección de Dependencias, LLM -> Grafo Tipado)
│   └── ask.py          # Consulta simple (One-shot QA)
├── tests/              # Pruebas automatizadas (Pytest)
│   ├── conftest.py     # Fixtures y Mocks robustos para GraphRepository
│   ├── test_ontology.py# Pruebas de la Ontología Dinámica y el ValidationPipeline
│   └── test_database.py# Pruebas transaccionales aisladas de Base de Datos
└── ...
```

## ✨ Características Principales

- **Dynamic Schema-First Extraction**: Las entidades y relaciones se validan contra un esquema dinámico registrado en tiempo de ejecución. El pipeline rechaza relaciones imposibles antes de llegar a la base de datos.
- **Auto-Recovery Loop (LLM)**: Si el LLM comete un error de estructura o de lógica ontológica, un bucle de reintento (`max_retries`) captura las fallas de Pydantic e instruye al agente para que auto-corrija su respuesta instantáneamente.
- **Patrón Repositorio y DI**: Base de código completamente testeable en aislamiento gracias a las inyecciones de dependencias formales.
- **Prevención de Cartesian Products**: El cliente de base de datos realiza inyecciones seguras y atómicas, mitigando el colapso del cluster.

## 📋 Requisitos Previos

- Python 3.11+
- Base de Datos Neo4j (AuraDB o local, ver. 5+)
- Acceso a un LLM (OpenAI API o Local via Ollama)

## 🚀 Instalación y Entorno Virtual Local

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
   pip install pytest pydantic neo4j openai
   pip install -r requirements.txt
   ```

4. **Configuración de Entorno:**
   Copia el archivo `.env.example` a `.env` y configura tus variables:
   ```env
   NEO4J_URI=bolt://localhost:7687
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=tu_password
   OPENAI_API_KEY=tu_api_key_o_ollama
   OPENAI_BASE_URL=http://localhost:11434/v1
   ```

## 💻 Pruebas Unitarias (Pytest)

Las pruebas están completamente aisladas utilizando mocks robustos (como `MockNeo4jDriver`) para evitar interactuar con bases de datos reales. Para ejecutar la suite completa de tests de la arquitectura:

```bash
PYTHONPATH=. .venv/bin/pytest tests/test_ontology.py tests/test_database.py
```

## 💻 Uso

### 1. Ingestar Datos (Modo DI & Async)
Para procesar un texto y poblar la base de datos de grafos utilizando la inyección de dependencias y la ontología dinámica:
```bash
python cli/ingest.py data/negocio.txt
```

### 2. Consulta de un solo uso (One-shot)
```bash
python cli/ask.py "¿Qué proyectos están en riesgo?"
```

### 3. Aplicación Web (Streamlit)
Para levantar la interfaz web interactiva que te permite consultar el grafo en tiempo real:
```bash
source venv/bin/activate
streamlit run app.py
```

## 🤝 Contribución

Seguimos estrictamente las directrices de tipado y modularidad definidas en nuestros estándares Empresa 2026. Por favor, asegúrate de que todo pase las pruebas de `pytest`, mantenga la inyección de dependencias y el patrón **Repository**. Las validaciones deben ejecutarse a través de `ValidationPipeline` y los esquemas en `core/ontology.py`.

## 📄 Licencia

Este proyecto está bajo la Licencia MIT.
