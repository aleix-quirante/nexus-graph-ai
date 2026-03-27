import asyncio
import os
import sys

# Ensure the root directory is in the path to import core correctly
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from core.engine import GraphQueryEngine


async def chat_loop():
    print("🤖 Bienvenido al Chat de NexusGraph AI.")
    print("Escribe '/exit' para salir o '/clear' para limpiar la pantalla.\n")
    engine = GraphQueryEngine()
    try:
        while True:
            user_input = input("Tú: ")
            if user_input.strip() == "/exit":
                print("👋 ¡Hasta luego!")
                break
            elif user_input.strip() == "/clear":
                print("\033[H\033[J", end="")
                continue
            elif not user_input.strip():
                continue

            await engine.query(user_input)
            print()
    finally:
        engine.close()


if __name__ == "__main__":
    asyncio.run(chat_loop())
