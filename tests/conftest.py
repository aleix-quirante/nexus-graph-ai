import pytest
from unittest.mock import MagicMock
from core.database import Neo4jClient
from core.ontology import OntologyRegistry, EntitySchema, RelationshipSchema


class MockTransaction:
    def __init__(self):
        self.queries = []

    def run(self, query, **kwargs):
        self.queries.append((query, kwargs))
        return MagicMock()


class MockSession:
    def __init__(self):
        self.tx = MockTransaction()
        self.executed_writes = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        pass

    def execute_write(self, func, *args, **kwargs):
        self.executed_writes.append((func, args, kwargs))
        return func(self.tx, *args, **kwargs)

    def run(self, query, **kwargs):
        self.tx.queries.append((query, kwargs))

        # Simple mock responses for basic queries
        mock_result = MagicMock()
        mock_result.data.return_value = [{"label": "EMPRESA"}, {"label": "PEDIDO"}]
        mock_result.__iter__.return_value = [{"label": "EMPRESA"}, {"label": "PEDIDO"}]

        if "db.labels" in query:
            return [{"label": "EMPRESA"}, {"label": "PEDIDO"}]
        elif "db.relationshipTypes" in query:
            return [
                {"relationshipType": "REALIZA_PEDIDO"},
                {"relationshipType": "ATIENDE_PEDIDO"},
            ]
        elif "db.propertyKeys" in query:
            return [{"propertyKey": "id"}, {"propertyKey": "monto"}]

        return mock_result


class MockNeo4jDriver:
    def __init__(self):
        self.sessions = []

    def session(self, **kwargs):
        session = MockSession()
        self.sessions.append(session)
        return session

    def verify_authentication(self):
        return True

    def close(self):
        pass


@pytest.fixture
def mock_neo4j_client():
    client = Neo4jClient("bolt://localhost:7687", "neo4j", "password")
    client.driver = MockNeo4jDriver()
    return client


@pytest.fixture
def test_registry():
    registry = OntologyRegistry()
    registry.register_entity(EntitySchema(name="EMPRESA", aliases=["PROVEEDOR"]))
    registry.register_entity(EntitySchema(name="PEDIDO", aliases=["ORDEN"]))
    registry.register_relationship(
        RelationshipSchema(
            name="REALIZA_PEDIDO",
            allowed_sources=["EMPRESA"],
            allowed_targets=["PEDIDO"],
        )
    )
    return registry
