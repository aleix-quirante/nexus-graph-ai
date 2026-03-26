import asyncio
import os
from dotenv import load_dotenv
from database import Neo4jClient

# Cargar variables de entorno
load_dotenv()


async def main():
    # Setup de variables
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")

    print("Inicializando Neo4jClient...")
    client = Neo4jClient(uri, user, password)

    try:
        # Aquí iría el código de extracción usando Pydantic AI
        # extraction = extractor.extract_from_text("...")
        # await client.add_graph_data(extraction)
        print(
            "Pipeline de extracción listo. Configura los modelos y datos para procesar."
        )
    finally:
        await client.close()
        print("Conexión cerrada.")


if __name__ == "__main__":
    asyncio.run(main())
