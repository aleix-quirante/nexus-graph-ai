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
from core.exceptions import DatabaseConnectionError

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class StaleTransactionError(Exception):
    """Exception raised when a concurrency violation is detected due to a stale fencing token."""

    pass


class GraphRepository(Protocol):
    async def check_connection(self) -> bool: ...

    async def clear_database(self) -> None: ...

    async def get_schema_snapshot(self) -> Dict[str, Any]: ...

    async def add_graph_data(
        self, extraction: GraphExtraction, fencing_token: int
    ) -> None: ...

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
            logger.error(
                f"❌ Fallo de autenticación en el Repository: {e}", exc_info=True
            )
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
            logger.error(f"❌ Error limpiando la base de datos: {e}", exc_info=True)
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
    async def add_graph_data(
        self, extraction: GraphExtraction, fencing_token: int
    ) -> None:
        async with self.driver.session(database="neo4j") as session:
            await session.run("CREATE (t:Check {timestamp: datetime()})")
            logger.info("🚀 Prueba de escritura inicial: ÉXITO")

            # Empaquetar todos los nodos en una única lista
            nodes_data = [
                {"id": n.id, "label": n.label.value, "props": n.properties}
                for n in extraction.nodes
            ]

            # Empaquetar todas las relaciones en una única lista
            rels_data = [
                {
                    "source_id": r.source_id,
                    "target_id": r.target_id,
                    "type": r.type,
                    "props": r.properties,
                }
                for r in extraction.relationships
            ]

            # Transmitir el lote completo en una sola transacción optimizada
            await session.execute_write(
                self._execute_batch_unwind, nodes_data, rels_data, fencing_token
            )

        logger.info("Ingesta completada en la nube.")

    @staticmethod
    async def _execute_batch_unwind(
        tx: AsyncTransaction, nodes_data: list, rels_data: list, fencing_token: int
    ) -> None:
        nodes_by_label = {}
        for node in nodes_data:
            nodes_by_label.setdefault(node["label"], []).append(node)

        for label, nodes in nodes_by_label.items():
            query = (
                f"UNWIND $nodes AS node "
                f"MERGE (n:`{label}` {{id: node.id}}) "
                "WITH n, node "
                "WHERE coalesce(n.last_fencing_token, 0) < $fencing_token "
                "SET n += node.props, n.last_fencing_token = $fencing_token"
            )
            await tx.run(query, nodes=nodes, fencing_token=fencing_token)

        rels_by_type = {}
        for rel in rels_data:
            rels_by_type.setdefault(rel["type"], []).append(rel)

        for rel_type, rels in rels_by_type.items():
            query = (
                "UNWIND $rels AS rel "
                "MATCH (a {id: rel.source_id}), (b {id: rel.target_id}) "
                f"MERGE (a)-[r:`{rel_type}`]->(b) "
                "WITH r, rel "
                "WHERE coalesce(r.last_fencing_token, 0) < $fencing_token "
                "SET r += rel.props, r.last_fencing_token = $fencing_token"
            )
            await tx.run(query, rels=rels, fencing_token=fencing_token)


# Maintain backward compatibility aliases if absolutely needed
Neo4jClient = Neo4jRepository
