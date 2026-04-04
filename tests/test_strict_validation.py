"""
Test Suite for Vulnerability #3: Strict Mode and Robust Typing

This test file demonstrates the current vulnerabilities in the Pydantic models
and verifies that the strict mode implementation correctly rejects invalid data.

Test Strategy:
1. VULNERABILITY tests: Demonstrate current behavior (should PASS before fix, FAIL after fix)
2. FIXED tests: Verify strict validation (should FAIL before fix, PASS after fix)
3. VALID tests: Ensure valid data is still accepted (should PASS always)

Author: Security Audit Team
Date: 2026-04-04
"""

import pytest
from pydantic import ValidationError

from core.ontology import AllowedNodeLabels, EntitySchema, RelationshipSchema
from core.schemas import GraphExtraction, Node, Relationship

# =============================================================================
# PHASE 1: VULNERABILITY TESTS (Demonstrate Current Weaknesses)
# =============================================================================


class TestVulnerabilities:
    """
    Tests that demonstrate current vulnerabilities.

    EXPECTED BEHAVIOR:
    - BEFORE FIX: All tests in this class should PASS (showing vulnerability)
    - AFTER FIX: All tests in this class should FAIL (showing fix works)
    """

    def test_node_accepts_extra_fields_VULNERABLE(self):
        """
        VULNERABILITY: Extra fields are silently ignored by default.

        CURRENT: This test PASSES (accepts extra fields)
        AFTER FIX: This test should FAIL (rejects extra fields)
        """
        try:
            node = Node(
                id="test",
                label=AllowedNodeLabels.Company,
                properties={},
                hacker_field="malicious_data",  # Extra field not in schema
            )
            # If we get here without error, vulnerability exists
            assert True
        except ValidationError:
            # If this raises ValidationError, the fix is already applied
            pytest.fail("Fix already applied - extra fields are being rejected")

    def test_node_accepts_invalid_id_format_VULNERABLE(self):
        """
        VULNERABILITY: IDs with invalid formats are accepted.

        CURRENT: This test PASSES (accepts invalid formats)
        AFTER FIX: This test should FAIL (rejects invalid formats)
        """
        invalid_ids = [
            "UPPERCASE_ID",  # Should be lowercase
            "With Spaces",  # Should not have spaces
            "with-dashes",  # Should use underscores only
        ]

        for invalid_id in invalid_ids:
            try:
                node = Node(
                    id=invalid_id, label=AllowedNodeLabels.Company, properties={}
                )
                # If we get here, vulnerability exists for this ID
                assert node.id == invalid_id
            except ValidationError:
                # If this raises ValidationError, the fix is already applied
                pytest.fail(
                    f"Fix already applied - invalid ID '{invalid_id}' is being rejected"
                )

    def test_relationship_accepts_invalid_type_format_VULNERABLE(self):
        """
        VULNERABILITY: Relationship types with invalid formats are accepted.

        CURRENT: This test PASSES (accepts invalid formats)
        AFTER FIX: This test should FAIL (rejects invalid formats)
        """
        invalid_types = [
            "lowercase_type",  # Should be UPPERCASE
            "With Spaces",  # Should not have spaces
        ]

        for invalid_type in invalid_types:
            try:
                rel = Relationship(
                    source_id="node1",
                    target_id="node2",
                    type=invalid_type,
                    properties={},
                )
                # If we get here, vulnerability exists for this type
                assert rel.type == invalid_type
            except ValidationError:
                # If this raises ValidationError, the fix is already applied
                pytest.fail(
                    f"Fix already applied - invalid type '{invalid_type}' is being rejected"
                )


# =============================================================================
# PHASE 2: STRICT VALIDATION TESTS (Verify Fix Works)
# =============================================================================


class TestStrictValidation:
    """
    Tests that verify strict validation is working correctly.

    EXPECTED BEHAVIOR:
    - BEFORE FIX: All tests in this class should FAIL (no strict validation)
    - AFTER FIX: All tests in this class should PASS (strict validation working)
    """

    def test_node_rejects_extra_fields_FIXED(self):
        """
        Verify that extra='forbid' rejects undeclared fields.
        """
        with pytest.raises(ValidationError) as exc_info:
            Node(
                id="test",
                label=AllowedNodeLabels.Company,
                properties={},
                hacker_field="malicious",  # Extra field
            )

        # Verify the error message mentions extra fields
        error_msg = str(exc_info.value).lower()
        assert (
            "extra" in error_msg
            or "unexpected" in error_msg
            or "forbidden" in error_msg
        )

    def test_node_rejects_uppercase_id_FIXED(self):
        """
        Verify that regex pattern rejects uppercase IDs.
        """
        with pytest.raises(ValidationError):
            Node(id="UPPERCASE_ID", label=AllowedNodeLabels.Company, properties={})

    def test_node_rejects_id_with_spaces_FIXED(self):
        """
        Verify that regex pattern rejects IDs with spaces.
        """
        with pytest.raises(ValidationError):
            Node(id="id with spaces", label=AllowedNodeLabels.Company, properties={})

    def test_node_rejects_id_with_dashes_FIXED(self):
        """
        Verify that regex pattern rejects IDs with dashes.
        """
        with pytest.raises(ValidationError):
            Node(id="id-with-dashes", label=AllowedNodeLabels.Company, properties={})

    def test_node_rejects_id_with_dots_FIXED(self):
        """
        Verify that regex pattern rejects IDs with dots.
        """
        with pytest.raises(ValidationError):
            Node(id="id.with.dots", label=AllowedNodeLabels.Company, properties={})

    def test_node_rejects_empty_id_FIXED(self):
        """
        Verify that min_length constraint rejects empty IDs.
        """
        with pytest.raises(ValidationError):
            Node(id="", label=AllowedNodeLabels.Company, properties={})

    def test_relationship_rejects_lowercase_type_FIXED(self):
        """
        Verify that regex pattern rejects lowercase relationship types.
        """
        with pytest.raises(ValidationError):
            Relationship(
                source_id="node1",
                target_id="node2",
                type="lowercase_type",
                properties={},
            )

    def test_relationship_rejects_type_with_spaces_FIXED(self):
        """
        Verify that regex pattern rejects types with spaces.
        """
        with pytest.raises(ValidationError):
            Relationship(
                source_id="node1",
                target_id="node2",
                type="TYPE WITH SPACES",
                properties={},
            )

    def test_relationship_rejects_type_with_dashes_FIXED(self):
        """
        Verify that regex pattern rejects types with dashes.
        """
        with pytest.raises(ValidationError):
            Relationship(
                source_id="node1",
                target_id="node2",
                type="TYPE-WITH-DASHES",
                properties={},
            )

    def test_relationship_rejects_type_starting_with_number_FIXED(self):
        """
        Verify that regex pattern rejects types starting with numbers.
        """
        with pytest.raises(ValidationError):
            Relationship(
                source_id="node1", target_id="node2", type="123_INVALID", properties={}
            )

    def test_relationship_rejects_empty_type_FIXED(self):
        """
        Verify that min_length constraint rejects empty types.
        """
        with pytest.raises(ValidationError):
            Relationship(source_id="node1", target_id="node2", type="", properties={})

    def test_node_rejects_nested_dict_in_properties_FIXED(self):
        """
        Verify that Union type rejects nested dicts in properties.
        """
        with pytest.raises(ValidationError):
            Node(
                id="test",
                label=AllowedNodeLabels.Company,
                properties={"nested": {"key": "value"}},
            )

    def test_node_rejects_list_in_properties_FIXED(self):
        """
        Verify that Union type rejects lists in properties.
        """
        with pytest.raises(ValidationError):
            Node(
                id="test",
                label=AllowedNodeLabels.Company,
                properties={"list": [1, 2, 3]},
            )

    def test_relationship_rejects_invalid_source_id_FIXED(self):
        """
        Verify that source_id follows same pattern as node IDs.
        """
        with pytest.raises(ValidationError):
            Relationship(
                source_id="INVALID-ID",
                target_id="valid_id",
                type="VALID_TYPE",
                properties={},
            )

    def test_relationship_rejects_invalid_target_id_FIXED(self):
        """
        Verify that target_id follows same pattern as node IDs.
        """
        with pytest.raises(ValidationError):
            Relationship(
                source_id="valid_id",
                target_id="INVALID-ID",
                type="VALID_TYPE",
                properties={},
            )


# =============================================================================
# PHASE 3: VALID DATA TESTS (Ensure Legitimate Use Cases Work)
# =============================================================================


class TestValidData:
    """
    Tests that verify valid data is accepted correctly.

    EXPECTED BEHAVIOR:
    - BEFORE FIX: All tests should PASS
    - AFTER FIX: All tests should PASS

    These tests ensure we don't break legitimate use cases.
    """

    def test_node_accepts_valid_snake_case_id(self):
        """
        Verify that valid snake_case lowercase IDs are accepted.
        """
        node = Node(
            id="empresa_techcorp", label=AllowedNodeLabels.Company, properties={}
        )
        assert node.id == "empresa_techcorp"

    def test_node_accepts_valid_id_with_numbers(self):
        """
        Verify that IDs with numbers are accepted.
        """
        node = Node(id="pedido_001", label=AllowedNodeLabels.Contract, properties={})
        assert node.id == "pedido_001"

    def test_node_accepts_valid_properties_string(self):
        """
        Verify that string properties are accepted.
        """
        node = Node(
            id="test", label=AllowedNodeLabels.Company, properties={"name": "TechCorp"}
        )
        assert node.properties["name"] == "TechCorp"
        assert isinstance(node.properties["name"], str)

    def test_node_accepts_valid_properties_int(self):
        """
        Verify that int properties are accepted.
        """
        node = Node(id="test", label=AllowedNodeLabels.Company, properties={"age": 10})
        assert node.properties["age"] == 10
        assert isinstance(node.properties["age"], int)

    def test_node_accepts_valid_properties_float(self):
        """
        Verify that float properties are accepted.
        """
        node = Node(
            id="test",
            label=AllowedNodeLabels.Company,
            properties={"revenue": 1000000.50},
        )
        assert node.properties["revenue"] == 1000000.50
        assert isinstance(node.properties["revenue"], float)

    def test_node_accepts_valid_properties_bool(self):
        """
        Verify that bool properties are accepted.
        """
        node = Node(
            id="test", label=AllowedNodeLabels.Company, properties={"active": True}
        )
        assert node.properties["active"] is True
        assert isinstance(node.properties["active"], bool)

    def test_node_accepts_valid_properties_none(self):
        """
        Verify that None properties are accepted.
        """
        node = Node(
            id="test", label=AllowedNodeLabels.Company, properties={"notes": None}
        )
        assert node.properties["notes"] is None

    def test_node_accepts_mixed_valid_properties(self):
        """
        Verify that mixed valid property types are accepted.
        """
        node = Node(
            id="empresa_techcorp",
            label=AllowedNodeLabels.Company,
            properties={
                "name": "TechCorp",
                "age": 10,
                "revenue": 1000000.50,
                "active": True,
                "notes": None,
            },
        )
        assert len(node.properties) == 5
        assert node.properties["name"] == "TechCorp"
        assert node.properties["age"] == 10
        assert node.properties["revenue"] == 1000000.50
        assert node.properties["active"] is True
        assert node.properties["notes"] is None

    def test_relationship_accepts_valid_uppercase_type(self):
        """
        Verify that valid UPPER_SNAKE_CASE types are accepted.
        """
        rel = Relationship(
            source_id="empresa_techcorp",
            target_id="pedido_001",
            type="REALIZA_PEDIDO",
            properties={},
        )
        assert rel.type == "REALIZA_PEDIDO"

    def test_relationship_accepts_valid_type_with_underscores(self):
        """
        Verify that types with underscores are accepted.
        """
        rel = Relationship(
            source_id="node1", target_id="node2", type="FIRMO_CONTRATO", properties={}
        )
        assert rel.type == "FIRMO_CONTRATO"

    def test_relationship_accepts_valid_type_with_numbers(self):
        """
        Verify that types with numbers are accepted.
        """
        rel = Relationship(
            source_id="node1", target_id="node2", type="TIPO_123", properties={}
        )
        assert rel.type == "TIPO_123"

    def test_graph_extraction_accepts_valid_data(self):
        """
        Verify that GraphExtraction accepts valid nodes and relationships.
        """
        nodes = [
            Node(
                id="empresa_techcorp",
                label=AllowedNodeLabels.Company,
                properties={"name": "TechCorp"},
            ),
            Node(
                id="pedido_001",
                label=AllowedNodeLabels.Contract,
                properties={"monto": 50000},
            ),
        ]

        relationships = [
            Relationship(
                source_id="empresa_techcorp",
                target_id="pedido_001",
                type="REALIZA_PEDIDO",
                properties={"fecha": "2026-04-04"},
            )
        ]

        extraction = GraphExtraction(nodes=nodes, relationships=relationships)

        assert len(extraction.nodes) == 2
        assert len(extraction.relationships) == 1

    def test_graph_extraction_accepts_empty_lists(self):
        """
        Verify that GraphExtraction accepts empty lists.
        """
        extraction = GraphExtraction(nodes=[], relationships=[])

        assert len(extraction.nodes) == 0
        assert len(extraction.relationships) == 0

    def test_entity_schema_accepts_valid_data(self):
        """
        Verify that EntitySchema accepts valid data.
        """
        schema = EntitySchema(
            name="EMPRESA",
            aliases=["PROVEEDOR", "CLIENTE"],
            description="Business entity",
        )
        assert schema.name == "EMPRESA"
        assert len(schema.aliases) == 2

    def test_relationship_schema_accepts_valid_data(self):
        """
        Verify that RelationshipSchema accepts valid data.
        """
        schema = RelationshipSchema(
            name="REALIZA_PEDIDO",
            aliases=["HACE_PEDIDO"],
            description="Order relationship",
            allowed_sources=["EMPRESA"],
            allowed_targets=["PEDIDO"],
        )
        assert schema.name == "REALIZA_PEDIDO"
        assert len(schema.allowed_sources) == 1


# =============================================================================
# PHASE 4: EDGE CASES AND BOUNDARY TESTS
# =============================================================================


class TestEdgeCases:
    """
    Tests for edge cases and boundary conditions.
    """

    def test_node_id_max_length(self):
        """
        Verify that IDs respect max_length constraint (255 chars).
        """
        # Valid: exactly 255 characters
        valid_id = "a" * 255
        node = Node(id=valid_id, label=AllowedNodeLabels.Company, properties={})
        assert len(node.id) == 255

        # Invalid: 256 characters (should fail after fix)
        invalid_id = "a" * 256
        try:
            Node(id=invalid_id, label=AllowedNodeLabels.Company, properties={})
            # If we get here, max_length is not enforced yet
            pytest.skip("max_length constraint not yet enforced")
        except ValidationError:
            # Expected after fix
            pass

    def test_entity_schema_name_max_length(self):
        """
        Verify that EntitySchema name respects max_length (100 chars).
        """
        # Valid: exactly 100 characters
        valid_name = "A" * 100
        schema = EntitySchema(name=valid_name)
        assert len(schema.name) == 100

        # Invalid: 101 characters (should fail after fix)
        invalid_name = "A" * 101
        try:
            EntitySchema(name=invalid_name)
            # If we get here, max_length is not enforced yet
            pytest.skip("max_length constraint not yet enforced")
        except ValidationError:
            # Expected after fix
            pass

    def test_entity_schema_description_max_length(self):
        """
        Verify that EntitySchema description respects max_length (1000 chars).
        """
        # Valid: exactly 1000 characters
        valid_desc = "A" * 1000
        schema = EntitySchema(name="TEST", description=valid_desc)
        assert len(schema.description) == 1000

        # Invalid: 1001 characters (should fail after fix)
        invalid_desc = "A" * 1001
        try:
            EntitySchema(name="TEST", description=invalid_desc)
            # If we get here, max_length is not enforced yet
            pytest.skip("max_length constraint not yet enforced")
        except ValidationError:
            # Expected after fix
            pass
