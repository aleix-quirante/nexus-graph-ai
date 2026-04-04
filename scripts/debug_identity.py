import asyncio
import os

from database import Neo4jClient
from dotenv import load_dotenv

load_dotenv(override=True)


async def main():
    # 2. Copia exactamente el URI y el USER que usaste en 'test_conn.py' (el que funciona).
    uri_test = "neo4j+s://ec5b915f.databases.neo4j.io"
    user_test = "neo4j"
    pass_hardcoded = "EZk2-YsvAAu2rXBajKYP38CFgknUMZp1D0LQ1rL9Lu4"

    # 3. Importa el URI y el USER que está leyendo 'main.py' desde el '.env'.
    uri_env = os.getenv("NEO4J_URI", "").strip().replace('"', "").replace("'", "")
    user_env = os.getenv("NEO4J_USER", "").strip().replace('"', "").replace("'", "")

    # 4. Haz una comparación de longitud y de contenido carácter por carácter:
    print("--- COMPARACIÓN DE URI ---")
    print(f"Len Test: {len(uri_test)}, Len Env: {len(uri_env)}")
    for i, (c1, c2) in enumerate(zip(uri_test, uri_env)):
        print(f"Pos {i}: {repr(c1)} vs {repr(c2)} -> {'MATCH' if c1 == c2 else 'DIFF'}")

    print("\n--- COMPARACIÓN DE USER ---")
    print(f"Len Test: {len(user_test)}, Len Env: {len(user_env)}")
    for i, (c1, c2) in enumerate(zip(user_test, user_env)):
        print(f"Pos {i}: {repr(c1)} vs {repr(c2)} -> {'MATCH' if c1 == c2 else 'DIFF'}")

    # 5. Intenta realizar una operación de ESCRITURA simple en 'debug_identity.py'
    # usando el mismo objeto 'Neo4jClient' que usa 'main.py'.
    print("\n--- TEST DE ESCRITURA CON Neo4jClient ---")

    db = Neo4jClient(uri_test, user_test, pass_hardcoded)

    try:
        async with db.driver.session() as session:
            # We must use tx.run correctly and await the result's consumption if needed.
            # But just returning tx.run is usually fine for execute_write, except we might need to consume it to avoid lazy execution issues.
            async def run_query(tx):
                res = await tx.run("MERGE (t:Test {id: 'identidad_validada'}) RETURN t")
                return await res.data()

            result = await session.execute_write(run_query)
            print("✅ ESCRITURA EXITOSA EN LA NUBE")
            print(f"Resultado: {result}")
    except Exception as e:
        print(f"❌ FALLÓ ESCRITURA: {type(e).__name__} - {e}")
    finally:
        await db.close()


if __name__ == "__main__":
    asyncio.run(main())
