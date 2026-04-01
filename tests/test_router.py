import pytest
import asyncio
from unittest.mock import AsyncMock, patch

from core.router import build_inference_graph, InferenceState, ExtractedEntity


@pytest.fixture
def graph():
    return build_inference_graph()


def init_state() -> InferenceState:
    return {
        "seed_node_id": "test_seed",
        "max_depth": 2,
        "context": '{"nodes":[], "rels":[]}',
        "attempts": 0,
        "extracted_entities": [],
        "confidence_score": 0.0,
        "error": None,
    }


@pytest.mark.asyncio
async def test_router_edge_success(graph):
    """
    Test scenario: Edge LLM returns a high confidence score (> 0.85).
    Expected: Graph finishes after Edge execution without calling Cloud fallback.
    """
    with patch("core.router.mock_edge_llm", new_callable=AsyncMock) as mock_edge:
        mock_edge.return_value = {
            "extracted_entities": [
                {"label": "CONCEPT", "properties": {"name": "EdgeExtracted"}}
            ],
            "confidence_score": 0.95,
        }

        state = init_state()
        result = await graph.ainvoke(state)

        assert result["attempts"] == 1
        assert result["confidence_score"] == 0.95
        assert result["extracted_entities"][0].properties["name"] == "EdgeExtracted"
        assert result["error"] is None


@pytest.mark.asyncio
async def test_router_edge_low_confidence_fallback(graph):
    """
    Test scenario: Edge LLM returns a low confidence score (< 0.85).
    Expected: Graph routes to Cloud LLM fallback.
    """
    with (
        patch("core.router.mock_edge_llm", new_callable=AsyncMock) as mock_edge,
        patch("core.router.mock_cloud_llm", new_callable=AsyncMock) as mock_cloud,
    ):

        mock_edge.return_value = {
            "extracted_entities": [
                {"label": "CONCEPT", "properties": {"name": "EdgeLowConf"}}
            ],
            "confidence_score": 0.70,
        }
        mock_cloud.return_value = {
            "extracted_entities": [
                {"label": "CONCEPT", "properties": {"name": "CloudExtracted"}}
            ],
            "confidence_score": 0.99,
        }

        state = init_state()
        result = await graph.ainvoke(state)

        assert result["attempts"] == 2
        assert result["confidence_score"] == 0.99
        assert result["extracted_entities"][0].properties["name"] == "CloudExtracted"


@pytest.mark.asyncio
async def test_router_edge_timeout_fallback(graph):
    """
    Test scenario: Edge LLM raises TimeoutError.
    Expected: Graph catches TimeoutError, sets error state, and routes to Cloud LLM fallback.
    """
    with (
        patch("core.router.mock_edge_llm", new_callable=AsyncMock) as mock_edge,
        patch("core.router.mock_cloud_llm", new_callable=AsyncMock) as mock_cloud,
    ):

        async def slow_mock_edge(*args, **kwargs):
            raise asyncio.TimeoutError()

        mock_edge.side_effect = slow_mock_edge
        mock_cloud.return_value = {
            "extracted_entities": [
                {"label": "CONCEPT", "properties": {"name": "CloudAfterTimeout"}}
            ],
            "confidence_score": 0.98,
        }

        state = init_state()
        result = await graph.ainvoke(state)

        assert result["attempts"] == 2
        assert result["confidence_score"] == 0.98
        assert result["extracted_entities"][0].properties["name"] == "CloudAfterTimeout"
