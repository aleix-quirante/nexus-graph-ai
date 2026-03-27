import logging
from neo4j import GraphDatabase, basic_auth

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class Neo4jClient:
    def __init__(self, uri, user, password):
        self.driver = GraphDatabase.driver(uri, auth=(user, password))

    def check_connection(self):
        try:
            self.driver.verify_authentication()
            print("✅ Autenticación verificada en el Client.")
            return True
        except Exception as e:
            print(f"❌ Fallo de autenticación en el Client: {e}")
            return False

    def clear_database(self):
        with self.driver.session() as session:
            session.run("MATCH (n) DETACH DELETE n")
        print("🗑️ Base de datos limpiada correctamente.")

    def get_schema_snapshot(self):
        with self.driver.session() as session:
            labels = [
                record["label"]
                for record in session.run("CALL db.labels() YIELD label")
            ]
            relationships = [
                record["relationshipType"]
                for record in session.run(
                    "CALL db.relationshipTypes() YIELD relationshipType"
                )
            ]
            properties = [
                record["propertyKey"]
                for record in session.run("CALL db.propertyKeys() YIELD propertyKey")
            ]
            return {
                "labels": labels,
                "relationships": relationships,
                "properties": properties,
            }

    def close(self):
        self.driver.close()

    def add_graph_data(self, extraction):
        with self.driver.session(database="neo4j") as session:
            session.run("CREATE (t:Check {timestamp: datetime()})")
            print("🚀 Prueba de escritura inicial: ÉXITO")
            # Transacciones controladas para evitar bloqueos en la BD
            for node in extraction.nodes:
                session.execute_write(self._merge_node, node)
            for rel in extraction.relationships:
                session.execute_write(self._merge_edge, rel)
        logger.info("Ingesta completada en la nube.")

    @staticmethod
    def _merge_node(tx, node):
        query = f"MERGE (n:{node.label} {{id: $id}}) SET n += $props"
        tx.run(query, id=node.id, props=node.properties)

    @staticmethod
    def _merge_edge(tx, rel):
        query = (
            f"MATCH (a {{id: $source_id}}), (b {{id: $target_id}}) "
            f"WITH a, b LIMIT 1 "
            f"MERGE (a)-[r:{rel.type}]->(b) "
            "SET r += $props"
        )
        tx.run(
            query,
            source_id=rel.source_id,
            target_id=rel.target_id,
            props=rel.properties,
        )
