import pytest
from core.schemas import GraphExtraction, Node, Relationship


def test_neo4j_client_add_graph_data(mock_neo4j_client):
    extraction = GraphExtraction(
        nodes=[
            Node(id="emp_1", label="EMPRESA", properties={"nombre": "TechCorp"}),
            Node(id="ped_1", label="PEDIDO", properties={"monto": 1000}),
        ],
        relationships=[
            Relationship(
                source_id="emp_1",
                target_id="ped_1",
                type="REALIZA_PEDIDO",
                properties={},
            )
        ],
    )

    mock_neo4j_client.add_graph_data(extraction)

    driver = mock_neo4j_client.driver
    assert len(driver.sessions) == 1
    session = driver.sessions[0]

    # 2 nodes + 1 relationship = 3 writes
    assert len(session.executed_writes) == 3

    # Check if the node query is correct
    node_queries = [q[0] for q in session.tx.queries if "MERGE (n:" in q[0]]
    assert len(node_queries) == 2
    assert "MERGE (n:EMPRESA {id: $id}) SET n += $props" in node_queries
    assert "MERGE (n:PEDIDO {id: $id}) SET n += $props" in node_queries

    # Check if the edge query is correct
    edge_queries = [q[0] for q in session.tx.queries if "MERGE (a)-[r:" in q[0]]
    assert len(edge_queries) == 1
    assert "MERGE (a)-[r:REALIZA_PEDIDO]->(b)" in edge_queries[0]


def test_neo4j_client_get_schema(mock_neo4j_client):
    schema = mock_neo4j_client.get_schema_snapshot()

    assert "labels" in schema
    assert "relationships" in schema
    assert "properties" in schema
    assert "EMPRESA" in schema["labels"]
