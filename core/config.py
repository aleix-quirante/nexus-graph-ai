from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, field_validator
from typing import Optional


class Settings(BaseSettings):
    # Neo4j configuration
    NEO4J_URI: str = "neo4j+s://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: SecretStr = SecretStr("password")

    # Redis configuration
    REDIS_URL: str = "rediss://localhost:6379/0"

    # LLM API Keys - Using SecretStr to prevent accidental logging
    OPENAI_API_KEY: Optional[SecretStr] = None
    ANTHROPIC_API_KEY: Optional[SecretStr] = None
    GEMINI_API_KEY: Optional[SecretStr] = None

    # MCP configuration
    MCP_HOST: str = "0.0.0.0"
    MCP_PORT: int = 8000

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

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        secrets_dir="/var/run/secrets/nexus-graph-ai",
    )


settings = Settings()
