import logging
from contextvars import ContextVar
from typing import Dict, List, Union, Any, Optional
import re

from fastapi import APIRouter, Request, HTTPException, Depends
from starlette.responses import Response

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from mcp.server.models import InitializationOptions
from pydantic import BaseModel, Field

from core.ontology import AllowedNodeLabels
from core.concurrency import OntologyLockManager
from core.config import settings
from core.auth import verify_cryptographic_identity, TokenPayload
from core.cypher_templates import get_safe_query, ALLOWED_CYPHER_TEMPLATES

from neo4j import AsyncDriver
from neo4j.exceptions import TransientError, ClientError

logger = logging.getLogger(__name__)

# Context for Zero-Trust role propagation
current_token: ContextVar[Optional[TokenPayload]] = ContextVar(
    "current_token", default=None
)

PropertyType = Union[str, int, float, bool]

# --- Pydantic Schemas ---


class ReadGraphNodeInput(BaseModel):
    node_id: str = Field(..., description="ID del nodo a leer del grafo")


class WriteGraphEdgeInput(BaseModel):
    source_id: str = Field(..., description="ID del nodo origen")
    target_id: str = Field(..., description="ID del nodo destino")
    edge_type: str = Field(
        ..., description="Tipo de relacion en formato UPPERCASE_SNAKE_CASE"
    )
    properties: Dict[str, PropertyType] = Field(
        default_factory=dict, description="Propiedades extra para la relacion"
    )


class QuerySubgraphInput(BaseModel):
    intent_name: str = Field(..., description="Nombre de la consulta pre-aprobada")
    parameters: Dict[str, Any] = Field(
        default_factory=dict, description="Parametros de la consulta"
    )


class GraphNodeOutput(BaseModel):
    id: str
    label: AllowedNodeLabels
    properties: Dict[str, PropertyType]


class GraphEdgeOutput(BaseModel):
    source_id: str
    target_id: str
    type: str
    properties: Dict[str, PropertyType]


class QueryOutput(BaseModel):
    records: List[Dict[str, PropertyType]]


# --- Abstraction Layer ---

lock_manager = OntologyLockManager(settings.REDIS_URL)


class MCPGraphService:
    def __init__(self, driver: AsyncDriver):
        self.driver = driver

    async def read_node(self, node_id: str) -> GraphNodeOutput:
        query = "MATCH (n {id: $node_id}) RETURN labels(n) as labels, n as properties"
        async with self.driver.session() as session:
            result = await session.run(query, node_id=node_id)
            record = await result.single()
            if not record:
                raise ValueError(f"Node {node_id} not found")

            props = dict(record["properties"])
            label = record["labels"][0] if record["labels"] else "UNKNOWN"
            filtered_props = {
                k: v for k, v in props.items() if isinstance(v, (str, int, float, bool))
            }
            return GraphNodeOutput(id=node_id, label=label, properties=filtered_props)

    async def write_edge(
        self,
        source_id: str,
        target_id: str,
        edge_type: str,
        properties: Dict[str, PropertyType],
    ) -> GraphEdgeOutput:

        async def _execute_edge_mutation(tx, fencing_token: int):
            # Check if nodes exist (dummy creation of nodes to emulate dynamic ontology expansion if they don't exist)
            query_nodes = """
            MERGE (a:DYNAMIC_NODE {id: $source_id})
            MERGE (b:DYNAMIC_NODE {id: $target_id})
            """
            await tx.run(query_nodes, source_id=source_id, target_id=target_id)

            # Optimistic Concurrency Control using MERGE and Enterprise Fencing Tokens.
            # Only perform the write if the current node/edge doesn't have a newer token.
            query = (
                f"MATCH (a {{id: $source_id}}), (b {{id: $target_id}}) "
                f"MERGE (a)-[r:`{edge_type}`]->(b) "
                "WITH r "
                "WHERE coalesce(r.last_fencing_token, 0) < $fencing_token "
                "SET r += $properties, r.last_fencing_token = $fencing_token "
                "RETURN r"
            )
            result = await tx.run(
                query,
                source_id=source_id,
                target_id=target_id,
                properties=properties,
                fencing_token=fencing_token,
            )
            return await result.single()

        # Replaced global async lock with Redlock + Fencing Tokens manager.
        # This provides distributed serialization and protects against stale writes.
        try:
            async with lock_manager.acquire_edge_locks(source_id, target_id) as token:
                async with self.driver.session() as session:
                    record = await session.execute_write(_execute_edge_mutation, token)
                    if not record:
                        logger.warning(
                            f"Write rejected: Stale token {token} for edge {source_id}->{target_id}"
                        )
                        raise ValueError(
                            f"Transaction rejected: A newer update (higher fencing token) has already been processed for this edge."
                        )
        except (ClientError, TransientError) as e:
            logger.error(f"Error during edge creation: {e}")
            raise ValueError(f"Failed to create edge due to database error: {e}")

        return GraphEdgeOutput(
            source_id=source_id,
            target_id=target_id,
            type=edge_type,
            properties=properties,
        )

    async def query_subgraph(
        self, intent_name: str, parameters: Dict[str, Any] | None = None
    ) -> QueryOutput:
        if parameters is None:
            parameters = {}

        # Retrieve the static, safe query template
        safe_cypher = get_safe_query(intent_name)

        # 2. Execute with forced parameterized query approach
        async with self.driver.session() as session:
            # Using read_transaction to strictly enforce read-only at database level as well
            async def _execute_read(tx):
                result = await tx.run(safe_cypher, parameters)
                return await result.values()

            records = await session.execute_read(_execute_read)

            output_records: List[Dict[str, PropertyType]] = []
            for idx, r in enumerate(records):
                output_records.append({"result_index": idx, "value": str(r)})

            return QueryOutput(records=output_records)


# --- MCP Server ---
mcp_server = Server("nexus-graph-mcp")


@mcp_server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return [
        Tool(
            name="read_graph_node",
            description="Lee las propiedades y etiqueta de un nodo especifico usando su ID",
            inputSchema=ReadGraphNodeInput.model_json_schema(),
        ),
        Tool(
            name="write_graph_edge",
            description="Escribe una nueva relacion direccional entre dos nodos existentes",
            inputSchema=WriteGraphEdgeInput.model_json_schema(),
        ),
        Tool(
            name="query_subgraph",
            description="Ejecuta una consulta pre-aprobada del registro de templates",
            inputSchema=QuerySubgraphInput.model_json_schema(),
        ),
    ]


_global_db_driver: AsyncDriver | None = None


def set_mcp_db_driver(driver: AsyncDriver) -> None:
    global _global_db_driver
    _global_db_driver = driver


@mcp_server.call_tool()
async def execute_mcp_action(
    name: str, arguments: Dict[str, PropertyType]
) -> list[TextContent]:
    if not _global_db_driver:
        return [
            TextContent(
                type="text",
                text="Error: Database driver not initialized in MCP context",
            )
        ]

    service = MCPGraphService(_global_db_driver)

    try:
        # Zero-Trust Role Verification: Mutative actions strictly require 'admin'
        if name == "write_graph_edge":
            token = current_token.get()
            if not token or token.role != "admin":
                logger.error(
                    f"RBAC Violation: Subject {token.sub if token else 'UNKNOWN'} attempted write_graph_edge without admin role."
                )
                raise HTTPException(
                    status_code=403,
                    detail="Forbidden: Admin role derived mathematically from token is required for destructive graph mutations.",
                )

        if name == "read_graph_node":
            data = ReadGraphNodeInput.model_validate(arguments)
            out = await service.read_node(data.node_id)
            return [TextContent(type="text", text=out.model_dump_json())]

        elif name == "write_graph_edge":
            data = WriteGraphEdgeInput.model_validate(arguments)
            out = await service.write_edge(
                data.source_id, data.target_id, data.edge_type, data.properties
            )
            return [TextContent(type="text", text=out.model_dump_json())]

        elif name == "query_subgraph":
            data = QuerySubgraphInput.model_validate(arguments)
            out = await service.query_subgraph(data.intent_name, data.parameters)
            return [TextContent(type="text", text=out.model_dump_json())]

        else:
            raise ValueError(f"Unknown tool: {name}")

    except HTTPException:
        raise
    except Exception as e:
        return [
            TextContent(type="text", text=f"Error processing tool {name}: {str(e)}")
        ]


# --- FastAPI Integration & RBAC ---

from starlette.routing import Mount

mcp_router = APIRouter()


sse_transport = SseServerTransport("/mcp/messages")


@mcp_router.get("/sse")
async def mcp_sse(
    request: Request, token: TokenPayload = Depends(verify_cryptographic_identity)
) -> Response:
    token_reset = current_token.set(token)
    try:
        async with sse_transport.connect_sse(
            request.scope, request.receive, request._send
        ) as streams:
            options = InitializationOptions(
                server_name="nexus-graph-mcp",
                server_version="1.0.0",
                capabilities=mcp_server.get_capabilities(),
            )
            await mcp_server.run(streams[0], streams[1], options)
        return Response()
    finally:
        current_token.reset(token_reset)


@mcp_router.post("/messages")
@mcp_router.post("/messages/")
async def mcp_messages(
    request: Request, token: TokenPayload = Depends(verify_cryptographic_identity)
) -> Response:
    token_reset = current_token.set(token)
    try:
        response_data = {"status": 200, "headers": [], "body": b""}

        async def dummy_send(message: dict) -> None:
            if message["type"] == "http.response.start":
                response_data["status"] = message["status"]
                response_data["headers"] = message.get("headers", [])
            elif message["type"] == "http.response.body":
                response_data["body"] += message.get("body", b"")

        await sse_transport.handle_post_message(
            request.scope, request.receive, dummy_send
        )

        headers = {
            k.decode("utf-8"): v.decode("utf-8")
            for k, v in response_data["headers"]
            if k.decode("utf-8").lower() not in ["content-length", "content-type"]
        }

        content_type = "text/plain"
        for k, v in response_data["headers"]:
            if k.decode("utf-8").lower() == "content-type":
                content_type = v.decode("utf-8")

        return Response(
            content=response_data["body"],
            status_code=response_data["status"],
            headers=headers,
            media_type=content_type,
        )
    finally:
        current_token.reset(token_reset)
