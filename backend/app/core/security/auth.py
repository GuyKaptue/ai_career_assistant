from __future__ import annotations

import jwt

from app.core.config import settings


def validate_bearer_token(token: str) -> dict:
    if not token:
        raise ValueError("A bearer token is required.")

    secret = settings.supabase_jwt_secret
    if not secret:
        raise RuntimeError("Authentication is not configured. Set SUPABASE_JWT_SECRET.")

    if len(secret.encode("utf-8")) < 32:
        raise RuntimeError("SUPABASE_JWT_SECRET must be at least 32 characters long for HS256 verification.")

    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"verify_signature": True, "require": ["exp", "sub"]},
        )
    except Exception as exc:  # pragma: no cover - validation is intentionally explicit.
        raise ValueError("The bearer token is invalid or expired.") from exc

    return payload
