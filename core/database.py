import logging
from typing import Any, Dict, Protocol
from neo4j import AsyncGraphDatabase, AsyncDriver, AsyncTransaction
from tenacity import (
    retry,
    stop_after_attempt,
    wait_exponential,
    retry_if_exception_type,
    AsyncRetrying,
)
from neo4j.exceptions import ServiceUnavailable, TransientError
from core.schemas import GraphExtraction

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class GraphRepository(Protocol):
    async def check_connection(self) -> bool: ...

    async def clear_database(self) -> None: ...

    async def get_schema_snapshot(self) -> Dict[str, Any]: ...

    async def add_graph_data(self, extraction: GraphExtraction) -> None: ...

    async def close(self) -> None: ...


class Neo4jRepository:
    def __init__(self, uri: str, user: str, password: str):
        self.driver: AsyncDriver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((ServiceUnavailable, TransientError)),
        reraise=True,
    )
    async def check_connection(self) -> bool:
        try:
            await self.driver.verify_authentication()
            logger.info("✅ Autenticación verificada en el Repository.")
            return True
        except Exception as e:
            logger.error(f"❌ Fallo de autenticación en el Repository: {e}")
            return False

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ServiceUnavailable, TransientError)),
        reraise=True,
    )
    async def clear_database(self) -> None:
        # Production-ready batch delete to avoid OOM errors on large graphs
        query = """
        MATCH (n)
        CALL {
            WITH n
            DETACH DELETE n
        } IN TRANSACTIONS OF 10000 ROWS
        """
        try:
            await self.driver.execute_query(query)
            logger.info("🗑️ Base de datos limpiada correctamente.")
        except Exception as e:
            logger.error(f"❌ Error limpiando la base de datos: {e}")
            raise

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ServiceUnavailable, TransientError)),
        reraise=True,
    )
    async def get_schema_snapshot(self) -> Dict[str, Any]:
        async with self.driver.session() as session:
            labels_result = await session.run("CALL db.labels() YIELD label")
            labels = [record["label"] async for record in labels_result]

            rel_result = await session.run(
                "CALL db.relationshipTypes() YIELD relationshipType"
            )
            relationships = [record["relationshipType"] async for record in rel_result]

            props_result = await session.run("CALL db.propertyKeys() YIELD propertyKey")
            properties = [record["propertyKey"] async for record in props_result]

            return {
                "labels": labels,
                "relationships": relationships,
                "properties": properties,
            }

    async def close(self) -> None:
        await self.driver.close()

    @retry(
        stop=stop_after_attempt(5),
        wait=wait_exponential(multiplier=1, min=2, max=30),
        retry=retry_if_exception_type((ServiceUnavailable, TransientError)),
        reraise=True,
    )
    async def add_graph_data(self, extraction: GraphExtraction) -> None:
        async with self.driver.session(database="neo4j") as session:
            await session.run("CREATE (t:Check {timestamp: datetime()})")
            logger.info("🚀 Prueba de escritura inicial: ÉXITO")

            for node in extraction.nodes:
                await session.execute_write(self._merge_node, node)
            for rel in extraction.relationships:
                await session.execute_write(self._execute_edge_mutation, rel)

        logger.info("Ingesta completada en la nube.")

    @staticmethod
    async def _merge_node(tx: AsyncTransaction, node: Any) -> None:
        query = f"MERGE (n:`{node.label.value}` {{id: $id}}) SET n += $props"
        await tx.run(query, id=node.id, props=node.properties)

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        retry=retry_if_exception_type((ServiceUnavailable, TransientError)),
        reraise=True,
    )
    async def _execute_edge_mutation(self, tx: AsyncTransaction, rel: Any) -> None:
        query = (
            f"MATCH (a {{id: $source_id}}), (b {{id: $target_id}}) "
            f"WITH a, b LIMIT 1 "
            f"MERGE (a)-[r:{rel.type}]->(b) "
            "SET r += $props"
        )
        await tx.run(
            query,
            source_id=rel.source_id,
            target_id=rel.target_id,
            props=rel.properties,
        )


# Maintain backward compatibility aliases if absolutely needed
Neo4jClient = Neo4jRepository
