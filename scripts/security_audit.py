import logging
import os
import re
import sys

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger("tier1-auditor")


def audit_dockerfile(path: str) -> list[str]:
    violations = []
    if not os.path.exists(path):
        return ["Dockerfile missing"]

    with open(path) as f:
        content = f.read()

    if "USER" not in content:
        violations.append(
            "NON-ROOT USER MISSING: Docker container runs as root by default."
        )

    if "HEALTHCHECK" not in content:
        violations.append(
            "HEALTHCHECK MISSING: No native health monitoring for orchestrator."
        )

    if "apt-get update" in content and "rm -rf /var/lib/apt/lists/*" not in content:
        violations.append(
            "APT CACHE NOT CLEANED: Increases attack surface and image size."
        )

    return violations


def audit_auth_security(path: str) -> list[str]:
    violations = []
    if not os.path.exists(path):
        return ["core/auth.py missing"]

    with open(path) as f:
        content = f.read()

    if "X-Forwarded-Client-Cert" not in content:
        violations.append(
            "mTLS HEADER MISSING: No cryptographic identity propagation detected."
        )

    if "verify_cryptographic_identity" not in content:
        violations.append(
            "UNIFIED AUTH FUNCTION MISSING: Inconsistent security entry point."
        )

    return violations


def audit_cypher_injection_protection(dir_path: str) -> list[str]:
    violations = []
    # Search for f-strings in .run() or execute_query() calls
    # Note: This is a simplified static analysis.
    pattern = re.compile(r'\.run\(f".*\{.*\}')

    for root, _, files in os.walk(dir_path):
        for file in files:
            if file.endswith(".py"):
                path = os.path.join(root, file)
                with open(path) as f:
                    for i, line in enumerate(f):
                        if pattern.search(line):
                            # Check if it's protected by validate_cypher_identifier
                            if "validate_cypher_identifier" not in line:
                                violations.append(
                                    f"CYPHER INJECTION RISK: {path}:{i + 1} - Potential unvalidated f-string in query."
                                )

    return violations


def run_full_audit():
    logger.info("🚀 Starting Tier-1 Adversarial Security Audit...")

    all_violations = []

    # 1. Infrastructure Audit
    logger.info("Inspecting Infrastructure artifacts...")
    docker_violations = audit_dockerfile("Dockerfile")
    all_violations.extend([("INFRA", v) for v in docker_violations])

    # 2. Security Layer Audit
    logger.info("Inspecting Security Layer (Auth/Guardrails)...")
    auth_violations = audit_auth_security("core/auth.py")
    all_violations.extend([("AUTH", v) for v in auth_violations])

    # 3. Code Injection Audit
    logger.info("Inspecting Code for Injection vectors...")
    code_violations = audit_cypher_injection_protection(".")
    all_violations.extend([("CODE", v) for v in code_violations])

    if not all_violations:
        logger.info("✅ Tier-1 Audit Passed! No critical violations found.")
        sys.exit(0)
    else:
        logger.error(f"❌ Tier-1 Audit Failed! Found {len(all_violations)} violations:")
        for category, violation in all_violations:
            print(f"  [{category}] {violation}")
        sys.exit(1)


if __name__ == "__main__":
    run_full_audit()
