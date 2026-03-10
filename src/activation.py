"""Offline license key verification using Ed25519 signatures.

Keys are issued by meshradar.io and have the format:
    mr1_<base64url(payload)>.<base64url(signature)>

The embedded public key can verify that a key was signed by
Mesh Radar's private key, but cannot be used to forge new keys.
"""

from __future__ import annotations

import base64
import logging

logger = logging.getLogger(__name__)

_PREFIX = "mr1_"

_PUBLIC_KEY_PEM = """\
-----BEGIN PUBLIC KEY-----
MCowBQYDK2VwAyEAahJndiwW0B9BfDyEcsFGNGFHPyaUfC+dwSDTfGlPJCE=
-----END PUBLIC KEY-----"""


def _pad_b64(s: str) -> str:
    return s + "=" * (-len(s) % 4)


def verify_license_key(token: str) -> bool:
    """Return True if *token* carries a valid Ed25519 signature."""
    if not token or not token.startswith(_PREFIX):
        return False

    body = token[len(_PREFIX):]
    dot = body.find(".")
    if dot < 1 or dot == len(body) - 1:
        return False

    try:
        payload_b64, sig_b64 = body[:dot], body[dot + 1:]
        payload_bytes = base64.urlsafe_b64decode(_pad_b64(payload_b64))
        sig_bytes = base64.urlsafe_b64decode(_pad_b64(sig_b64))
    except Exception:
        return False

    try:
        from Crypto.PublicKey import ECC
        from Crypto.Signature import eddsa

        pub = ECC.import_key(_PUBLIC_KEY_PEM)
        verifier = eddsa.new(pub, "rfc8032")
        verifier.verify(payload_bytes, sig_bytes)
        return True
    except (ValueError, ImportError):
        return False
