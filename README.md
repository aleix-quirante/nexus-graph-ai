# Nexus Graph AI 🌌

![Version](https://img.shields.io/badge/versión-2.1.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/licencia-MIT-green)

Nexus Graph AI es una plataforma de vanguardia que combina Bases de Datos Orientadas a Grafos e Inteligencia Artificial para proporcionar conocimiento relacional profundo y capacidades inteligentes de consulta de datos. Construido bajo los estándares de la **Arquitectura de Referencia Empresa 2026** y aplicando el patrón de diseño **Schema-First Graph Extraction**.

## 🏗️ Arquitectura de Referencia (Schema-First)

Nuestra arquitectura está diseñada para ofrecer escalabilidad extrema, modularidad y procesamiento enfocado principalmente en IA ("AI-first"). A diferencia de los sistemas RAG tradicionales, Nexus Graph AI obliga a los modelos generativos a adherirse estrictamente a una topología de Grafo de Conocimiento predefinida, eliminando alucinaciones y estandarizando las relaciones a gran escala.

A continuación, se muestra el flujo de datos de alto nivel:

```mermaid
graph TD
    %% Estilos
    classDef client fill:#3b82f6,stroke:#1d4ed8,stroke-width:2px,color:#fff;
    classDef core fill:#10b981,stroke:#047857,stroke-width:2px,color:#fff;
    classDef ai fill:#8b5cf6,stroke:#6d28d9,stroke-width:2px,color:#fff;
    classDef db fill:#f59e0b,stroke:#b45309,stroke-width:2px,color:#fff;

    %% Nodos
    Client([Interfaces: chat.py / ask.py / cli]) ::: client
    Engine[Engine Central<br/>core/engine.py] ::: core
    Schema[Schema Map<br/>core/schema_map.py] ::: core
    Agent{Agentes Cypher & Answer<br/>pydantic-ai} ::: ai
    GraphDB[(Base de Datos Neo4j<br/>core/database.py)] ::: db
    
    %% Conexiones
    Client -->|Pregunta Natural / Texto Raw| Engine
    Engine -->|Carga de Reglas Estrictas| Schema
    Schema -->|Restricciones de Tipado| Agent
    Engine -->|Generación & Síntesis| Agent
    Engine -->|Cypher Seguro (IS NOT NULL)| GraphDB
    Agent <-->|Contexto & Esquema| GraphDB
```

## 📂 Estructura del Proyecto

```text
nexus-graph-ai/
├── core/               # Motor principal
│   ├── database.py     # Cliente Neo4j (Conexión, Transacciones, Cartesian Product Fix)
│   ├── engine.py       # Lógica Multi-Agente (Traducción NLP a Cypher con 8 Reglas Críticas)
│   └── schema_map.py   # Diccionario Central de Nodos y Relaciones Canónicas (Schema-First)
├── cli/                # Comandos ejecutables
│   ├── ingest.py       # Pipeline de inyección de datos (LLM -> Grafo Tipado)
│   └── ask.py          # Consulta simple (One-shot QA)
├── data/               # Documentos fuente
│   ├── empleados.txt   # Ejemplos HR
│   └── negocio.txt     # Ejemplos B2B (Logística y Presupuestos)
├── tests/              # Pruebas automatizadas
│   ├── test_basico.py  # Pruebas básicas
│   ├── test_stress.py  # Pruebas de estrés
│   ├── test_conn.py    # Pruebas de conexión
│   └── test_qa.py      # Pruebas de QA
├── schemas.py          # Validación Pydantic (GraphExtraction, Node, Relationship)
├── chat.py             # Interfaz interactiva de consola
├── requirements.txt    # Dependencias
└── .env                # Variables de entorno
```

## ✨ Características Principales

- **Schema-First Extraction**: Las entidades (`EMPRESA`, `PEDIDO`, etc.) y relaciones (`REALIZA_PEDIDO`, `TIENE_RIESGO`) están fuertemente tipadas en `schema_map.py`. El LLM nunca inventa nodos o relaciones nuevas que rompan la base de datos, garantizando una ingesta masiva predecible.
- **Consultas impulsadas por IA Infallibles**: El motor en `core/engine.py` incorpora 8 reglas estrictas de generación Cypher que obligan a la IA a no inventar propiedades, no hacer búsquedas literales inútiles y a usar sintaxis segura para Neo4j 5+ (como `IS NOT NULL` en lugar de `EXISTS`).
- **Prevención de Cartesian Products**: El cliente de base de datos realiza inyecciones `WITH a, b LIMIT 1 MERGE` que previenen el colapso del cluster de Neo4j al ingestar relaciones de forma asíncrona.
- **Extracción de Grafos de Conocimiento**: Extrae automáticamente entidades, montos financieros, riesgos y relaciones a partir de texto no estructurado usando modelos de lenguaje (Ollama/Qwen).
- **Arquitectura Modular**: Separación clara entre motor de base de datos (`core/database.py`), inteligencia de agentes (`core/engine.py`) y CLI (`cli/`).
- **Chat Interactivo**: Sesiones conversacionales continuas con tu base de datos mediante comandos sencillos.

## 📋 Requisitos Previos

- Python 3.11+
- Base de Datos Neo4j (AuraDB o local, ver. 5+)
- Acceso a un LLM (OpenAI API o Local via Ollama - recomendado: qwen2.5:32b o superior para GraphRAG)

## 🚀 Instalación

1. **Clonar el repositorio:**
   ```bash
   git clone https://github.com/tu-organizacion/nexus-graph-ai.git
   cd nexus-graph-ai
   ```

2. **Instalar dependencias:**
   ```bash
   pip install -r requirements.txt
   ```

3. **Configuración de Entorno:**
   Copia el archivo `.env.example` a `.env` (o crea uno) y configura tus variables:
   ```env
   NEO4J_URI=bolt://localhost:7687
   NEO4J_USER=neo4j
   NEO4J_PASSWORD=tu_password
   OPENAI_API_KEY=tu_api_key_o_ollama
   OPENAI_BASE_URL=http://localhost:11434/v1
   ```

## 💻 Uso

### 1. Ingestar Datos (Modo Schema-First)
Para procesar un texto y poblar la base de datos de grafos automáticamente, respetando el `schema_map.py`:
```bash
python cli/ingest.py data/negocio.txt
```

### 2. Consulta de un solo uso (One-shot)
Para hacer una pregunta rápida sin entrar al chat interactivo:
```bash
python cli/ask.py "¿Qué proyectos están en riesgo?"
```

### 3. Modo Chat Interactivo
Inicia la consola interactiva conversacional:
```bash
python chat.py
```
*(Comandos del chat: escribe `/clear_db` para limpiar la base de datos de Neo4j, `/clear` para limpiar pantalla de terminal, o `/exit` para salir).*

## 🤝 Contribución

Seguimos estrictamente las directrices de tipado y modularidad definidas en nuestros estándares Empresa 2026. Por favor, asegúrate de que todo pase la validación de `pydantic` y se adhiera al patrón **Schema-First Extraction** antes de hacer PR. Nunca añadas propiedades al LLM Extraction que no estén respaldadas en el `schema_map.py`.

## 📄 Licencia

Este proyecto está bajo la Licencia MIT - consulta el archivo LICENSE para más detalles.
