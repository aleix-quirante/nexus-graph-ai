import asyncio
from unittest.mock import AsyncMock

import pytest

from api.mcp import handle_call_tool, set_mcp_db_driver
from core.ontology import lock_manager


class MockSession:
    def __init__(self, concurrency_state):
        self.concurrency_state = concurrency_state
        self._in_transaction = False

    async def __aenter__(self):
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        pass

    async def execute_write(self, query_func):
        # We simulate the Neo4j execute_write behavior but add race condition detection
        # If locks fail, multiple coroutines could enter execute_write concurrently
        assert not self.concurrency_state["in_write"], (
            "🚨 RACE CONDITION DETECTADA: Múltiples escrituras simultáneas en sesión"
        )
        self.concurrency_state["in_write"] = True

        # Simulate execution time to force race conditions if locks are missing
        await asyncio.sleep(0.05)

        try:
            # We mock the tx object
            tx = AsyncMock()
            tx.run.return_value = AsyncMock()
            tx.run.return_value.single.return_value = {"record": "mocked"}

            result = await query_func(tx)

            self.concurrency_state["success_count"] += 1
            return result
        finally:
            self.concurrency_state["in_write"] = False


class MockDriver:
    def __init__(self, concurrency_state):
        self.concurrency_state = concurrency_state

    def session(self):
        return MockSession(self.concurrency_state)


@pytest.mark.asyncio
async def test_ontology_distributed_lock_concurrency() -> None:
    # State tracking to detect race conditions and successful mutations
    concurrency_state = {"in_write": False, "success_count": 0}

    mock_driver = MockDriver(concurrency_state)
    set_mcp_db_driver(mock_driver)  # type: ignore

    # Force the local lock fallback if Redis is not configured, to guarantee test execution
    if lock_manager.redis is None:
        await lock_manager.connect()

    async def agent_task(agent_id: int):
        payload = {
            "source_id": "empresa_central",
            "target_id": f"persona_{agent_id}",
            "edge_type": "NUEVO_ESQUEMA_DINAMICO",  # They all compete for the same schema lock
            "properties": {"agent_id": agent_id, "confidence_score": 0.95},
        }
        return await handle_call_tool("write_graph_edge", payload)

    # Launch 10 concurrent agents
    tasks = [agent_task(i) for i in range(10)]

    results = await asyncio.gather(*tasks, return_exceptions=True)

    # Check for exceptions
    for res in results:
        if isinstance(res, Exception):
            pytest.fail(f"Agent failed with exception: {res}")

    # The success_count should be exactly 10, meaning all 10 serialized successfully
    assert concurrency_state["success_count"] == 10, (
        f"Expected 10 serialized executions, got {concurrency_state['success_count']}"
    )
    assert not concurrency_state["in_write"], (
        "Transaction flag was left True, possible state leak"
    )
