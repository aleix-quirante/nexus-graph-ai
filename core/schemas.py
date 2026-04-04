from pydantic import BaseModel, ConfigDict, Field

from core.ontology import AllowedNodeLabels


class Node(BaseModel):
    """
    Nodo del grafo con validación estricta B2B 2026.
    - strict=True: Sin coerción de tipos
    - extra="forbid": Rechaza campos no declarados
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    id: str = Field(
        ...,
        min_length=1,
        max_length=255,
        pattern=r"^[a-z0-9_]+$",
        description="ID único, normalizado en snake_case y minúsculas (ej. 'empresa_techcorp'). Crucial para enlaces.",
    )
    label: AllowedNodeLabels = Field(
        ...,
        description="Categoría semántica obligatoria del nodo, validada contra el Enum AllowedNodeLabels.",
    )
    properties: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict,
        description="Diccionario clave-valor con los metadatos literales extraídos. Tipos explícitos: str, int, float, bool, None.",
    )


class Relationship(BaseModel):
    """
    Relación entre nodos con validación estricta B2B 2026.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    source_id: str = Field(
        ...,
        min_length=1,
        pattern=r"^[a-z0-9_]+$",
        description="ID exacto del nodo de origen (debe coincidir con un ID de nodo extraído).",
    )
    target_id: str = Field(
        ...,
        min_length=1,
        pattern=r"^[a-z0-9_]+$",
        description="ID exacto del nodo de destino (debe coincidir con un ID de nodo extraído).",
    )
    type: str = Field(
        ...,
        min_length=1,
        pattern=r"^[A-Z][A-Z0-9_]*$",
        description="Tipo de relación en UPPERCASE_SNAKE_CASE (ej. 'FIRMO_CONTRATO', 'CONTIENE_RIESGO').",
    )
    properties: dict[str, str | int | float | bool | None] = Field(
        default_factory=dict, description="Metadatos de la relación (ej. 'fecha')."
    )


class GraphExtraction(BaseModel):
    """
    Resultado de extracción de grafo con validación estricta.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    nodes: list[Node] = Field(
        ..., min_length=0, description="Lista de todos los nodos detectados."
    )
    relationships: list[Relationship] = Field(
        ...,
        min_length=0,
        description="Lista de relaciones lógicas que conectan los nodos.",
    )
