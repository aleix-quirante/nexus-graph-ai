import pytest
from core.ontology import ValidationPipeline
from core.schemas import GraphExtraction, Node, Relationship


@pytest.mark.parametrize(
    "raw_label, expected_label",
    [
        ("EMPRESA", "EMPRESA"),
        ("PROVEEDOR", "EMPRESA"),
        ("DESCONOCIDO", "DESCONOCIDO"),
        ("", ""),
    ],
)
def test_entity_resolution(test_registry, raw_label, expected_label):
    assert test_registry.resolve_entity_label(raw_label) == expected_label


@pytest.mark.parametrize(
    "nodes, relationships, expected_rels_count",
    [
        # Valid Relationship
        (
            [
                Node(id="e1", label="EMPRESA", properties={}),
                Node(id="p1", label="PEDIDO", properties={}),
            ],
            [
                Relationship(
                    source_id="e1", target_id="p1", type="REALIZA_PEDIDO", properties={}
                )
            ],
            1,
        ),
        # Invalid Source (PEDIDO cannot REALIZA_PEDIDO)
        (
            [
                Node(id="p2", label="PEDIDO", properties={}),
                Node(id="p1", label="PEDIDO", properties={}),
            ],
            [
                Relationship(
                    source_id="p2", target_id="p1", type="REALIZA_PEDIDO", properties={}
                )
            ],
            0,
        ),
        # Unmapped relationship is kept as is since no schema restricts it (or depending on strictness)
        (
            [
                Node(id="e1", label="EMPRESA", properties={}),
                Node(id="p1", label="PEDIDO", properties={}),
            ],
            [
                Relationship(
                    source_id="e1", target_id="p1", type="NUEVA_RELACION", properties={}
                )
            ],
            1,
        ),
    ],
)
def test_validation_pipeline(test_registry, nodes, relationships, expected_rels_count):
    pipeline = ValidationPipeline(test_registry)
    extraction = GraphExtraction(nodes=nodes, relationships=relationships)

    validated = pipeline.validate_extraction(extraction)

    assert len(validated.relationships) == expected_rels_count
    if expected_rels_count > 0:
        assert validated.relationships[0].source_id == relationships[0].source_id
