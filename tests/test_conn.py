import asyncio
from neo4j import AsyncGraphDatabase


async def test():
    uri = "neo4j+s://ec5b915f.databases.neo4j.io"
    user = "neo4j"
    password = "EZk2-YsvAAu2rXBajKYP38CFgknUMZp1D0LQ1rL9Lu4"

    driver = AsyncGraphDatabase.driver(uri, auth=(user, password))
    try:
        await driver.verify_authentication()
        print("✅ ¡CONEXIÓN EXITOSA! La contraseña es correcta.")
    except Exception as e:
        print(f"❌ FALLO TOTAL: {e}")
    finally:
        await driver.close()


asyncio.run(test())
