from core.ontology import registry

SCHEMA_MAP = registry.get_schema_map()

PRIMARY_IDENTITY_PROPERTY = "id"


def get_standard_label(raw_label: str) -> str:
    return registry.resolve_entity_label(raw_label)


def get_standard_rel(raw_rel: str) -> str:
    return registry.resolve_relationship_type(raw_rel)


def get_mapped_label(raw_label: str) -> str:
    return get_standard_label(raw_label)
