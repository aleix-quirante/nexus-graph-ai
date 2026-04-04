import json
import os
import traceback

from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_ai import Agent

from core.database import GraphRepository, Neo4jClient
from core.schema_map import SCHEMA_MAP
from core.security_guardrails import SecurityEnforcer, SecurityGuardrailViolation


class CypherResponse(BaseModel):
    query: str = Field(
        ...,
        description="Consulta Cypher válida de solo lectura (MATCH, RETURN). NUNCA usar MERGE o CREATE.",
    )
    explanation: str = Field(
        ..., description="Explicación ejecutiva de 1 línea de lo que hace la consulta."
    )


CYPHER_AGENT_PROMPT_TEMPLATE = """
Eres un experto en Cypher. Cuentas con un SCHEMA_MAP que define que EMPRESA puede aparecer como e, PROVEEDOR o CLIENTE. 
Al generar la consulta, si el usuario pregunta por una empresa, busca en todas esas etiquetas.
SCHEMA_MAP de referencia: {schema_map}

El esquema actual de la base de datos es:
Nodos detectados: {labels}
Relaciones detectadas: {relationships}
Propiedades disponibles: {properties}
Genera la consulta basada estrictamente en este esquema.
REGLAS CRÍTICAS:
1. Búsqueda Infalible: La consulta generada debe ser flexible y resistente a fallos de caracteres. Usa SIEMPRE una sola palabra clave (la más distintiva del nombre, ej. si es 'Construcciones Aleix', usa SOLO 'aleix'). Nunca busques el nombre entero con espacios. Usa: WHERE toLower(n.id) CONTAINS 'aleix' OR toLower(n.nombre) CONTAINS 'aleix'.
2. Para preguntas sobre 'qué material', 'qué pedido' o 'qué pasa con...', busca relaciones bidireccionales genéricas (ej. MATCH (e:EMPRESA)-[r]-(p:PEDIDO)). Esto evita fallos de dirección o saltos variables. Ten en cuenta que en este esquema, el nodo de tipo PEDIDO representa tanto el pedido como el material en sí mismo.
3. Usa comodines o nodos genéricos sin dirección (MATCH (n)-[r]-(m)) cuando no sepas exactamente qué etiqueta tiene o si puede haber varias relaciones. Ejemplo: MATCH (n)-[r]-(m) WHERE toLower(n.id) CONTAINS toLower('aleix') RETURN n, r, m
4. SINTAXIS CYPHER: NUNCA uses llaves para las etiquetas de los nodos. Las etiquetas de los nodos van sin llaves ni comillas. Ejemplo CORRECTO: (e:EMPRESA). Ejemplo INCORRECTO: (e:{{EMPRESA}}).
5. NUNCA uses expresiones de ruta de longitud variable con tipos múltiples (como `[:A|B*1..2]`), ya que puede causar errores sintácticos o retornos vacíos en algunas bases de datos. Si necesitas ambos, simplemente usa `-[r]-` y filtra después si es necesario.
6. REGLA ABSOLUTA DE SINTAXIS PARA PROPIEDADES: NUNCA USES `EXISTS(variable.propiedad)` ni `exists(variable.propiedad)`. Está prohibido y obsoleto en Neo4j. Usa SIEMPRE `variable.propiedad IS NOT NULL` en su lugar.
7. NO BUSQUES LITERALES INÚTILES. NUNCA HAGAS UN WHERE CON `operacion`, `proyecto` O `presupuesto`. Las operaciones, proyectos y presupuestos están modelados mediante las propiedades (ej. `n.monto`). Si preguntan por dinero o presupuesto, busca TODOS los nodos que tengan `monto`. Ejemplo EXACTO y ÚNICO a generar: `MATCH (n) WHERE n.monto IS NOT NULL RETURN n.id, n.monto`.
8. NO INVENTES PROPIEDADES O RELACIONES EN EL MATCH. Retorna solo las que sabemos que existen según el esquema. Si buscas dinero, usa la propiedad `n.monto`, NO busques una relación `[:PRESUPUESTO]`.
9. EXPLORACIÓN CRÍTICA: Cuando el usuario haga una pregunta abierta (ej. 'por qué', 'qué pasa con', 'resumen', motivos o riesgos), NO te limites a los vecinos directos. Debes explorar a 2 saltos de distancia para encontrar la causa raíz. Usa este patrón exacto: MATCH (n)-[r1]-(m) OPTIONAL MATCH (m)-[r2]-(k) WHERE toLower(n.id) CONTAINS 'valor' OR toLower(n.nombre) CONTAINS 'valor' RETURN n.id AS origen, type(r1) AS rel1, m.id AS intermedio, type(r2) AS rel2, k.id AS destino, k.descripcion AS detalle_destino LIMIT 20
10. ANTI-ALUCINACIÓN EN CONTEOS: Si se te pide contar elementos específicos (ej. camiones, empleados), busca SOLO nodos o propiedades que coincidan semánticamente con ese concepto. NUNCA cuentes relaciones genéricas `COUNT(n)` asumiendo que son lo que el usuario busca. Si el concepto no existe en tu SCHEMA_MAP o en el grafo, la consulta debe devolver vacío o 0. Es preferible decir 'no hay datos' que inventar.
11. EXCLUSIONES Y GRAFOS INVERSOS: Para preguntas que impliquen la ausencia de algo (ej. pedidos SIN riesgo, entidades QUE NO tienen X), NUNCA uses UNION ni UNION ALL. Usa siempre el patrón de negación de Cypher y NUNCA introduzcas variables ni etiquetas en el nodo destino dentro de NOT: `MATCH (n:PEDIDO) WHERE NOT (n)-[:TIENE_RIESGO]-() RETURN n`. Repito: el nodo destino en el NOT debe ser `()` vacío, sin `(r:RIESGO)`.
"""


class GraphQueryEngine:
    def __init__(self, client: GraphRepository | None = None):
        if client is None:
            load_dotenv(override=True)
            self.client = Neo4jClient(
                os.getenv("NEO4J_URI", ""),
                os.getenv("NEO4J_USER", ""),
                os.getenv("NEO4J_PASSWORD", ""),
            )
        else:
            self.client = client

        self.security = SecurityEnforcer()
        self.answer_agent = Agent(
            "openai:qwen2.5:32b",
            system_prompt=(
                "Eres un analista de datos B2B experto. "
                "Usa los datos JSON obtenidos de la base de datos para responder a la pregunta del usuario. "
                "Si los datos están vacíos, indica que no se encontró información relevante. "
                "SIEMPRE debes responder en el mismo idioma en el que se te hace la pregunta."
            ),
        )

    async def query(self, user_question: str) -> str:
        try:
            # 1. Input Security Layer (Sanitization & Guardrails)
            print("🛡️ Validando integridad de entrada...")
            sanitized_question = await self.security.sanitize_input(user_question)
            if sanitized_question != user_question:
                print(f"⚠️ PII detectado y redactado: '{sanitized_question}'")

            schema = await self.client.get_schema_snapshot()

            prompt = CYPHER_AGENT_PROMPT_TEMPLATE.format(
                schema_map=SCHEMA_MAP,
                labels=schema.get("labels", []),
                relationships=schema.get("relationships", []),
                properties=schema.get("properties", []),
            )

            cypher_agent = Agent(
                "openai:qwen2.5:32b",
                output_type=CypherResponse,
                system_prompt=prompt,
            )

            print(f"🧠 Analizando intención corporativa: '{sanitized_question}'")
            result = await cypher_agent.run(
                f"Pregunta del usuario: {sanitized_question}. Genera el Cypher."
            )
            # Support both .data and .output based on pydantic-ai version
            cypher_data = getattr(result, "data", getattr(result, "output", None))

            if not cypher_data:
                print("❌ No se pudo extraer la consulta Cypher.")
                return "Error: No se pudo generar la consulta Cypher."

            print(f"⚙️ Cypher Generado: {cypher_data.query}")
            print(f"📝 Razón: {cypher_data.explanation}")

            # Force idempotency with a read-only transaction and context manager
            async with self.client.driver.session(
                default_access_mode="READ"
            ) as session:
                records = await session.run(cypher_data.query)
                data = [record.data() async for record in records]

                print("\n📊 RESULTADOS DETERMINISTAS:")
                print(json.dumps(data, indent=2, ensure_ascii=False))

                print("\n🤖 SINTETIZANDO RESPUESTA FINAL...")
                final_response = await self.answer_agent.run(
                    f"Pregunta del usuario: {sanitized_question}\n\nDatos de la DB: {json.dumps(data, ensure_ascii=False)}"
                )

                answer_data = getattr(
                    final_response, "data", getattr(final_response, "output", "")
                )

                # 2. Output Security Layer (Validation)
                print("🛡️ Validando integridad de salida...")
                validated_answer = await self.security.validate_llm_output(answer_data)

                print(f"\n✨ RESPUESTA:\n{validated_answer}")
                return validated_answer
        except SecurityGuardrailViolation as e:
            print(f"🚨 Bloqueo de Seguridad (Gatekeeper): {str(e)}")
            return "Error de Seguridad: La consulta ha sido bloqueada por políticas corporativas."
        except Exception as e:
            print(f"❌ Error crítico en Engine: {str(e)}")
            traceback.print_exc()
            return f"Error: {str(e)}"

    async def close(self):
        await self.client.close()
