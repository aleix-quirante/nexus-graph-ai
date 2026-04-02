import jwt
import logging
from typing import Optional, Literal
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field, ValidationError
from core.config import settings

# Configure logging
logger = logging.getLogger(__name__)

# Security Scheme
security = HTTPBearer()

# Recognized roles in the taxonomy
RoleType = Literal["admin", "agent"]


class TokenPayload(BaseModel):
    """
    Cryptographic identity claim schema.
    """

    sub: str = Field(..., description="Subject (unique user/service identifier)")
    role: RoleType = Field(..., description="Assigned RBAC role (admin, agent)")
    exp: int = Field(..., description="Token expiration timestamp (Unix Epoch)")


async def verify_cryptographic_identity(
    auth: HTTPAuthorizationCredentials = Depends(security),
) -> TokenPayload:
    """
    Strict cryptographic identity validation middleware.
    Decodes and verifies RS256 JWT signatures against the configured public key.
    Enforces 'Deny by Default' policy.
    """
    token = auth.credentials

    try:
        # Decode and verify JWT
        payload = jwt.decode(
            token,
            settings.JWT_PUBLIC_KEY,
            algorithms=["RS256"],
            options={"verify_exp": True},
        )

        # Validate schema via Pydantic
        token_data = TokenPayload(**payload)

        logger.info(f"Verified identity: {token_data.sub} with role: {token_data.role}")
        return token_data

    except jwt.ExpiredSignatureError:
        logger.warning("JWT validation failed: Token expired.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except (jwt.InvalidTokenError, ValidationError) as e:
        logger.warning(
            f"Zero-Trust violation: Invalid token or unrecognized claims. Error: {str(e)}"
        )
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Invalid or unauthorized identity token. Zero-Trust policy violation.",
        )
    except Exception as e:
        logger.error(f"Unexpected authentication failure: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: Default Policy.",
        )
