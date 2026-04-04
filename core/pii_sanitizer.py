from core.security_guardrails import PIISanitizer

_instance = PIISanitizer()


def sanitize_payload(text: str) -> str:
    """Enterprise-grade PII Sanitization wrapper for backward compatibility."""
    return _instance.sanitize(text)


# Singleton instance for legacy callers
pii_sanitizer_instance = _instance
