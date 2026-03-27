# Nexus Graph AI 🌌

![Version](https://img.shields.io/badge/versión-2.0.0-blue.svg)
![Python](https://img.shields.io/badge/python-3.11%2B-blue)
![License](https://img.shields.io/badge/licencia-MIT-green)

Nexus Graph AI es una plataforma de vanguardia que combina Bases de Datos Orientadas a Grafos e Inteligencia Artificial para proporcionar conocimiento relacional profundo y capacidades inteligentes de consulta de datos. Construido bajo los estándares de la **Arquitectura de Referencia Empresa 2026**.

## 🏗️ Arquitectura de Referencia

Nuestra arquitectura está diseñada para ofrecer escalabilidad extrema, modularidad y procesamiento enfocado principalmente en IA ("AI-first"). A continuación, se muestra el flujo de datos de alto nivel:

```mermaid
graph TD
    %% Estilos
    classDef client fill:#3b82f6,stroke:#1d4ed8,stroke-width:2px,color:#fff;
    classDef core fill:#10b981,stroke:#047857,stroke-width:2px,color:#fff;
    classDef ai fill:#8b5cf6,stroke:#6d28d9,stroke-width:2px,color:#fff;
    classDef db fill:#f59e0b,stroke:#b45309,stroke-width:2px,color:#fff;

    %% Nodos
    Client([Interfaces: chat.py / ask.py]) ::: client
    Engine[Engine Central<br/>core/engine.py] ::: core
    Agent{Agentes Cypher & Answer<br/>pydantic-ai} ::: ai
    GraphDB[(Base de Datos Neo4j<br/>core/database.py)] ::: db
    
    %% Conexiones
    Client -->|Pregunta Natural| Engine
    Engine -->|Generación & Síntesis| Agent
    Engine -->|Cypher/Transacciones| GraphDB
    Agent <-->|Contexto & Esquema| GraphDB
```

## 📂 Estructura del Proyecto

```text
nexus-graph-ai/
├── core/               # Motor principal
│   ├── database.py     # Cliente Neo4j (Conexión y Transacciones)
│   └── engine.py       # Lógica Multi-Agente (Traducción NLP a Cypher)
├── cli/                # Comandos ejecutables
│   ├── ingest.py       # Pipeline de inyección de datos (LLM -> Grafo)
│   └── ask.py          # Consulta simple (One-shot QA)
├── data/               # Documentos fuente
│   └── empleados.txt   # Ejemplos y raw data
├── chat.py             # Interfaz interactiva de consola
├── requirements.txt    # Dependencias
└── .env                # Variables de entorno
```

## ✨ Características Principales

- **Consultas impulsadas por IA**: Realiza consultas a datos de grafos complejos utilizando lenguaje natural (soporte multilenguaje automático).
- **Extracción de Grafos de Conocimiento**: Extrae automáticamente entidades y relaciones a partir de texto no estructurado usando modelos de lenguaje (Ollama/Qwen).
- **Arquitectura Modular**: Separación clara entre motor de base de datos (`core/database.py`), inteligencia de agentes (`core/engine.py`) y CLI (`cli/`).
- **Chat Interactivo**: Sesiones conversacionales continuas con tu base de datos mediante comandos sencillos.

## 📋 Requisitos Previos

- Python 3.11+
- Base de Datos Neo4j (AuraDB o local)
- Acceso a un LLM (OpenAI API o Local via Ollama)

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

### 1. Ingestar Datos
Para procesar un texto y poblar la base de datos de grafos automáticamente:
```bash
python cli/ingest.py data/empleados.txt
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
*(Comandos del chat: escribe `/clear` para limpiar pantalla o `/exit` para salir).*

## 🤝 Contribución

Seguimos estrictamente las directrices de tipado y modularidad definidas en nuestros estándares Empresa 2026. Por favor, asegúrate de que todo pase la validación de `pydantic` y se adhiera a la arquitectura `core/cli` antes de hacer PR.

## 📄 Licencia

Este proyecto está bajo la Licencia MIT - consulta el archivo LICENSE para más detalles.
