from presidio_analyzer import AnalyzerEngine
from presidio_anonymizer import AnonymizerEngine
import logging

logger = logging.getLogger(__name__)


class PIISanitizer:
    def __init__(self):
        # Se inicializa en memoria al arrancar el contenedor
        self.analyzer = AnalyzerEngine()
        self.anonymizer = AnonymizerEngine()
        # Definimos qué es radiactivo para nuestro negocio
        self.entities_to_block = [
            "CREDIT_CARD",
            "CRYPTO",
            "EMAIL_ADDRESS",
            "IBAN_CODE",
            "IP_ADDRESS",
            "PERSON",
            "PHONE_NUMBER",
            "MEDICAL_LICENSE",
        ]

    def sanitize_prompt(self, text: str) -> str:
        """
        Analiza el texto localmente y sustituye PII por tokens <REDACTED>
        antes de que el texto toque internet.
        """
        try:
            # 1. Detectar (Local)
            results = self.analyzer.analyze(
                text=text,
                entities=self.entities_to_block,
                language="es",  # Asumimos contexto en español
            )

            # 2. Anonimizar (Local)
            anonymized_result = self.anonymizer.anonymize(
                text=text, analyzer_results=results
            )
            return anonymized_result.text
        except Exception as e:
            # Fail-Secure: Si el sanitizador falla, bloqueamos el texto por completo.
            logger.error(f"Fallo crítico en PIISanitizer: {str(e)}")
            return "[TEXTO BLOQUEADO POR FALLO DE SEGURIDAD INTERNA]"


# Instancia Singleton para reutilizar la carga en memoria
pii_sanitizer_instance = PIISanitizer()
