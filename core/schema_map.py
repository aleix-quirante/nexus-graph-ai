SCHEMA_MAP = {
    "labels": {
        "EMPRESA": ["e", "PROVEEDOR", "CLIENTE", "SOCIEDAD"],
        "PEDIDO": ["p", "ORDEN", "ENCARGO", "PRODUCTO"],
        "RIESGO": ["r", "PROBLEMA", "ALERTA", "RETRASO"],
        "EMPLEADO": ["persona", "COMERCIAL", "RESPONSABLE"],
    },
    "relationships": {
        "REALIZA_PEDIDO": ["HACE_PEDIDO", "TIENE_PEDIDO", "COMPRA", "SOLICITA"],
        "ATIENDE_PEDIDO": ["TIENE_PRECIO", "SUMINISTRA", "PROVEE"],
        "TIENE_RIESGO": ["CONTIENE_RIESGO", "RIESGO_DETECTADO"],
        "ASIGNADO_A": ["LLEVA_CUENTA", "RESPONSABLE_DE"],
    },
    "properties": {
        "id": ["nombre", "name", "identificador", "entidad"],
        "monto": ["precio", "presupuesto", "coste", "valor"],
        "descripcion": ["nota", "detalle", "observacion"],
    },
}

PRIMARY_IDENTITY_PROPERTY = "id"


def get_standard_label(raw_label: str) -> str:
    """
    Devuelve la clave estándar del diccionario si el raw_label está en su lista de valores.
    """
    if not raw_label:
        return ""

    raw_upper = raw_label.upper()

    for standard_key, aliases in SCHEMA_MAP["labels"].items():
        if raw_upper == standard_key:
            return standard_key
        if raw_upper in [alias.upper() for alias in aliases]:
            return standard_key

    return raw_upper


def get_standard_rel(raw_rel: str) -> str:
    """
    Devuelve la clave estándar del diccionario si el raw_rel está en su lista de valores.
    """
    if not raw_rel:
        return ""

    raw_upper = raw_rel.upper()

    for standard_key, aliases in SCHEMA_MAP.get("relationships", {}).items():
        if raw_upper == standard_key:
            return standard_key
        if raw_upper in [alias.upper() for alias in aliases]:
            return standard_key

    return raw_upper


# Alias para mantener la compatibilidad con otras partes del código que usan get_mapped_label
def get_mapped_label(raw_label: str) -> str:
    return get_standard_label(raw_label)
