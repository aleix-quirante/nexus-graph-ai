import asyncio
import os
import sys

# Permitir importar de core estando en la carpeta tests/
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.engine import GraphQueryEngine


async def run_stress_test():
    print("--- INICIANDO STRESS TEST AVANZADO ---")

    print("\n[STRESS TEST] Iniciando motor Graph AI (sin limpiar DB)...")
    engine = GraphQueryEngine()

    preguntas = [
        "¿Cuál es el valor total sumado de todos los pedidos?",
        "¿Cuántos camiones tiene exactamente la flota de Hierros del Vallès en total?",
        "Dime qué pedidos NO tienen ningún riesgo asociado.",
    ]

    try:
        for i, pregunta in enumerate(preguntas, 1):
            print(f"\n======================================")
            print(f"PREGUNTA {i}: {pregunta}")
            print(f"======================================")

            # El engine ya imprime internamente el Cypher, su justificación y el resultado del LLM.
            # Capturamos la salida para asegurar que fluya correctamente en consola.
            ans = await engine.query(pregunta)

            print(f"\n>>> RESPUESTA FINAL CONSOLIDADA (P{i}):\n{ans}")

    finally:
        engine.close()

    print("\n--- STRESS TEST FINALIZADO ---")


if __name__ == "__main__":
    asyncio.run(run_stress_test())
