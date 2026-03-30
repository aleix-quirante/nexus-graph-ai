import asyncio
import os
import subprocess
from dotenv import load_dotenv
from core.database import Neo4jClient
from core.engine import GraphQueryEngine


async def run_qa():
    print("--- INICIANDO QA END-TO-END ---")

    # 1. Limpiar la base de datos
    load_dotenv(override=True)
    uri = os.getenv("NEO4J_URI", "")
    user = os.getenv("NEO4J_USER", "")
    password = os.getenv("NEO4J_PASSWORD", "")

    client = Neo4jClient(uri, user, password)
    print("\n[QA] Limpiando la base de datos...")
    client.clear_database()
    client.close()

    # 2. Ejecutar la ingesta
    print("\n[QA] Ejecutando ingesta de data/negocio.txt...")
    result = subprocess.run(
        ["python3", "cli/ingest.py", "data/negocio.txt"], capture_output=True, text=True
    )
    if result.returncode != 0:
        print("❌ Error en la ingesta:")
        print(result.stderr)
        return
    else:
        print("✅ Ingesta completada con éxito.")
        # print(result.stdout) # Opcional si quieres ver toda la salida

    # 3. Consultas
    print("\n[QA] Ejecutando consultas al motor Graph AI...")
    engine = GraphQueryEngine()
    try:
        q1 = "¿De cuánto dinero es el presupuesto de la operación?"
        print(f"\nPregunta 1: {q1}")
        ans1 = await engine.query(q1)
        print(f"-> Respuesta Final Q1:\n{ans1}")

        q2 = "¿Por qué está enfadado Construcciones Aleix?"
        print(f"\nPregunta 2: {q2}")
        ans2 = await engine.query(q2)
        print(f"-> Respuesta Final Q2:\n{ans2}")

    finally:
        engine.close()

    print("\n--- QA FINALIZADO ---")


if __name__ == "__main__":
    asyncio.run(run_qa())
