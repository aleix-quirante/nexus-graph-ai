import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient

# Mock setup_telemetry and FastAPIInstrumentor before importing main
with (
    patch("core.observability.setup_telemetry") as mock_setup_telemetry,
    patch(
        "api.main.FastAPIInstrumentor.instrument_app", create=True
    ) as mock_instrument,
):
    from api.main import app

client = TestClient(app)


def test_health_check():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok", "system": "Nexus Graph AI Core"}


def test_mcp_discover():
    response = client.get("/mcp/discover")
    assert response.status_code == 200
    assert response.json() == {"schema": {}}
