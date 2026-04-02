# TECH DUE DILIGENCE REPORT: NEXUS GRAPH AI (AUDIT 2026-Q2)

## 1. ANÁLISIS DE BRECHAS CRÍTICAS Y VULNERABILIDADES
- **Inyección de Prompts Semántica:** Aunque existe un `SLMGuard`, el `fail-open` en `core/security_guardrails.py:109` es inaceptable para SOC2. Si el guardián falla, el sistema permite cualquier entrada.
- **Fencing Tokens inconsistentes:** `core/worker.py:45` utiliza `time.time()` como token, lo cual es propenso a colisiones en sistemas distribuidos de alta frecuencia. `core/concurrency.py` implementa un contador global en Redis, pero el worker no lo consume.
- **Fuga de PII en Observabilidad:** `SecurityAttributeProcessor` en `core/observability.py` intenta filtrar, pero la lista de `raw_payload_keys` es estática y manual. Falta integración con el motor de Presidio para filtrado dinámico antes de exportar trazas.
- **Falta de Validación de Salida en Worker:** El worker extrae grafos (`core/worker.py`) pero no valida la salida semántica contra toxicidad o alucinaciones de seguridad, confiando ciegamente en el `result_type` de Pydantic AI.

## 2. DEUDA TÉCNICA Y ANTIPATRONES
- **Falta de Tipado Estricto:** Ausencia de configuración `mypy --strict`. Varios archivos carecen de anotaciones completas en retornos (`None` vs `NoReturn`).
- **Acoplamiento de Infraestructura:** El `redis_client` en `core/multi_agent.py` está hardcoded (`localhost:6379`), rompiendo la inyectabilidad de configuraciones de `core/config.py`.
- **Idempotencia Frágil:** `check_idempotency_key` en `multi_agent.py` usa un `window_timestamp` que puede causar procesamientos duplicados en los bordes del intervalo.
- **Ciclos en LangGraph:** `route_reasoning` en `core/multi_agent.py` es una función placeholder que siempre devuelve `terminal_node`, no hay lógica real de razonamiento circular o salida condicional basada en calidad.

## 3. INFRAESTRUCTURA Y DAY 2 OPERATIONS
- **Configuración TLS Inconsistente:** `core/config.py` obliga `rediss://` y `neo4j+s://`, pero el `Dockerfile` arranca un servidor Streamlit en el puerto 8000 sin terminación TLS local ni headers de seguridad (HSTS).
- **Observabilidad GenAI:** Los nombres de métricas en `core/multi_agent.py` no siguen estrictamente la convención OTel `gen_ai.client.*` emergente en 2026.
- **Circuit Breaker:** El timeout de 15s en `CircuitBreakerRouter` es arbitrario y no está vinculado a SLAs por cliente/tenant.

## 4. TOOLING ENTERPRISE MANDATORIO
- **SAST/DAST:** Falta integración de `bandit` o `semgrep` en el pipeline de CI (`.github/workflows/security.yml` no analizado pero sospecho incompleto).
- **Secret Management:** Se detectan placeholders vacíos para API Keys en `core/config.py`. Se requiere integración con HashiCorp Vault o AWS Secrets Manager mediante `pydantic-settings`.
- **Estructura de Logs:** Los logs no están estructurados (JSON) de forma nativa, dificultando el parsing en Grafana Loki/ELK.
