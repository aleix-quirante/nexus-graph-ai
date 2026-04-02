class NexusError(Exception):
    """Base class for all Nexus errors."""

    def __init__(self, message: str, details: dict = None):
        super().__init__(message)
        self.message = message
        self.details = details or {}


class InfrastructureError(NexusError):
    """Base class for infrastructure-related errors (DB, Redis, etc.)"""

    pass


class DatabaseError(InfrastructureError):
    """Base class for database errors."""

    pass


class DatabaseConnectionError(DatabaseError):
    """Raised when connection to Neo4j fails."""

    pass


class DatabaseTransactionError(DatabaseError):
    """Raised when a Neo4j transaction fails."""

    pass


class RedisError(InfrastructureError):
    """Base class for Redis errors."""

    pass


class RedisConnectionError(RedisError):
    """Raised when connection to Redis fails."""

    pass


class AIError(NexusError):
    """Base class for AI/LLM related errors."""

    pass


class LLMTimeoutError(AIError):
    """Raised when LLM request times out."""

    pass


class LLMProviderError(AIError):
    """Raised when LLM provider returns an error."""

    pass


class SecurityError(NexusError):
    """Base class for security and access errors."""

    pass


class AuthenticationError(SecurityError):
    """Raised when authentication fails."""

    pass


class AuthorizationError(SecurityError):
    """Raised when RBAC or other authorization fails."""

    pass


class RateLimitExceededError(SecurityError):
    """Raised when rate limit is exceeded."""

    pass


class BusinessLogicError(NexusError):
    """Base class for application-level business logic errors."""

    pass


class ResourceNotFoundError(BusinessLogicError):
    """Raised when a requested resource (node, etc.) is not found."""

    pass


class ConflictError(BusinessLogicError):
    """Raised when an operation conflicts with existing state (e.g. stale token)."""

    pass
