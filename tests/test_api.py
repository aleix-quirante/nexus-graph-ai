import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from api.main import app, db


@pytest.fixture
def mock_neo4j():
    with patch("api.main.AsyncGraphDatabase.driver") as mock_driver:
        mock_instance = AsyncMock()
        mock_driver.return_value = mock_instance
        yield mock_instance


@pytest.mark.asyncio
async def test_health_check(mock_neo4j):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_mcp_discover(mock_neo4j):
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://test"
    ) as ac:
        response = await ac.get("/mcp/discover")
    assert response.status_code == 200
    assert response.json() == {"schema": {}}
