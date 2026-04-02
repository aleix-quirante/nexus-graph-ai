from fastapi import Request, HTTPException, status
from pydantic import BaseModel, ConfigDict
from cryptography import x509
from cryptography.hazmat.backends import default_backend


class CertIdentity(BaseModel):
    model_config = ConfigDict(strict=True, frozen=True)
    common_name: str
    organization: str
    roles: frozenset[str]


async def require_mtls_identity(request: Request) -> CertIdentity:
    """Valida la identidad criptográfica del cliente extraída del Envoy/Istio sidecar."""
    cert_pem = request.headers.get("X-Forwarded-Client-Cert")
    if not cert_pem:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Client certificate missing. Enforcement by Service Mesh bypassed.",
        )

    try:
        cert = x509.load_pem_x509_certificate(
            cert_pem.encode("utf-8"), default_backend()
        )
        subject = cert.subject
        cn = subject.get_attributes_for_oid(x509.oid.NameOID.COMMON_NAME)[0].value
        org = subject.get_attributes_for_oid(x509.oid.NameOID.ORGANIZATION_NAME)[
            0
        ].value

        ous = [
            attr.value
            for attr in subject.get_attributes_for_oid(
                x509.oid.NameOID.ORGANIZATIONAL_UNIT_NAME
            )
        ]

        return CertIdentity(common_name=cn, organization=org, roles=frozenset(ous))
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Cryptographic identity verification failed.",
        )
