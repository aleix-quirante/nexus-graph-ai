# Immutable registry of pre-approved parameterized queries
ALLOWED_CYPHER_TEMPLATES: dict[str, str] = {
    "get_node_neighbors": """
        MATCH (n {id: $node_id})-[r]-(m)
        RETURN type(r) as relation, m.id as neighbor_id, m.type as neighbor_type
        LIMIT 50
    """,
    "check_path_exists": """
        MATCH p=shortestPath((start {id: $start_id})-[:*1..3]-(end {id: $end_id}))
        RETURN length(p) as distance
    """,
}


def get_safe_query(intent: str) -> str:
    """Validates the requested intent and returns the corresponding static Cypher string."""
    if intent not in ALLOWED_CYPHER_TEMPLATES:
        raise ValueError(f"Unauthorized query intent: {intent}")
    return ALLOWED_CYPHER_TEMPLATES[intent]
