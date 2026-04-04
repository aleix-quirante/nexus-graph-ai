from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, create_model


class AllowedNodeLabels(str, Enum):
    Company = "Company"
    Person = "Person"
    Contract = "Contract"
    Technology = "Technology"


class EntitySchema(BaseModel):
    """
    Esquema de entidad con validación estricta B2B 2026.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    name: str = Field(..., min_length=1, max_length=100)
    aliases: list[str] = Field(default_factory=list)
    description: str = Field(default="", max_length=1000)
    properties: dict[str, type] = Field(default_factory=dict)
    valid_from: datetime = Field(default_factory=datetime.utcnow)
    valid_until: datetime | None = Field(default=None)
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)


class RelationshipSchema(BaseModel):
    """
    Esquema de relación con validación estricta B2B 2026.
    """

    model_config = ConfigDict(strict=True, extra="forbid")

    name: str = Field(..., min_length=1, max_length=100)
    aliases: list[str] = Field(default_factory=list)
    description: str = Field(default="", max_length=1000)
    allowed_sources: list[str] = Field(default_factory=list)
    allowed_targets: list[str] = Field(default_factory=list)
    valid_from: datetime = Field(default_factory=datetime.utcnow)
    valid_until: datetime | None = Field(default=None)
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0)


class OntologyRegistry:
    def __init__(self):
        self._entities: dict[str, EntitySchema] = {}
        self._relationships: dict[str, RelationshipSchema] = {}

    def register_entity(self, schema: EntitySchema):
        self._entities[schema.name.upper()] = schema

    def register_relationship(self, schema: RelationshipSchema):
        self._relationships[schema.name.upper()] = schema

    def get_entity(self, name: str) -> EntitySchema | None:
        return self._entities.get(name.upper())

    def get_relationship(self, name: str) -> RelationshipSchema | None:
        return self._relationships.get(name.upper())

    def resolve_entity_label(self, raw_label: str) -> str:
        if not raw_label:
            return ""
        raw_upper = raw_label.upper()
        if raw_upper in self._entities:
            return raw_upper
        for name, schema in self._entities.items():
            if raw_upper in [alias.upper() for alias in schema.aliases]:
                return name
        return raw_upper

    def resolve_relationship_type(self, raw_type: str) -> str:
        if not raw_type:
            return ""
        raw_upper = raw_type.upper()
        if raw_upper in self._relationships:
            return raw_upper
        for name, schema in self._relationships.items():
            if raw_upper in [alias.upper() for alias in schema.aliases]:
                return name
        return raw_upper

    def generate_pydantic_models(self) -> dict[str, type[BaseModel]]:
        # Generates Pydantic models for strictly validating extracted data
        models = {}
        for name, schema in self._entities.items():
            fields = {
                "id": (str, Field(..., description="Unique ID for this entity")),
                "label": (str, Field(default=name, Literal=name)),
                "properties": (dict[str, Any], Field(default_factory=dict)),
            }
            # For strictness, one could add specific properties based on schema.properties
            model = create_model(f"{name}Node", **fields, __base__=BaseModel)
            models[name] = model
        return models

    def get_schema_map(self) -> dict[str, Any]:
        """Provides a backward-compatible schema map dict."""
        return {
            "labels": {name: schema.aliases for name, schema in self._entities.items()},
            "relationships": {
                name: schema.aliases for name, schema in self._relationships.items()
            },
            "properties": {
                "id": ["nombre", "name", "identificador", "entidad"],
                "monto": ["precio", "presupuesto", "coste", "valor"],
                "descripcion": ["nota", "detalle", "observacion"],
            },
        }


from contextlib import asynccontextmanager

from core.concurrency import OntologyLockManager as DistributedLockManager
from core.config import settings


class OntologyLockManager:
    def __init__(self):
        self.manager = DistributedLockManager(settings.REDIS_URL)

    async def connect(self):
        # Compatibility method
        pass

    @asynccontextmanager
    async def acquire(self, lock_key: str):
        # Map old 'acquire' to new 'acquire_node_lock'
        async with self.manager.acquire_node_lock(lock_key) as token:
            yield token


# Global lock manager instance
lock_manager = OntologyLockManager()

# Instantiate the global registry and populate it with default B2B domain
registry = OntologyRegistry()

registry.register_entity(
    EntitySchema(
        name="EMPRESA",
        aliases=["PROVEEDOR", "CLIENTE", "SOCIEDAD"],
        description="Business entity or company",
    )
)
registry.register_entity(
    EntitySchema(
        name="PEDIDO",
        aliases=["ORDEN", "ENCARGO", "PRODUCTO"],
        description="Order or product request",
    )
)
registry.register_entity(
    EntitySchema(
        name="RIESGO",
        aliases=["PROBLEMA", "ALERTA", "RETRASO"],
        description="Risk or issue",
    )
)
registry.register_entity(
    EntitySchema(
        name="EMPLEADO",
        aliases=["PERSONA", "COMERCIAL", "RESPONSABLE"],
        description="Person or employee",
    )
)

registry.register_relationship(
    RelationshipSchema(
        name="REALIZA_PEDIDO",
        aliases=["HACE_PEDIDO", "TIENE_PEDIDO", "COMPRA", "SOLICITA"],
        allowed_sources=["EMPRESA", "EMPLEADO"],
        allowed_targets=["PEDIDO"],
    )
)
registry.register_relationship(
    RelationshipSchema(
        name="ATIENDE_PEDIDO",
        aliases=["TIENE_PRECIO", "SUMINISTRA", "PROVEE"],
        allowed_sources=["EMPRESA"],
        allowed_targets=["PEDIDO"],
    )
)
registry.register_relationship(
    RelationshipSchema(
        name="TIENE_RIESGO",
        aliases=["CONTIENE_RIESGO", "RIESGO_DETECTADO"],
        allowed_sources=["PEDIDO", "EMPRESA"],
        allowed_targets=["RIESGO"],
    )
)
registry.register_relationship(
    RelationshipSchema(
        name="ASIGNADO_A",
        aliases=["LLEVA_CUENTA", "RESPONSABLE_DE"],
        allowed_sources=["PEDIDO", "EMPRESA"],
        allowed_targets=["EMPLEADO"],
    )
)


class ValidationPipeline:
    def __init__(self, registry: OntologyRegistry):
        self.registry = registry

    def validate_extraction(self, extraction: Any) -> Any:
        # extraction is expected to be GraphExtraction from core.schemas
        for node in extraction.nodes:
            node.label = self.registry.resolve_entity_label(node.label)

        valid_nodes = {node.id: node.label for node in extraction.nodes}

        valid_rels = []
        for rel in extraction.relationships:
            rel.type = self.registry.resolve_relationship_type(rel.type)

            # Strict edge validation (ontology constraints)
            rel_schema = self.registry.get_relationship(rel.type)
            if rel_schema:
                src_label = valid_nodes.get(rel.source_id)
                tgt_label = valid_nodes.get(rel.target_id)

                # If constraints exist, apply them
                if (
                    rel_schema.allowed_sources
                    and src_label
                    and src_label not in rel_schema.allowed_sources
                ):
                    continue  # Skip invalid relationship source
                if (
                    rel_schema.allowed_targets
                    and tgt_label
                    and tgt_label not in rel_schema.allowed_targets
                ):
                    continue  # Skip invalid relationship target

            valid_rels.append(rel)

        extraction.relationships = valid_rels
        return extraction
