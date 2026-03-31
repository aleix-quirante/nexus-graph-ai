import streamlit as st
import asyncio
import sys
import os

# Add root directory to path to ensure core imports work
sys.path.append(os.path.abspath(os.path.dirname(__file__)))

from core.engine import GraphQueryEngine

st.set_page_config(
    page_title="Nexus Graph AI - Query Engine", page_icon="🕸️", layout="centered"
)

st.title("🕸️ Nexus Graph AI")
st.markdown("Consulta tu base de datos orientada a grafos utilizando lenguaje natural.")

# Initialize the engine in session state if it doesn't exist
if "engine" not in st.session_state:
    st.session_state.engine = GraphQueryEngine()

# Input for the user's question
question = st.text_input(
    "Ingresa tu pregunta:", placeholder="Ej. ¿Qué material provee la empresa X?"
)


async def run_query(q):
    return await st.session_state.engine.query(q)


if st.button("Consultar", type="primary"):
    if question.strip():
        with st.spinner("Analizando intención corporativa y generando consulta..."):
            try:
                # Run the asynchronous query
                answer = asyncio.run(run_query(question))

                st.success("Consulta completada con éxito.")
                st.markdown("### Respuesta:")
                st.write(answer)
            except Exception as e:
                st.error(f"Error al procesar la consulta: {str(e)}")
    else:
        st.warning("Por favor, ingresa una pregunta antes de consultar.")

st.markdown("---")
st.markdown(
    "**Nota:** Esta aplicación se conecta a la base de datos Neo4j configurada en las variables de entorno."
)
