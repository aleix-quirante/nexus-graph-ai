import asyncio
import json
from typing import Any, TypedDict

from langgraph.graph import END, StateGraph
from neo4j import AsyncDriver
from pydantic import BaseModel


class ExtractedEntity(BaseModel):
    label: str
    properties: dict[str, Any]


class InferenceState(TypedDict):
    """
    Schema for the LangGraph State.
    """

    seed_node_id: str
    max_depth: int
    context: str  # Condensed context
    attempts: int
    extracted_entities: list[ExtractedEntity]
    confidence_score: float
    error: str | None


async def extract_and_prune_subgraph(
    driver: AsyncDriver, seed_node_id: str, max_depth: int = 2
) -> str:
    """
    Sub-Graph Context Pruning.
    Extracts an n-hop subgraph around a seed node and condenses it by filtering out
    temporal and system metadata (e.g., valid_from, valid_until, confidence_score)
    to fit efficiently into a local Edge LLM context window.
    """
    query = (
        """
    MATCH p=(n {id: $seed_node_id})-[*0..%d]-(m)
    WITH nodes(p) AS ns, relationships(p) AS rs
    UNWIND ns AS node
    WITH collect(DISTINCT node) AS distinct_nodes, rs
    UNWIND rs AS rel
    WITH distinct_nodes, collect(DISTINCT rel) AS distinct_rels
    RETURN distinct_nodes AS nodes, distinct_rels AS rels
    """
        % max_depth
    )

    # To avoid Cypher syntax issues with variable depth, we inject max_depth safely since it's an int.

    async with driver.session() as session:
        result = await session.run(query, seed_node_id=seed_node_id)
        record = await result.single()

    if not record:
        return "{}"

    nodes_raw = record.get("nodes", [])
    rels_raw = record.get("rels", [])

    compact_nodes = []
    compact_rels = []

    # Filter out system and temporal metadata
    exclude_keys = {"valid_from", "valid_until", "confidence_score"}

    for node in nodes_raw:
        if not node:
            continue
        props = dict(node)
        pruned_props = {k: v for k, v in props.items() if k not in exclude_keys}
        labels = list(node.labels) if hasattr(node, "labels") else []
        compact_nodes.append(
            {"id": props.get("id", "unknown"), "labels": labels, "props": pruned_props}
        )

    for rel in rels_raw:
        if not rel:
            continue
        props = dict(rel)
        pruned_props = {k: v for k, v in props.items() if k not in exclude_keys}

        # Depending on the Neo4j driver version, relationships have start_node and end_node properties
        start_id = (
            dict(rel.start_node).get("id", "unknown")
            if hasattr(rel, "start_node")
            else "unknown"
        )
        end_id = (
            dict(rel.end_node).get("id", "unknown")
            if hasattr(rel, "end_node")
            else "unknown"
        )

        compact_rels.append(
            {
                "type": rel.type if hasattr(rel, "type") else "UNKNOWN",
                "start": start_id,
                "end": end_id,
                "props": pruned_props,
            }
        )

    compact_context = {"nodes": compact_nodes, "rels": compact_rels}
    return json.dumps(compact_context, separators=(",", ":"))


# --- Mocks for LLMs ---


async def mock_edge_llm(context: str) -> dict[str, Any]:
    """
    Simulates a local Edge LLM execution.
    May be slow or yield low confidence.
    """
    await asyncio.sleep(0.1)  # Simulate computation
    # In a real scenario, this would call Ollama or Llama.cpp
    return {
        "extracted_entities": [
            {"label": "CONCEPT", "properties": {"name": "EdgeExtracted"}}
        ],
        "confidence_score": 0.90,  # Can be modified in tests via mocking
    }


async def mock_cloud_llm(context: str) -> dict[str, Any]:
    """
    Simulates a fallback to a Cloud LLM (e.g., GPT-4o).
    Highly reliable and high confidence.
    """
    await asyncio.sleep(0.05)
    return {
        "extracted_entities": [
            {"label": "CONCEPT", "properties": {"name": "CloudExtracted"}}
        ],
        "confidence_score": 0.99,
    }


# --- LangGraph Nodes ---


async def edge_inference_node(state: InferenceState) -> InferenceState:
    """
    Main execution node: delegates to the Edge LLM using asyncio.wait_for to prevent blocking.
    """
    state["attempts"] += 1

    try:
        # Enforce strict timeout for Edge LLM (e.g. 0.5s for test purposes)
        result = await asyncio.wait_for(mock_edge_llm(state["context"]), timeout=0.5)

        state["extracted_entities"] = [
            ExtractedEntity(**e) for e in result.get("extracted_entities", [])
        ]
        state["confidence_score"] = result.get("confidence_score", 0.0)
        state["error"] = None

    except TimeoutError:
        state["error"] = "TimeoutError"
        state["confidence_score"] = 0.0
    except Exception as e:
        state["error"] = str(e)
        state["confidence_score"] = 0.0

    return state


async def cloud_fallback_node(state: InferenceState) -> InferenceState:
    """
    Secondary fallback node: executes Cloud LLM when Edge fails or degrades.
    """
    state["attempts"] += 1
    try:
        result = await mock_cloud_llm(state["context"])
        state["extracted_entities"] = [
            ExtractedEntity(**e) for e in result.get("extracted_entities", [])
        ]
        state["confidence_score"] = result.get("confidence_score", 0.0)
        state["error"] = None
    except Exception as e:
        state["error"] = f"Cloud Fallback Error: {str(e)}"

    return state


# --- Conditional Routing ---


def evaluate_inference(state: InferenceState) -> str:
    """
    Conditional routing logic:
    If TimeoutError or confidence < 0.85, route to cloud_fallback.
    Else, finish successfully.
    """
    if state.get("error") == "TimeoutError":
        return "cloud_fallback"
    if state.get("confidence_score", 0.0) < 0.85:
        return "cloud_fallback"
    return "end"


# --- Graph Assembly ---


def build_inference_graph() -> StateGraph:
    """
    Builds and compiles the Inference Routing Graph.
    """
    workflow = StateGraph(InferenceState)

    workflow.add_node("edge_inference", edge_inference_node)
    workflow.add_node("cloud_fallback", cloud_fallback_node)

    workflow.set_entry_point("edge_inference")

    workflow.add_conditional_edges(
        "edge_inference",
        evaluate_inference,
        {"cloud_fallback": "cloud_fallback", "end": END},
    )

    workflow.add_edge("cloud_fallback", END)

    return workflow.compile()
