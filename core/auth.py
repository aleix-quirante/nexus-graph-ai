from typing import Optional, Set
from fastapi import Request, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from cryptography import x509
from cryptography.hazmat.backends import default_backend
import logging

logger = logging.getLogger(__name__)


class TokenPayload(BaseModel):
    """
    Unified Identity Payload for Nexus Graph AI.
    Maps cryptographic cert data (CN, OU) to a standard subject/role structure.
    """

    model_config = ConfigDict(strict=True, frozen=True)

    sub: str = Field(..., description="Subject identity (derived from CN)")
    role: str = Field("user", description="Primary role (derived from OU)")
    org: str = Field(..., description="Organization (derived from O)")
    raw_roles: Set[str] = Field(
        default_factory=set, description="Full set of roles/OUs"
    )


async def verify_cryptographic_identity(request: Request) -> TokenPayload:
    """
    Validates cryptographic identity from mTLS headers (Envoy/Istio).
    Alias for high-security zero-trust enforcement.
    """
    cert_pem = request.headers.get("X-Forwarded-Client-Cert")

    if not cert_pem:
        logger.warning("Auth Failure: X-Forwarded-Client-Cert header missing.")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Client certificate missing. Zero-Trust enforcement bypassed.",
        )

    try:
        # Load and parse the PEM certificate
        cert = x509.load_pem_x509_certificate(
            cert_pem.encode("utf-8"), default_backend()
        )
        subject = cert.subject

        # Extract Common Name (CN) as the primary identity
        cn_attrs = subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)
        if not cn_attrs:
            raise ValueError("Common Name (CN) missing from certificate.")
        cn = cn_attrs[0].value

        # Extract Organization (O)
        org_attrs = subject.get_attributes_for_oid(x509.oid.NameOID.ORGANIZATION_NAME)
        org = org_attrs[0].value if org_attrs else "UNKNOWN_ORG"

        # Extract Organizational Units (OU) as roles
        ous = {
            attr.value
            for attr in subject.get_attributes_for_oid(
                x509.oid.NameOID.ORGANIZATIONAL_UNIT_NAME
            )
        }

        # Determine primary role (admin if 'admin' OU is present, else user)
        primary_role = "admin" if "admin" in [ou.lower() for ou in ous] else "user"

        return TokenPayload(sub=cn, role=primary_role, org=org, raw_roles=ous)

    except Exception as e:
        logger.error(f"Cryptographic verification failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Forbidden: Cryptographic identity verification failed.",
        )


# Maintain legacy alias for backward compatibility during transition
require_mtls_identity = verify_cryptographic_identity
CertIdentity = TokenPayload
