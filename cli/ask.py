import asyncio
import os
import sys

# Ensure the root directory is in the path to import core correctly
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from core.engine import GraphQueryEngine


async def main():
    if len(sys.argv) < 2:
        print("Uso: python cli/ask.py 'Tu pregunta aquí'")
        return
    question = sys.argv[1]
    engine = GraphQueryEngine()
    try:
        await engine.query(question)
    finally:
        engine.close()


if __name__ == "__main__":
    asyncio.run(main())
