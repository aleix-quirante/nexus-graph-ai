import json
import urllib.request
import urllib.error
from pydantic import BaseModel, field_validator
from typing import Any


class SecurityGuardrailViolation(Exception):
    """Exception raised for security policy violations (PII, PHI, Toxicity)."""

    pass


class ContentInspectionModel(BaseModel):
    """
    Pydantic model that delegates deep inspection for PII, PHI and toxicity
    to a Small Language Model (LLM as a Judge).
    """

    output_text: str

    @field_validator("output_text")
    @classmethod
    def inspect_content(cls, v: str) -> str:
        prompt = (
            "You are a strict security guardrail system. Analyze the following text "
            "for toxicity, confidential information (PII/PHI), or malicious intent. "
            "Respond ONLY with '1' if any of these are present (violation), or '0' if the text is safe. "
            "Evaluate the semantic context to resist evasion tactics like Leetspeak, obfuscation, or Base64."
        )

        payload = json.dumps(
            {
                "model": "slm-judge",
                "messages": [
                    {"role": "system", "content": prompt},
                    {"role": "user", "content": v},
                ],
                "temperature": 0.0,
                "max_tokens": 10,
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            "http://localhost:8000/v1/chat/completions",
            data=payload,
            headers={"Content-Type": "application/json"},
        )

        try:
            with urllib.request.urlopen(req, timeout=5.0) as response:
                result = json.loads(response.read().decode("utf-8"))
                judge_response = (
                    result.get("choices", [{}])[0]
                    .get("message", {})
                    .get("content", "")
                    .strip()
                )
                if "1" in judge_response:
                    raise ValueError(
                        "Semantic security violation detected by SLM Judge"
                    )
        except urllib.error.URLError as e:
            raise ValueError(f"SLM Judge network exception: {str(e)}")
        except Exception as e:
            if isinstance(e, ValueError) and "Semantic security violation" in str(e):
                raise
            raise ValueError(f"SLM Judge processing error: {str(e)}")

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
