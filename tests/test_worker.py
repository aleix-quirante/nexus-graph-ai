import pytest
from pydantic import ValidationError
from pydantic_ai import Agent
from pydantic_ai.models.test import TestModel

from core.worker import process_message_with_recovery, insert_to_neo4j, agent
from core.schemas import GraphExtraction, Node, Relationship


@pytest.mark.asyncio
async def test_auto_recovery_loop_success_after_failure(mocker):
    """
    Test that the auto-recovery loop successfully catches a validation error,
    injects the error context, and completes the extraction on a subsequent attempt.
    """
    content = "Company A signed a contract with Company B."

    # We will mock the agent.run method to raise a ValidationError on the first call,
    # and return a successful result on the second call.

    # Create a mock valid response
    valid_data = GraphExtraction(
        nodes=[
            Node(id="company_a", label="COMPANY", properties={}),
            Node(id="company_b", label="COMPANY", properties={}),
        ],
        relationships=[
            Relationship(
                source_id="company_a",
                target_id="company_b",
                type="SIGNED_CONTRACT",
                properties={},
            )
        ],
    )

    # Create a mock run result
    class MockRunResult:
        def __init__(self, data):
            self.data = data

    # Function to simulate agent behavior
    call_count = 0

    async def mock_run(prompt):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            # First attempt: simulate a validation error
            # We raise a Pydantic ValidationError. To do this, we need to try validating bad data
            try:
                GraphExtraction.model_validate(
                    {"nodes": [{"id": "bad"}], "relationships": []}
                )
            except ValidationError as e:
                raise e
        else:
            # Second attempt: success
            return MockRunResult(valid_data)

    # Mock the agent.run method
    mocker.patch.object(agent, "run", side_effect=mock_run)

    # Execute the function
    result = await process_message_with_recovery(content, max_retries=3)

    # Assertions
    assert call_count == 2
    assert result == valid_data


def test_insert_to_neo4j(caplog):
    valid_data = GraphExtraction(
        nodes=[Node(id="a", label="L", properties={})], relationships=[]
    )
    insert_to_neo4j(valid_data)
    assert "Successfully inserted 1 nodes and 0 relationships to Neo4j." in caplog.text
