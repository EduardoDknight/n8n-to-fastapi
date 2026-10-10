import hashlib
import hmac


def sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def verify_signature(body: bytes, signature: str | None, secret: str) -> bool:
    """Constant-time check of an `X-Signature: sha256=<hex>` header over the raw body."""
    if not signature:
        return False
    return hmac.compare_digest(sign(body, secret), signature.removeprefix("sha256="))
