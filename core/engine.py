import os
import json
import traceback
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from pydantic_ai import Agent
from core.database import Neo4jClient
from core.schema_map import SCHEMA_MAP


class CypherResponse(BaseModel):
    query: str = Field(
        ...,
        description="Consulta Cypher válida de solo lectura (MATCH, RETURN). NUNCA usar MERGE o CREATE.",
    )
    explanation: str = Field(
        ..., description="Explicación ejecutiva de 1 línea de lo que hace la consulta."
    )


class GraphQueryEngine:
    def __init__(self):
        load_dotenv(override=True)
        self.client = Neo4jClient(
            os.getenv("NEO4J_URI", ""),
            os.getenv("NEO4J_USER", ""),
            os.getenv("NEO4J_PASSWORD", ""),
        )
        self.answer_agent = Agent(
            "openai:qwen2.5:32b",
            system_prompt=(
                "Eres un analista de datos B2B experto. "
                "Usa los datos JSON obtenidos de la base de datos para responder a la pregunta del usuario. "
                "Si los datos están vacíos, indica que no se encontró información relevante. "
                "SIEMPRE debes responder en el mismo idioma en el que se te hace la pregunta."
            ),
        )

    async def query(self, user_question: str):
        try:
            schema = self.client.get_schema_snapshot()

            cypher_agent = Agent(
                "openai:qwen2.5:32b",
                output_type=CypherResponse,
                system_prompt=(
                    "Eres un experto en Cypher. Cuentas con un SCHEMA_MAP que define que EMPRESA puede aparecer como e, PROVEEDOR o CLIENTE. "
                    "Al generar la consulta, si el usuario pregunta por una empresa, busca en todas esas etiquetas.\n"
                    f"SCHEMA_MAP de referencia: {SCHEMA_MAP}\n\n"
                    "El esquema actual de la base de datos es:\n"
                    f"Nodos detectados: {schema['labels']}\n"
                    f"Relaciones detectadas: {schema['relationships']}\n"
                    f"Propiedades disponibles: {schema['properties']}\n"
                    "Genera la consulta basada estrictamente en este esquema.\n"
                    "REGLAS CRÍTICAS:\n"
                    "1. Búsqueda Infalible: La consulta generada debe ser flexible y resistente a fallos de caracteres. Usa SIEMPRE una sola palabra clave (la más distintiva del nombre, ej. si es 'Construcciones Aleix', usa SOLO 'aleix'). Nunca busques el nombre entero con espacios. Usa: "
                    "WHERE toLower(n.id) CONTAINS 'aleix' OR toLower(n.nombre) CONTAINS 'aleix'.\n"
                    "2. Para preguntas sobre 'qué material', 'qué pedido' o 'qué pasa con...', busca relaciones bidireccionales genéricas (ej. MATCH (e:EMPRESA)-[r]-(p:PEDIDO)). Esto evita fallos de dirección o saltos variables. Ten en cuenta que en este esquema, el nodo de tipo PEDIDO representa tanto el pedido como el material en sí mismo (ej. 'pedido_vigas_acero').\n"
                    "3. Usa comodines o nodos genéricos sin dirección (MATCH (n)-[r]-(m)) cuando no sepas exactamente qué etiqueta tiene o si puede haber varias relaciones. Ejemplo: MATCH (n)-[r]-(m) WHERE toLower(n.id) CONTAINS toLower('aleix') RETURN n, r, m\n"
                    "4. SINTAXIS CYPHER: NUNCA uses llaves para las etiquetas de los nodos. Las etiquetas de los nodos van sin llaves ni comillas. Ejemplo CORRECTO: (e:EMPRESA). Ejemplo INCORRECTO: (e:{EMPRESA}).\n"
                    "5. NUNCA uses expresiones de ruta de longitud variable con tipos múltiples (como `[:A|B*1..2]`), ya que puede causar errores sintácticos o retornos vacíos en algunas bases de datos. Si necesitas ambos, simplemente usa `-[r]-` y filtra después si es necesario.\n"
                    "6. REGLA ABSOLUTA DE SINTAXIS PARA PROPIEDADES: NUNCA USES `EXISTS(variable.propiedad)` ni `exists(variable.propiedad)`. Está prohibido y obsoleto en Neo4j. Usa SIEMPRE `variable.propiedad IS NOT NULL` en su lugar.\n"
                    "7. NO BUSQUES LITERALES INÚTILES. NUNCA HAGAS UN WHERE CON `operacion`, `proyecto` O `presupuesto` (ni en IDs, ni en nombres, ni en tipos de relación). Las operaciones, proyectos y presupuestos están modelados mediante las propiedades (ej. `n.monto`). Si preguntan por dinero o presupuesto, busca TODOS los nodos que tengan `monto`. Ejemplo EXACTO y ÚNICO a generar: `MATCH (n) WHERE n.monto IS NOT NULL RETURN n.id, n.monto`.\n"
                    "8. NO INVENTES PROPIEDADES O RELACIONES EN EL MATCH. Retorna solo las que sabemos que existen según el esquema. Si buscas dinero, usa la propiedad `n.monto`, NO busques una relación `[:PRESUPUESTO]` ni hagas un `WHERE r.tipo CONTAINS 'presupuesto'`.\n"
                    "9. EXPLORACIÓN CRÍTICA: Cuando el usuario haga una pregunta abierta (ej. 'por qué', 'qué pasa con', 'resumen', motivos o riesgos), NO te limites a los vecinos directos. Debes explorar a 2 saltos de distancia para encontrar la causa raíz. Usa este patrón exacto: "
                    "MATCH (n)-[r1]-(m) OPTIONAL MATCH (m)-[r2]-(k) WHERE toLower(n.id) CONTAINS 'valor' OR toLower(n.nombre) CONTAINS 'valor' "
                    "RETURN n.id AS origen, type(r1) AS rel1, m.id AS intermedio, type(r2) AS rel2, k.id AS destino, k.descripcion AS detalle_destino LIMIT 20\n"
                    "10. ANTI-ALUCINACIÓN EN CONTEOS: Si se te pide contar elementos específicos (ej. camiones, empleados), busca SOLO nodos o propiedades que coincidan semánticamente con ese concepto. NUNCA cuentes relaciones genéricas `COUNT(n)` asumiendo que son lo que el usuario busca. Si el concepto no existe en tu SCHEMA_MAP o en el grafo, la consulta debe devolver vacío o 0. Es preferible decir 'no hay datos' que inventar.\n"
                    "11. EXCLUSIONES Y GRAFOS INVERSOS: Para preguntas que impliquen la ausencia de algo (ej. pedidos SIN riesgo, entidades QUE NO tienen X), NUNCA uses UNION ni UNION ALL. Usa siempre el patrón de negación de Cypher y NUNCA introduzcas variables ni etiquetas en el nodo destino dentro de NOT: `MATCH (n:PEDIDO) WHERE NOT (n)-[:TIENE_RIESGO]-() RETURN n`. Repito: el nodo destino en el NOT debe ser `()` vacío, sin `(r:RIESGO)`.\n"
                ),
            )

            print(f"🧠 Analizando intención corporativa: '{user_question}'")
            result = await cypher_agent.run(
                f"Pregunta del usuario: {user_question}. Genera el Cypher."
            )
            # Support both .data and .output based on pydantic-ai version
            cypher_data = getattr(result, "data", getattr(result, "output", None))

            if not cypher_data:
                print("❌ No se pudo extraer la consulta Cypher.")
                return

            print(f"⚙️ Cypher Generado: {cypher_data.query}")
            print(f"📝 Razón: {cypher_data.explanation}")

            with self.client.driver.session() as session:
                records = session.run(cypher_data.query)
                data = records.data()
                print("\n📊 RESULTADOS DETERMINISTAS:")
                print(json.dumps(data, indent=2, ensure_ascii=False))

                print("\n🤖 SINTETIZANDO RESPUESTA FINAL...")
                final_response = await self.answer_agent.run(
                    f"Pregunta del usuario: {user_question}\n\nDatos de la DB: {json.dumps(data, ensure_ascii=False)}"
                )

                answer_data = getattr(
                    final_response, "data", getattr(final_response, "output", "")
                )
                print(f"\n✨ RESPUESTA:\n{answer_data}")
                return answer_data
        except Exception as e:
            print(f"❌ Error crítico en Engine: {str(e)}")
            traceback.print_exc()
            return f"Error: {str(e)}"

    def close(self):
        self.client.close()
