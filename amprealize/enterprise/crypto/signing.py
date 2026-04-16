"""Enterprise audit log signing.

Imported by OSS as:

    from amprealize.enterprise.crypto.signing import (
        AuditSigner,
        generate_signing_key,
        load_signer_from_settings,
    )
"""

from __future__ import annotations

from typing import Any


class AuditSigner:
    """Signs and verifies audit log entries using HMAC or asymmetric keys.

    Stub — replace with real cryptographic implementation.
    """

    def __init__(self, key: bytes | None = None, **kwargs: Any) -> None:
        self._key = key

    def sign(self, payload: bytes) -> bytes:
        raise NotImplementedError("AuditSigner.sign not yet implemented")

    def verify(self, payload: bytes, signature: bytes) -> bool:
        raise NotImplementedError("AuditSigner.verify not yet implemented")


def generate_signing_key(**kwargs: Any) -> bytes:
    """Generate a new signing key.

    Stub — replace with real key generation (e.g. cryptography.hazmat).
    """
    raise NotImplementedError("generate_signing_key not yet implemented")


def load_signer_from_settings(settings: Any = None) -> AuditSigner:
    """Load an AuditSigner from application settings.

    Stub — replace with real settings-based key loading.
    """
    raise NotImplementedError("load_signer_from_settings not yet implemented")
