import os
from abc import ABC, abstractmethod
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, field_validator


# --- Secret Management Abstraction (SOLID: Interface Segregation & Dependency Inversion) ---


class SecretProvider(ABC):
    """Abstract interface for secret retrieval (Strategy Pattern)."""

    @abstractmethod
    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        """Fetch a secret by key."""
        pass


class EnvSecretProvider(SecretProvider):
    """Initial implementation using environment variables (SOC2 Phase 1)."""

    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return os.getenv(key, default)


class VaultSecretProvider(SecretProvider):
    """Placeholder for HashiCorp Vault (SOC2 Phase 2)."""

    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        # Implementation for Vault would go here
        raise NotImplementedError("Vault provider not yet implemented.")


class AWSSecretManagerProvider(SecretProvider):
    """Placeholder for AWS Secrets Manager (SOC2 Phase 2)."""

    def get_secret(self, key: str, default: Optional[str] = None) -> Optional[str]:
        # Implementation for AWS would go here
        raise NotImplementedError("AWS provider not yet implemented.")


class SecretFacade:
    """
    Facade to isolate secret access from the rest of the application.
    Enables single-line configuration changes to switch providers.
    """

    def __init__(self, provider: SecretProvider):
        self._provider = provider

    def get(self, key: str, default: Optional[str] = None) -> Optional[str]:
        return self._provider.get_secret(key, default)

    def get_secret_str(
        self, key: str, default: Optional[str] = None
    ) -> Optional[SecretStr]:
        val = self.get(key, default)
        return SecretStr(val) if val is not None else None


# --- Configuration Initialization ---


def get_secret_provider() -> SecretProvider:
    """
    Factory to select the secret provider based on environment configuration.
    Follows SOC2 requirements for flexible runtime secret management.
    """
    provider_type = os.getenv("SECRET_PROVIDER", "env").lower()
    if provider_type == "vault":
        return VaultSecretProvider()
    if provider_type == "aws":
        return AWSSecretManagerProvider()
    return EnvSecretProvider()


# SINGLE LINE TO CHANGE PROVIDER:
# Change 'current_secret_provider = ...' to manually instantiate or use the factory.
current_secret_provider = get_secret_provider()
secrets = SecretFacade(current_secret_provider)


class Settings(BaseSettings):
    """
    Application settings refactored to use the SecretFacade.
    Follows SOLID principles by decoupling configuration from secret storage.
    """

    # Security configuration
    JWT_PUBLIC_KEY: str = secrets.get(
        "JWT_PUBLIC_KEY",
        "-----BEGIN PUBLIC KEY-----\nMIIBIjANBgkqhkiG9w0BAQEFAAOCAQ8AMIIBCgKCAQEA1v...\n-----END PUBLIC KEY-----",
    )

    # Neo4j configuration
    NEO4J_URI: str = secrets.get("NEO4J_URI", "neo4j+s://localhost:7687")
    NEO4J_USER: str = secrets.get("NEO4J_USER", "neo4j")
    NEO4J_PASSWORD: SecretStr = secrets.get_secret_str("NEO4J_PASSWORD", "password")

    # Redis configuration
    REDIS_URL: str = secrets.get("REDIS_URL", "rediss://localhost:6379/0")

    # LLM API Keys - Using SecretStr to prevent accidental logging
    OPENAI_API_KEY: Optional[SecretStr] = secrets.get_secret_str("OPENAI_API_KEY")
    ANTHROPIC_API_KEY: Optional[SecretStr] = secrets.get_secret_str("ANTHROPIC_API_KEY")
    GEMINI_API_KEY: Optional[SecretStr] = secrets.get_secret_str("GEMINI_API_KEY")

    # MCP configuration
    MCP_HOST: str = "0.0.0.0"
    MCP_PORT: int = 8000

    # Security SLM Guard configuration
    SLM_GUARD_ENDPOINT: str = secrets.get(
        "SLM_GUARD_ENDPOINT", "http://localhost:8000/v1/chat/completions"
    )

    @field_validator("NEO4J_URI")
    @classmethod
    def validate_neo4j_uri(cls, v: str) -> str:
        if not v.startswith("neo4j+s://"):
            raise ValueError(
                "Insecure Neo4j URI detected. 'neo4j+s://' scheme is mandatory for zero-trust compliance."
            )
        return v

    @field_validator("REDIS_URL")
    @classmethod
    def validate_redis_url(cls, v: str) -> str:
        if not v.startswith("rediss://"):
            raise ValueError(
                "Insecure Redis URL detected. 'rediss://' scheme is mandatory for zero-trust compliance."
            )
        return v

    @field_validator("NEO4J_PASSWORD")
    @classmethod
    def validate_password_not_default(cls, v: SecretStr) -> SecretStr:
        """
        Previene despliegues con credenciales por defecto.
        Estándar B2B 2026: Fail-fast en configuración insegura.
        """
        password = v.get_secret_value()

        # Lista de passwords prohibidos (comunes y por defecto)
        forbidden_passwords = [
            "password",
            "neo4j",
            "admin",
            "123456",
            "12345678",
            "qwerty",
            "abc123",
            "Password1",
            "changeme",
            "default",
        ]

        if password.lower() in [p.lower() for p in forbidden_passwords]:
            raise ValueError(
                f"Production deployment with default/weak password is forbidden. "
                f"The password '{password[:3]}***' is in the list of commonly used passwords. "
                f"Set NEO4J_PASSWORD environment variable with a strong credential (min 16 characters)."
            )

        # Validación de longitud mínima (B2B 2026 compliance)
        if len(password) < 16:
            raise ValueError(
                f"NEO4J_PASSWORD must be at least 16 characters for B2B compliance. "
                f"Current length: {len(password)} characters. "
                f"Please use a strong password with minimum 16 characters."
            )

        return v

    model_config = SettingsConfigDict(
        # We still support .env for non-secret configuration if needed,
        # but secrets are now abstracted via the provider.
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        # For SOC2 compliance, we'd ideally avoid local secrets_dir in production
        # and rely exclusively on the SecretProvider.
    )


# Instantiate settings
settings = Settings()
