import hashlib
import hmac
import secrets
from django.conf import settings
from typing import Optional


PAYSTACK_IPS = {
    '52.31.139.228',
    '52.214.14.220',
    '52.49.173.169',
}


def get_client_ip(request) -> str:
    """
    Safely extract client IP from request headers.
    """
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        ip = x_forwarded_for.split(',')[0].strip()
    else:
        ip = request.META.get('REMOTE_ADDR', '')
    return ip


def is_paystack_ip(ip: str) -> bool:
    """
    Optional defense-in-depth: check if source IP matches official Paystack webhook ranges.
    """
    return ip in PAYSTACK_IPS


def verify_paystack_signature(payload_bytes: bytes, signature_header: Optional[str]) -> bool:
    """
    Verifies the HMAC-SHA512 signature sent by Paystack in the 'x-paystack-signature' header.
    Uses constant-time comparison (hmac.compare_digest) to prevent side-channel timing attacks.
    """
    if not signature_header:
        return False

    secret_key = getattr(settings, 'PAYSTACK_SECRET_KEY', None)
    if not secret_key:
        return False

    computed_hash = hmac.new(
        secret_key.encode('utf-8'),
        msg=payload_bytes,
        digestmod=hashlib.sha512
    ).hexdigest()

    return hmac.compare_digest(computed_hash.lower(), signature_header.strip().lower())


def verify_flutterwave_hash(signature_header: Optional[str]) -> bool:
    """
    Verifies the secret hash sent by Flutterwave in the 'verif-hash' header.
    Uses constant-time comparison to prevent timing attacks.
    """
    if not signature_header:
        return False

    expected_hash = getattr(settings, 'FLUTTERWAVE_SECRET_HASH', None)
    if not expected_hash:
        return False

    return hmac.compare_digest(expected_hash.strip(), signature_header.strip())


def generate_secure_reference(prefix: str = "EDK") -> str:
    """
    Generates a cryptographically strong, unguessable payment reference (CSPRNG).
    """
    token = secrets.token_hex(12).upper()
    return f"{prefix}-{token}"
