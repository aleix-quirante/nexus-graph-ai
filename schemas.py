from pydantic import BaseModel
from typing import List, Dict, Any


class Node(BaseModel):
    id: str
    type: str
    properties: Dict[str, Any]


class Relationship(BaseModel):
    id: str
    type: str
    start_node_id: str
    end_node_id: str
    properties: Dict[str, Any]


class GraphData(BaseModel):
    nodes: List[Node]
    relationships: List[Relationship]


class GraphExtraction(BaseModel):
    data: GraphData
