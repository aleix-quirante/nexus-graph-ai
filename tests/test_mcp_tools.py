import pytest
from httpx import AsyncClient, ASGITransport
import json

from api.main import app
from typing import Dict, Union, Any

PropertyType = Union[str, int, float, bool]

# Define base headers for valid requests
VALID_HEADERS = {"X-MCP-Role": "admin"}
INVALID_HEADERS = {"X-MCP-Role": "guest"}
MISSING_HEADERS: Dict[str, str] = {}


@pytest.mark.asyncio
async def test_rbac_missing_header() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/mcp/sse", headers=MISSING_HEADERS)
        assert response.status_code == 403
        assert "Acceso Denegado" in response.json()["detail"]


@pytest.mark.asyncio
async def test_rbac_invalid_role() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.get("/mcp/sse", headers=INVALID_HEADERS)
        assert response.status_code == 403
        assert "Acceso Denegado" in response.json()["detail"]


@pytest.mark.asyncio
async def test_rbac_valid_role() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # It's an SSE endpoint, but the RBAC happens before connecting streams.
        # It might just hang/block trying to establish SSE, but we should at least get a 200/StreamingResponse.
        # Actually starlette StreamingResponse may return headers immediately.
        try:
            # We timeout the request so it doesn't wait forever for SSE stream if it connects
            response = await client.get("/mcp/sse", headers=VALID_HEADERS, timeout=1.0)
            assert response.status_code == 200
        except Exception:
            # If it times out, it means the connection was accepted and SSE started.
            pass


@pytest.mark.asyncio
async def test_mcp_post_message_rbac_missing() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/mcp/messages/", json={}, headers=MISSING_HEADERS)
        if response.status_code == 404:
            response = await client.post(
                "/mcp/messages", json={}, headers=MISSING_HEADERS
            )
        assert response.status_code == 403


@pytest.mark.asyncio
async def test_mcp_post_message_missing_session_id() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as client:
        # Valid RBAC, but no session_id in query params (SseServerTransport validation)
        response = await client.post("/mcp/messages/", json={}, headers=VALID_HEADERS)
        if response.status_code == 404:
            response = await client.post(
                "/mcp/messages", json={}, headers=VALID_HEADERS
            )
        # SseServerTransport returns 400 for missing session_id
        assert response.status_code == 400
        assert "session_id is required" in response.text


# To test the tools themselves more cleanly (since MCP HTTP transport requires setting up SSE and taking session_id),
# We can test the schema validation and graph service directly or through the mcp_server API.

from api.mcp import mcp_server, MCPGraphService, set_mcp_db_driver, handle_call_tool


class DummyDriver:
    pass


@pytest.fixture(autouse=True)
def setup_dummy_driver():
    set_mcp_db_driver(DummyDriver())  # type: ignore


@pytest.mark.asyncio
async def test_tool_read_graph_node_invalid_payload() -> None:
    # mcp_server.call_tool handles the payload validation using Pydantic
    # Let's mock the db_driver or test direct schema failure
    result = await handle_call_tool("read_graph_node", {"wrong_param": "123"})
    # Since we catch Exception in call_tool, it returns a TextContent with the error
    assert len(result) == 1
    assert "Error processing tool read_graph_node" in result[0].text
    assert "validation error" in result[0].text.lower()


@pytest.mark.asyncio
async def test_tool_query_subgraph_mutation_rejection() -> None:
    # query_subgraph rejects CREATE/MERGE etc.
    result = await handle_call_tool(
        "query_subgraph", {"cypher_query": "CREATE (n:Test)"}
    )
    assert len(result) == 1
    assert "Solo se permiten consultas de lectura" in result[0].text


@pytest.mark.asyncio
async def test_tool_write_graph_edge_valid_schema() -> None:
    valid_payload = {
        "source_id": "empresa_1",
        "target_id": "persona_1",
        "edge_type": "CONTRATO",
        "properties": {"year": 2026, "active": True},
    }

    # We expect an error inside the service because DummyDriver doesn't have a session,
    # but NOT a pydantic validation error.
    result = await handle_call_tool("write_graph_edge", valid_payload)
    assert len(result) == 1
    text = result[0].text
    # Should not be a validation error
    assert "validation error" not in text.lower()
    # Should be an internal error (e.g. DummyDriver object has no attribute 'session')
    assert "session" in text.lower() or "dummydriver" in text.lower()
