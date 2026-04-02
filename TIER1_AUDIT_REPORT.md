# TECH DUE DILIGENCE REPORT: NEXUS GRAPH AI (FORTUNE 500 TIER-1 AUDIT)

## 1. ANÁLISIS DE BRECHAS CRÍTICAS Y VULNERABILIDADES
- **Inyección de Prompts y Envenenamiento de Contexto:** El sistema depende de un `SLMGuard` que, antes de mi intervención, fallaba en abierto (`fail-open`). Las trazas de LangGraph no implementan validación de integridad criptográfica en cada salto de nodo, permitiendo la manipulación del historial del agente en memoria compartida (Redis).
- **Fallo de Consistencia en Fencing Tokens:** El uso de `time.time()` en el worker para transacciones de Neo4j es un error catastrófico. En condiciones de alta concurrencia o deriva de reloj en el clúster, esto garantiza escrituras fuera de orden y corrupción del grafo de conocimiento.
- **Exfiltración de PII durante Failover:** El `CircuitBreakerRouter` redirige consultas a la nube (Gemini Pro) cuando falla el proveedor local. Si el prompt original contiene PII no sanitizada, se produce una violación inmediata de GDPR/SOC2 al enviar datos sensibles a una infraestructura externa no autorizada específicamente para ese tenant.
- **Inseguridad en MCP (Model Context Protocol):** La capa MCP carece de sandboxing de ejecución. Si un agente es inducido a llamar a una herramienta con parámetros maliciosos (Prompt Injection Indirecta), puede ejecutar comandos arbitrarios en el host si no hay un aislamiento estricto (gVisor/Firecracker).

## 2. DEUDA TÉCNICA Y ANTIPATRONES
- **Gestión Negligente de Estados en Redis:** Se observan TTLs inconsistentes. La falta de un `Distributed State Manager` robusto hace que el orquestador LangGraph sea susceptible a ciclos infinitos si un nodo de "reasoning" falla de forma no determinista y no hay un `recursion_limit` forzado por lógica de negocio.
- **Violación de Idempotencia:** Las mutaciones en Neo4j no son atómicas respecto al estado de Redis. Un fallo tras escribir en Neo4j pero antes de actualizar el lock en Redis deja el sistema en un estado bizantino.
- **Tipado Laxo:** A pesar de usar Python 3.10, la falta de `mypy --strict` permite el paso de tipos `Any` en puntos críticos de la orquestación, ocultando bugs de lógica en la transformación de esquemas de grafos.

## 3. INFRAESTRUCTURA, RESILIENCIA Y DAY 2 OPS
- **Topología K8s Insuficiente:** El `ScaledObject` de KEDA es demasiado simple. No considera métricas de "backpressure" de Kafka ni latencia P99 de los LLMs. Se requiere un HPA basado en métricas custom de OTel.
- **Observabilidad Inmadura:** La implementación de OpenTelemetry no captura el `Time To First Token (TTFT)` de forma granular por proveedor, impidiendo auditorías de SLA en tiempo real. Falta un registro inmutable de decisiones del agente (Audit Trail) para cumplimiento regulatorio.
- **Zero-Trust:** Aunque se valida mTLS en el API Gateway, la comunicación interna entre el Worker y Neo4j/Redis no impone rotación de certificados ni identidades SPIFFE/SPIRE.

## 4. TOOLING ENTERPRISE MANDATORIO
- **Barreras de Seguridad (Guardrails):** Es imperativo integrar NeMo Guardrails o un motor OPA (Open Policy Agent) para validar cada transición de estado del agente.
- **Análisis de Seguridad Continuo:** Integración obligatoria de `Semgrep` (reglas pro para LLMs) y `Trivy` para escaneo de vulnerabilidades en el runtime de contenedores.
- **Chaos Engineering:** Implementación de LitmusChaos o Gremlin para validar la resiliencia ante particiones de red entre los nodos de Redis que gestionan la concurrencia.
