from pydantic import BaseModel, field_validator
from typing import Any


class SecurityGuardrailViolation(Exception):
    """Exception raised for security policy violations (PII, PHI, Toxicity)."""

    pass


class ContentInspectionModel(BaseModel):
    """
    Pydantic model that simulates deep inspection for PII, PHI and toxicity.
    No regular expressions are used.
    """

    output_text: str

    @field_validator("output_text")
    @classmethod
    def inspect_content(cls, v: str) -> str:
        text_lower = v.lower()

        # Toxicity detection without regex
        toxic_keywords = ["idiot", "stupid", "moron", "hate", "kill", "die", "toxic"]
        words = text_lower.split()
        if any(toxic_word in words for toxic_word in toxic_keywords):
            raise ValueError("Toxic content detected")

        # PII / PHI detection without regex
        sensitive_terms = [
            "ssn",
            "social security",
            "credit card",
            "password",
            "confidential",
        ]
        if any(term in text_lower for term in sensitive_terms):
            raise ValueError("Potential PII/PHI keywords detected")

        # Simulating sequence detection for numbers (e.g. CC or SSN)
        consecutive_digits = 0
        for char in v:
            if char.isdigit():
                consecutive_digits += 1
                if (
                    consecutive_digits >= 9
                ):  # Simulate detecting a 9+ digit sensitive number
                    raise ValueError(
                        "Numeric sequence matching PII/PHI length detected"
                    )
            else:
                consecutive_digits = 0

        return v


class SecurityEnforcer:
    """
    Security Enforcer class to validate LLM outputs.
    """

    async def validate_llm_output(self, output: str) -> str:
        """
        Validates the output string using the Pydantic inspection model.
        Raises SecurityGuardrailViolation on failure.
        """
        try:
            validated_model = ContentInspectionModel(output_text=output)
            return validated_model.output_text
        except Exception as e:
            raise SecurityGuardrailViolation(f"Security validation failed: {str(e)}")
