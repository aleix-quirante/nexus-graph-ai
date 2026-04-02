import presidio_analyzer
import presidio_anonymizer

analyzer = presidio_analyzer.AnalyzerEngine()
anonymizer = presidio_anonymizer.AnonymizerEngine()


def sanitize_payload(text: str) -> str:
    """Bloquea exfiltración de PII antes del envío a LLM Cloud."""
    results = analyzer.analyze(
        text=text,
        entities=["PERSON", "EMAIL_ADDRESS", "PHONE_NUMBER", "CREDIT_CARD", "CRYPTO"],
        language="en",
    )
    anonymized_result = anonymizer.anonymize(text=text, analyzer_results=results)
    return anonymized_result.text
