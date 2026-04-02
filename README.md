# Nexus Graph AI 

**Enterprise-Grade Knowledge Graph Orchestration Engine**

Nexus Graph AI is a robust, production-ready system engineered to bridge the gap between deterministic knowledge representation and probabilistic Large Language Models. Built for environments where downtime is unacceptable and data integrity is paramount, this platform provides a highly scalable architecture that strictly adheres to zero-trust principles and fail-fast operational paradigms.

---

## 🏗 System Topology & Architecture

Our architecture is strictly typed, highly concurrent, and designed with military-grade precision to guarantee SOC2 readiness and absolute observability.

### 1. LangGraph Orchestration & Multi-Agent Concurrency
At the core of Nexus Graph AI lies a sophisticated multi-agent system powered by **LangGraph**. The workflow orchestrates complex asynchronous state machines that gracefully handle non-deterministic execution paths. This provides:
- **Resilient Execution Pipelines:** Strict graph topologies mapping distinct operational states to deterministic state transitions.
- **Fail-Fast Error Handling:** Immediate circuit breaking and propagation of unrecoverable state anomalies.
- **Micro-batching & Concurrency:** High-throughput task execution managing state across deeply nested multi-agent workflows.
- **Three-Tier LLM Routing & Active Resilience:** A robust Circuit Breaker pattern routes general queries to an efficient local Ollama/Llama-3 model (Tier 1) for privacy and speed. If the local model degrades, fails, or exceeds a 15-second timeout, the system automatically falls back to the Gemini Pro API (Tier 2). Specialized security operations, such as PII/PHI detection via the `SecurityEnforcer`, bypass local processing and explicitly route to Gemini Pro (Tier 3) to leverage its superior semantic reasoning capabilities.

### 2. Distributed Synchronization via Redlock + Fencing Tokens (Enterprise Standard)
In a horizontally scaled environment, preventing race conditions on graph mutations is critical. Nexus utilizes the **Redlock** algorithm over a clustered Redis backbone to enforce strict distributed mutexes:
- **Pessimistic Locking Mechanisms:** Ensuring exclusive write access during concurrent ingest pipelines or schema migrations.
- **Deadlock Mitigation:** Lease-based lock acquisition with automatic expiration and high-availability quorum-based voting.
- **Monotonic Fencing Tokens:** Employs strictly increasing fencing tokens (Serial Numbers) to validate and guarantee serializability in Neo4j transactions.
- **The Guard (Neo4j Validation):** Every write operation includes a fencing token check (`WHERE last_fencing_token < $new_token`). If a stale token is detected, the transaction is rejected, ensuring zero data corruption.

### 3. Deep Integration with Neo4j & Graph Modeling
Nexus completely abstracts cypher execution through an advanced persistence layer, enforcing a rigid ontological schema modeled in **Neo4j**:
- **Strict Data Typing & Ontological Validity:** Schema definitions define explicit node labels and edge relationships prior to ingestion, rejecting non-conforming structures.
- **Optimized Graph Traversal:** Index-backed exact matches and full-text search integrated with vector similarity retrieval for hybrid search paradigms.
- **ACID Transactions:** Full transactional guarantees protecting the integrity of the knowledge base during multi-step graph updates.

### 4. MCP Integration (Model Context Protocol)
The system exposes native capabilities to external LLM environments utilizing standard **MCP (Model Context Protocol)** interfaces:
- **Standardized Tool Ingestion:** Instantly pluggable interfaces that securely expose targeted graph querying tools directly to authorized models.
- **Contextual Boundary Enforcement:** Strict encapsulation of the internal state while projecting exactly the necessary operational schema.

### 5. Deterministic Context Pruning
Feeding raw graph data to LLMs often results in context window pollution and hallucination. Our **Context Pruning** algorithms deterministically compress graph sub-trees before prompt construction:
- **Information Density Maximization:** Algorithmic ranking of node relevance based on edge weight, traversal depth, and semantic proximity.
- **Hard Context Bounds:** Enforcing strict token limits by truncating peripheral data, ensuring optimal inference efficiency and reduced latency.

### 6. Absolute Observability & Telemetry (99.99% SLA)
The system implements an enterprise-grade LLM Observability stack based on **OpenTelemetry**:
- **High-Resolution LLM Metrics:** Real-time capture of **Time To First Token (TTFT)**, fractional latency, and model-specific performance histograms.
- **Economic Traceability:** Automatic injection of industry-standard attributes `llm.usage.prompt_tokens` and `llm.usage.completion_tokens` for precise financial cost attribution per reasoning step.
- **Unified Distributed Tracing:** Seamless context propagation of Trace IDs across **LangGraph**, **Redis**, and **Neo4j** using W3C TraceContext, providing a "waterfall" visualization of the entire request lifecycle.
- **Structural Obfuscation & Semantic Security:** A custom **OpenTelemetry Attribute Processor** replaces brittle regex-based redaction. It enforces zero-trust logging by blocking raw payloads (`prompt`, `completion`) unless explicitly validated by the semantic security node and redacting sensitive keys (API keys, tokens, PII) at the telemetry layer.

### 7. Deep Health Probes & Resilience
The system implements a production-grade asynchronous deep health check at `/health` to ensure high availability (99.99% SLA):
- **Real-time Connectivity Checks:** Verifies both Redis (via `ping()`) and Neo4j (via lightweight `RETURN 1` query) in parallel.
- **Strict Resource Isolation:** Enforces a 2.0-second timeout on all probe operations using `asyncio.wait_for`, preventing probe-induced resource exhaustion or silent backpressure during partial outages.
- **Detailed State Reporting:** Returns `200 OK` only when all critical dependencies are operational. Returns `503 Service Unavailable` with granular component status if any dependency fails or times out.
- **Safety First:** Health probes never trigger LLM inference, avoiding unnecessary costs, rate-limiting, or latency spikes.

### 9. Elastic Enterprise Scaling (KEDA & Prometheus)
The system implements a proactive horizontal scaling architecture (HPA) to maintain a 99.99% SLA during high-demand AI processing periods:
- **Custom AI Metrics:** A specialized Prometheus Gauge `active_ai_tasks` tracks concurrent AI reasoning operations in real-time.
- **Event-Driven Autoscaling (KEDA):** A `ScaledObject` monitors the Prometheus metrics endpoint.
- **Dynamic Thresholds:** Configured to trigger horizontal pod replication when reaching a threshold of **5 active tasks per pod**, ensuring low latency and preventing resource exhaustion.
- **Fast Downscaling:** Optimized cooldown periods to release resources once AI bursts subside, maintaining cost-efficiency without sacrificing responsiveness.

### 10. Enterprise Security Pipeline & Gatekeeping
Security is integrated at the pipeline level, ensuring zero-trust interaction between users and the core LLMs:
- **PII/PHI Sanitization (Microsoft Presidio):** Real-time detection and automatic redaction of sensitive data (emails, phones, bank accounts, names) using local edge processing before the prompt reaches any model.
- **SLM-based Integrity Guardrails:** Fast binary classification for Prompt Injection and Toxicity using specialized Small Language Models (SLMs). This layer acts as a "gatekeeper," blocking malicious intents with minimal latency and zero LLM invocation on violations.
- **Output Validation:** Post-inference verification of LLM responses to prevent data leakage or non-compliant content generation.
- **Zero-Trust Secret Ingestion:** Configuration is prioritized from mounted secrets (e.g., Kubernetes `Secret` or Vault) at `/var/run/secrets/nexus-graph-ai` via Pydantic's native `secrets_dir`.
- **Enforced Encryption Schemes:** Fatal validators block application startup if connections to core dependencies (Neo4j, Redis) do not use strictly encrypted protocols (`neo4j+s://`, `rediss://`).
- **RBAC & Isolation:** Query isolation ensuring agents can only access authorized graph sub-graphs.
- **Secret Management:** Strict segregation of sensitive credentials from the operational logic layer.

### 11. Mandatory SAST Security Enforcement (Blocking CI)
To maintain enterprise-grade security standards, every Pull Request and Push to `main` undergoes mandatory automated security analysis. The CI pipeline is configured to **break the build** if vulnerabilities are detected:
- **Bandit (Python Security):** Deep recursive scanning for SQL injections, insecure library usage, and configuration weaknesses. Configured to fail on `MEDIUM` and `HIGH` severity findings.
- **Semgrep (Pattern Matching):** Multilingual scanning using strict `security-audit` and `p/python` rulesets. Any finding within these rulesets will block the merge process.
- **Trivy (Vulnerability Scan):** Automated scanning for OS vulnerabilities in the `Dockerfile` and library dependencies in `requirements.txt`. Configured with `exit-code: 1` to **strictly block the pipeline** if any **CRITICAL** vulnerability is detected.
- **Inflexible Policy:** Code cannot reach the `main` branch if there are pending security findings of `MEDIUM` or `HIGH` severity (Bandit/Semgrep) or `CRITICAL` severity (Trivy).

---

## Contratos de Datos (AgentState)

El motor multi-agente opera sobre un flujo de estado estrictamente tipado. Si integras herramientas externas o inyectas estado inicial, debes adherirte a la siguiente estructura:
- `messages`: Lista de strings con el contexto o prompts enviados.
- `current_node`: String que indica el nodo actual del flujo de LangGraph.
- `extracted_entities`: Lista de diccionarios con claves `key` y `value` de tipo string, representando las entidades procesadas.
- `query`, `response` e `history`: Campos internos de gestión de razonamiento y firmas criptográficas del LLM.

---

## 🚀 Getting Started

*Internal Documentation & Deployment configuration requires proper authorization.*

Nexus Graph AI requires Python 3.10+, an accessible Neo4j Enterprise cluster, and a Redis deployment for Redlock distributed synchronization.

```bash
# Verify system dependencies
make format && make lint && make typecheck && make test

# Initialize the infrastructure and boot the API
docker-compose up -d --build
```

---
*Built for scale. Engineered for resilience. Nexus Graph AI.*
