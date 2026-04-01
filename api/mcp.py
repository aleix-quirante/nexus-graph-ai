import logging
from typing import Dict, List, Union, Any
import re

from fastapi import APIRouter, Request, HTTPException, Depends
from starlette.responses import Response

from mcp.server import Server
from mcp.server.sse import SseServerTransport
from mcp.types import Tool, TextContent
from mcp.server.models import InitializationOptions
from pydantic import BaseModel, Field

from neo4j import AsyncDriver
from neo4j.exceptions import TransientError, ClientError

logger = logging.getLogger(__name__)

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
    cypher_query: str = Field(
        ..., description="Consulta cypher parametrizada a ejecutar"
    )
    parameters: Dict[str, Any] = Field(
        default_factory=dict, description="Parametros de la consulta"
    )


class GraphNodeOutput(BaseModel):
    id: str
    label: str
    properties: Dict[str, PropertyType]


class GraphEdgeOutput(BaseModel):
    source_id: str
    target_id: str
    type: str
    properties: Dict[str, PropertyType]


class QueryOutput(BaseModel):
    records: List[Dict[str, PropertyType]]


# --- Abstraction Layer ---


class ASTValidator:
    """Static AST-like validation for Cypher queries to ensure read-only operations."""

    ALLOWED_CLAUSES = {
        "MATCH",
        "WITH",
        "WHERE",
        "RETURN",
        "ORDER BY",
        "SKIP",
        "LIMIT",
        "YIELD",
        "UNWIND",
    }
    FORBIDDEN_CLAUSES = {
        "CREATE",
        "MERGE",
        "SET",
        "DELETE",
        "REMOVE",
        "DROP",
        "CALL",
        "LOAD CSV",
        "FOREACH",
    }

    @classmethod
    def validate_read_only(cls, query: str):
        """
        Validates that a Cypher query only contains allowed read operations.
        Uses a simplified static analysis approach.
        """
        # Remove string literals and comments to avoid false positives
        query_stripped = re.sub(r"'[^']*'", "''", query)
        query_stripped = re.sub(r'"[^"]*"', '""', query_stripped)
        query_stripped = re.sub(r"//.*$", "", query_stripped, flags=re.MULTILINE)

        upper_query = query_stripped.upper()

        # Check for forbidden clauses
        for forbidden in cls.FORBIDDEN_CLAUSES:
            # Match whole words to avoid partial matches (e.g., 'MATCH (SETTING)' shouldn't trigger 'SET')
            if re.search(rf"\b{forbidden}\b", upper_query):
                raise ValueError(
                    f"AST Validation Error: Forbidden clause detected '{forbidden}'. Query must be read-only."
                )


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

        async def _execute_edge_mutation(tx):
            # Check if nodes exist (dummy creation of nodes to emulate dynamic ontology expansion if they don't exist)
            query_nodes = """
            MERGE (a:DYNAMIC_NODE {id: $source_id})
            MERGE (b:DYNAMIC_NODE {id: $target_id})
            """
            await tx.run(query_nodes, source_id=source_id, target_id=target_id)

            # Optimistic Concurrency Control using MERGE and internal locking mechanisms of Neo4j.
            # Removed the external async lock_manager in favor of database-level concurrency handling.
            query = (
                f"MATCH (a {{id: $source_id}}), (b {{id: $target_id}}) "
                f"MERGE (a)-[r:`{edge_type}`]->(b) "
                f"SET r += $properties "
                f"RETURN r"
            )
            result = await tx.run(
                query, source_id=source_id, target_id=target_id, properties=properties
            )
            return await result.single()

        # Replaced global async lock with Neo4j's built-in transaction retries and optimistic concurrency
        # which is partition tolerant and safe. execute_write automatically handles retries for TransientErrors.
        async with self.driver.session() as session:
            try:
                record = await session.execute_write(_execute_edge_mutation)
                if not record:
                    raise ValueError(
                        "Could not create edge. Check if source and target nodes exist."
                    )
            except ClientError as e:
                logger.error(f"ClientError during edge creation: {e}")
                raise ValueError(f"Failed to create edge due to client error: {e}")
            except TransientError as e:
                logger.error(f"TransientError during edge creation: {e}")
                raise ValueError(
                    f"Failed to create edge due to transient error (concurrency/network): {e}"
                )

        return GraphEdgeOutput(
            source_id=source_id,
            target_id=target_id,
            type=edge_type,
            properties=properties,
        )

    async def query_subgraph(
        self, cypher: str, parameters: Dict[str, Any] = None
    ) -> QueryOutput:
        if parameters is None:
            parameters = {}

        # 1. Apply static AST validation to ensure read-only
        ASTValidator.validate_read_only(cypher)

        # 2. Execute with forced parameterized query approach
        async with self.driver.session() as session:
            # Using read_transaction to strictly enforce read-only at database level as well
            async def _execute_read(tx):
                result = await tx.run(cypher, parameters)
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
            description="Ejecuta una consulta Cypher parametrizada de solo lectura",
            inputSchema=QuerySubgraphInput.model_json_schema(),
        ),
    ]


_global_db_driver: AsyncDriver | None = None


def set_mcp_db_driver(driver: AsyncDriver) -> None:
    global _global_db_driver
    _global_db_driver = driver


@mcp_server.call_tool()
async def handle_call_tool(name: str, arguments: dict) -> list[TextContent]:
    if not _global_db_driver:
        return [
            TextContent(
                type="text",
                text="Error: Database driver not initialized in MCP context",
            )
        ]

    service = MCPGraphService(_global_db_driver)

    try:
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
            out = await service.query_subgraph(data.cypher_query, data.parameters)
            return [TextContent(type="text", text=out.model_dump_json())]

        else:
            raise ValueError(f"Unknown tool: {name}")

    except Exception as e:
        return [
            TextContent(type="text", text=f"Error processing tool {name}: {str(e)}")
        ]


# --- FastAPI Integration & RBAC ---

from starlette.routing import Mount

mcp_router = APIRouter()


def get_rbac_role(request: Request) -> str:
    role = request.headers.get("X-MCP-Role")
    if not role or role not in ["admin", "agent"]:
        raise HTTPException(
            status_code=403,
            detail="Acceso Denegado: Se requiere un rol valido en X-MCP-Role",
        )
    return role


sse_transport = SseServerTransport("/mcp/messages")


@mcp_router.get("/sse")
async def mcp_sse(request: Request, role: str = Depends(get_rbac_role)) -> Response:
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


@mcp_router.post("/messages")
@mcp_router.post("/messages/")
async def mcp_messages(
    request: Request, role: str = Depends(get_rbac_role)
) -> Response:
    response_data = {"status": 200, "headers": [], "body": b""}

    async def dummy_send(message: dict) -> None:
        if message["type"] == "http.response.start":
            response_data["status"] = message["status"]
            response_data["headers"] = message.get("headers", [])
        elif message["type"] == "http.response.body":
            response_data["body"] += message.get("body", b"")

    await sse_transport.handle_post_message(request.scope, request.receive, dummy_send)

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
