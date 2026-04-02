from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import field_validator
from typing import Optional


class Settings(BaseSettings):
    # Neo4j configuration
    NEO4J_URI: str = "neo4j+s://localhost:7687"
    NEO4J_USER: str = "neo4j"
    NEO4J_PASSWORD: str = "password"

    # Redis configuration
    REDIS_URL: str = "rediss://localhost:6379/0"

    # LLM API Keys
    OPENAI_API_KEY: str = ""
    ANTHROPIC_API_KEY: Optional[str] = None

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
