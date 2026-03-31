from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI, Depends
from neo4j import AsyncGraphDatabase, AsyncDriver
import os


class Database:
    driver: AsyncDriver | None = None


db = Database()


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    uri = os.getenv("NEO4J_URI", "bolt://localhost:7687")
    user = os.getenv("NEO4J_USER", "neo4j")
    password = os.getenv("NEO4J_PASSWORD", "password")

    db.driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    # Simple check on startup
    try:
        await db.driver.verify_connectivity()
    except Exception as e:
        print(f"Failed to connect to Neo4j on startup: {e}")

    yield

    if db.driver:
        await db.driver.close()


app = FastAPI(lifespan=lifespan, title="Nexus Graph AI Enterprise")


async def get_db_driver() -> AsyncGenerator[AsyncDriver, None]:
    if db.driver is None:
        raise RuntimeError("Database driver not initialized")
    yield db.driver


@app.get("/health")
async def health_check() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/mcp/discover")
async def mcp_discover() -> dict[str, dict]:
    return {"schema": {}}
