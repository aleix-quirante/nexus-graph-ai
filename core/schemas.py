from pydantic import BaseModel, Field
from typing import List, Dict, Any
from core.ontology import AllowedNodeLabels


class Node(BaseModel):
    id: str = Field(
        ...,
        description="ID único, normalizado en snake_case y minúsculas (ej. 'empresa_techcorp'). Crucial para enlaces.",
    )
    label: AllowedNodeLabels = Field(
        ...,
        description="Categoría semántica obligatoria del nodo, validada contra el Enum AllowedNodeLabels.",
    )
    properties: Dict[str, Any] = Field(
        default_factory=dict,
        description="Diccionario clave-valor con los metadatos literales extraídos.",
    )


class Relationship(BaseModel):
    source_id: str = Field(
        ...,
        description="ID exacto del nodo de origen (debe coincidir con un ID de nodo extraído).",
    )
    target_id: str = Field(
        ...,
        description="ID exacto del nodo de destino (debe coincidir con un ID de nodo extraído).",
    )
    type: str = Field(
        ...,
        description="Tipo de relación en UPPERCASE_SNAKE_CASE (ej. 'FIRMO_CONTRATO', 'CONTIENE_RIESGO').",
    )
    properties: Dict[str, Any] = Field(
        default_factory=dict, description="Metadatos de la relación (ej. 'fecha')."
    )


class GraphExtraction(BaseModel):
    nodes: List[Node] = Field(..., description="Lista de todos los nodos detectados.")
    relationships: List[Relationship] = Field(
        ..., description="Lista de relaciones lógicas que conectan los nodos."
    )
