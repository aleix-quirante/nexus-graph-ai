import logging
from neo4j import AsyncGraphDatabase

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Neo4jClient:
    def __init__(self, uri, user, password):
        self.driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    async def close(self):
        await self.driver.close()

    async def add_graph_data(self, extraction):
        async with self.driver.session() as session:
            # Transacciones controladas para evitar bloqueos en la BD
            for node in extraction.nodes:
                await session.execute_write(self._merge_node, node)
            for rel in extraction.relationships:
                await session.execute_write(self._merge_edge, rel)
        logger.info("Ingesta completada en la nube.")

    @staticmethod
    async def _merge_node(tx, node):
        query = f"MERGE (n:{node.label} {{id: $id}}) SET n += $props"
        await tx.run(query, id=node.id, props=node.properties)

    @staticmethod
    async def _merge_edge(tx, rel):
        query = (
            "MATCH (a {id: $source_id}), (b {id: $target_id}) "
            f"MERGE (a)-[r:{rel.type}]->(b) "
            "SET r += $props"
        )
        await tx.run(
            query,
            source_id=rel.source_id,
            target_id=rel.target_id,
            props=rel.properties,
        )
