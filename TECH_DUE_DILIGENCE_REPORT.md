# TECH DUE DILIGENCE REPORT: NEXUS-GRAPH-AI (AUDIT 2026-Q2)
**AUDITOR:** Principal Staff Engineer & Lead Security Auditor (IA Distributed Infra)
**ESTADO:** RECHAZADO PARA PRODUCCIÓN TIER-1

### 1. ANÁLISIS DE BRECHAS CRÍTICAS Y VULNERABILIDADES

*   **Soberanía de Identidad Fallida (mTLS Spoofing):** La dependencia crítica en la cabecera `X-SSL-Client-Verify` (`api/main.py:45`) para validar mTLS es una vulnerabilidad de nivel arquitectónico. Cualquier actor con acceso a la red interna (o un contenedor comprometido en el mismo pod) puede inyectar esta cabecera y saltarse el perímetro de seguridad. En 2026, una arquitectura Enterprise debe realizar la validación del certificado directamente en el runtime o mediante un sidecar de Service Mesh (Istio/Linkerd) con política de denegación por defecto.
*   **RBAC por Cabeceras (Security by Header):** El uso de `X-MCP-Role` en `api/mcp.py:256` para diferenciar entre roles `admin` y `agent` es un antipatrón de seguridad flagrante. No existe una validación criptográfica de la identidad del agente, lo que permite la escalada de privilegios trivial mediante la manipulación de cabeceras HTTP.
*   **Inyección de Cypher de Ejecución Remota:** La herramienta `query_subgraph` (`api/mcp.py:152`) acepta una cadena `cypher_query` arbitraria. Aunque se use `execute_read`, un ataque de *Indirect Prompt Injection* puede forzar al agente a ejecutar consultas Cypher maliciosas que agoten los recursos de la base de datos (DoS) o exfiltren el esquema completo mediante procedimientos APOC si están habilitados.
*   **Exfiltración de PII en Fallback de Nube:** El mecanismo de conmutación por error en `core/multi_agent.py:177` redirige las consultas a Gemini Pro cuando falla el proveedor local. El sistema falla al no integrar una etapa de limpieza obligatoria de PII/PHI (Sanitization) *antes* de enviar los datos a la nube pública, violando normativas de soberanía de datos (GDPR/HIPAA 2026).
*   **Condiciones de Carrera Distribuidas:** El `OntologyLockManager` (`core/concurrency.py:28`) utiliza un timeout de bloqueo de 10s. En operaciones de escritura masivas en Neo4j (`core/database.py:113`), si la transacción supera los 10s por latencia de red o carga en el disco, el bloqueo se libera automáticamente, permitiendo escrituras concurrentes que corromperán el estado del grafo a pesar del uso de *fencing tokens*.

### 2. DEUDA TÉCNICA Y ANTIPATRONES

*   **Operaciones No Atómicas (Graph Pollution):** En `api/mcp.py:101`, la función `_execute_edge_mutation` realiza un `MERGE` de nodos antes de crear la relación. Si la creación de la relación falla (por ejemplo, debido a un token de fencing obsoleto), los nodos "huérfanos" permanecen en la base de datos. Esto viola la integridad transaccional y ensucia la ontología empresarial con datos parciales.
*   **Terminación de Grafo Heurística e Inmadura:** El enrutamiento en `core/multi_agent.py:325` decide la terminación basándose en `len(response) > 10`. Este es un criterio amateur que no garantiza la calidad de la respuesta ni previene ciclos infinitos en flujos multi-agente complejos. Se requiere una evaluación semántica o un nodo de revisión dedicado (LLM Judge) con lógica de parada determinista.
*   **Acoplamiento de Configuraciones:** Aunque se utiliza `pydantic-settings`, el sistema carece de una integración nativa con proveedores de secretos (HashiCorp Vault, AWS Secrets Manager) en tiempo de ejecución. Las claves de API y credenciales de base de datos se gestionan como variables de entorno, lo cual es inaceptable para auditorías SOC2 Tipo II.
*   **Gestión de Excepciones Genéricas:** El uso extensivo de `try...except Exception` en capas críticas de la API (`api/main.py:92`, `api/mcp.py:243`) oculta errores de sistema (como fallos de segmentación o errores de conexión de bajo nivel) y complica la observabilidad en escenarios de post-mortem.

### 3. INFRAESTRUCTURA, RESILIENCIA Y DAY 2 OPERATIONS

*   **Observabilidad de "Caja Negra":** La implementación de OpenTelemetry (`core/observability.py`) utiliza una modificación directa de atributos internos (`_attributes`), lo cual es frágil. Además, la telemetría es puramente técnica y carece de métricas de negocio críticas: coste de tokens por tenant, latencia fraccionada por etapa del agente (RAG vs Reasoning) y trazabilidad inmutable para auditorías forenses de IA.
*   **Probes de Salud de Alto Costo:** El endpoint `/health` (`api/main.py:212`) ejecuta consultas reales en Neo4j y pings en Redis. Usar este endpoint como `LivenessProbe` en Kubernetes bajo carga pesada provocará reinicios en cascada del clúster si las bases de datos experimentan latencia transitoria. Se requiere una separación entre `Liveness` (estado del proceso) y `Readiness` (capacidad de procesamiento).
*   **Escalado Predictivo Inexistente:** El uso de `ACTIVE_AI_TASKS` para el escalado con KEDA es un buen comienzo, pero al ser un Gauge local (`prometheus_client.Gauge`), la métrica es inconsistente en despliegues con múltiples réplicas detrás de un balanceador. Se requiere un contador distribuido en Redis para un escalado horizontal (HPA) preciso.
*   **Topología de Red Zero-Trust:** La arquitectura carece de definiciones de `NetworkPolicies` y políticas de servicio que impidan el movimiento lateral. Los componentes (FastAPI, Redis, Neo4j) asumen confianza mutua una vez dentro de la red del clúster.

### 4. TOOLING ENTERPRISE MANDATORIO

Para alcanzar los estándares de ingeniería Fortune 500, se prescribe la integración inmediata de:

1.  **Validación Estática Estricta:** Migración obligatoria a `mypy --strict` y uso de `Pydantic V2` con `strict=True` para evitar la coerción de tipos silenciosa en modelos de datos de misión crítica.
2.  **Seguridad de Suministro (Supply Chain Security):** Integración de `Snyk` o `Trivy` en el pipeline de CI/CD para el escaneo de vulnerabilidades en dependencias y capas de contenedores en tiempo real.
3.  **Frameworks de Guardrails Robustos:** Reemplazar el `SLMGuard` artesanal por `Guardrails AI` o `NeMo Guardrails`, configurados para detectar ataques de inyección de prompt complejos, jailbreaks y alucinaciones semánticas.
4.  **Resiliencia de Red y Caos:** Implementación de `Chaos Mesh` para validar la tolerancia a fallos bizantinos y particiones de red entre Redis y Neo4j, asegurando que el sistema pueda operar bajo el SLA del 99.99%.
5.  **Gestión de Secretos Dinámicos:** Integración con `HashiCorp Vault` mediante el patrón de Sidecar Injection para rotación de credenciales sin reinicio de pods y encriptación de secretos en tránsito y en reposo.
6.  **Tracing Distribuido Multi-Tenant:** Configuración de `Jaeger` o `Honeycomb` con soporte para propagación de contexto de tenant-ID en todas las llamadas asíncronas de LangGraph para análisis de costes y performance granular.
