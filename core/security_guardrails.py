import re
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class SecurityEnforcer:
    """
    Security middleware/interceptor to evaluate LLM responses for PII/PHI exfiltration
    and destructive hallucinations. Acts as a compensatory control for ISO 27001.
    """

    # High-performance regex patterns
    # Matches generic 16-digit credit cards with optional hyphens/spaces
    CC_PATTERN = re.compile(r"\b(?:\d[ -]*?){13,16}\b")

    # Matches typical internal email structures, configurable via domain if needed
    # For now, matching obvious generic patterns and a placeholder for company domains
    INTERNAL_EMAIL_PATTERN = re.compile(
        r"\b[A-Za-z0-9._%+-]+@(?:internal\.company\.com|corp\.local|admin\..+)\b",
        re.IGNORECASE,
    )

    # Broad SSN pattern as an example of PHI/PII
    SSN_PATTERN = re.compile(r"\b\d{3}[-.]?\d{2}[-.]?\d{4}\b")

    # Simple toxicity keywords (in a real scenario, use a dedicated NLP model/API)
    TOXICITY_KEYWORDS = re.compile(
        r"\b(idiot|stupid|moron|hate|kill|die)\b", re.IGNORECASE
    )

    def __init__(self, block_on_failure: bool = True):
        self.block_on_failure = block_on_failure

    def evaluate_payload(self, text: str) -> Dict[str, Any]:
        """
        Evaluates the generated text against security patterns.
        Returns a dict with evaluation results.
        """
        findings = []
        is_safe = True

        if not text or not isinstance(text, str):
            return {
                "is_safe": True,
                "findings": [],
                "reason": "Empty or non-string payload",
            }

        # Check for Credit Cards
        if self.CC_PATTERN.search(text):
            findings.append("Credit Card Information Detected (PII)")
            is_safe = False

        # Check for Internal Emails
        if self.INTERNAL_EMAIL_PATTERN.search(text):
            findings.append("Internal Corporate Email Detected (Exfiltration Risk)")
            is_safe = False

        # Check for SSN
        if self.SSN_PATTERN.search(text):
            findings.append("Social Security Number Detected (PII/PHI)")
            is_safe = False

        # Basic Toxicity check
        if self.TOXICITY_KEYWORDS.search(text):
            findings.append("Toxic content or inappropriate language detected")
            is_safe = False

        return {
            "is_safe": is_safe,
            "findings": findings,
            "reason": ", ".join(findings) if findings else "Payload is clean",
        }

    def enforce(self, text: str) -> str:
        """
        Enforces security policies. If the text is unsafe and block_on_failure is True,
        it raises an exception or returns a redacted/safe message.
        """
        evaluation = self.evaluate_payload(text)

        if not evaluation["is_safe"]:
            logger.warning(f"SecurityEnforcer violation: {evaluation['reason']}")

            if self.block_on_failure:
                # Return a safe, standardized message or raise a specific exception
                return "[REDACTED] The generated response was blocked by security guardrails due to policy violations."

        return text
