import asyncio
from neo4j import AsyncGraphDatabase


class Neo4jClient:
    def __init__(self, uri, user, password):
        self.driver = AsyncGraphDatabase.driver(uri, auth=(user, password))

    async def close(self):
        await self.driver.close()

    async def add_graph_data(self, extraction):
        async with self.driver.session() as session:
            # Crear Nodos
            for node in extraction.nodes:
                query = f"MERGE (n:{node.label} {{id: $id}}) SET n += $props"
                await session.run(query, id=node.id, props=node.properties)

            # Crear Relaciones
            for rel in extraction.relationships:
                query = (
                    f"MATCH (a {{id: $source}}), (b {{id: $target}}) "
                    f"MERGE (a)-[r:{rel.relation_type}]->(b)"
                )
                await session.run(query, source=rel.source, target=rel.target)
