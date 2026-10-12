"""Bearer-token validation for Supabase-issued JWTs.

The (unverified) token header's ``alg`` only routes between two mutually
exclusive verification paths:

- ``HS256`` — legacy shared-secret tokens verified with ``SUPABASE_JWT_SECRET``
  (tests, older Supabase projects).
- ``ES256``/``RS256`` — asymmetric tokens issued by modern Supabase projects.
  Verified against the project JWKS at
  ``{SUPABASE_URL}/auth/v1/.well-known/jwks.json`` with strict ``iss`` and
  ``aud`` checks.

Each path only ever uses its own key material (shared secret vs JWKS public
keys), so header-based routing cannot be abused for algorithm-confusion
attacks.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

import jwt
from jwt import PyJWKClient
from jwt.exceptions import PyJWKError

from app.core.config import settings

ASYMMETRIC_ALGORITHMS = frozenset({"ES256", "RS256"})
SUPABASE_JWT_AUDIENCE = "authenticated"
_JWKS_CACHE_LIFETIME_SECONDS = 3600


def validate_bearer_token(token: str) -> dict:
    if not token:
        raise ValueError("A bearer token is required.")

    algorithm = _header_algorithm(token)
    if algorithm is not None and algorithm in ASYMMETRIC_ALGORITHMS:
        return _validate_asymmetric_token(token, algorithm)
    return _validate_hs256_token(token)


def _header_algorithm(token: str) -> str | None:
    """Read ``alg`` from the unverified header; None when the token is undecodable."""
    try:
        return jwt.get_unverified_header(token).get("alg")
    except Exception:
        return None


def _validate_hs256_token(token: str) -> dict:
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
    except Exception as exc:  # validation is intentionally explicit.
        raise ValueError("The bearer token is invalid or expired.") from exc

    return payload


def _validate_asymmetric_token(token: str, algorithm: str) -> dict:
    base_url = (settings.supabase_url or "").rstrip("/")
    if not base_url:
        raise RuntimeError("Authentication is not configured. Set SUPABASE_URL.")

    try:
        signing_key = _jwks_signing_key(f"{base_url}/auth/v1/.well-known/jwks.json", token)
    except ValueError:
        raise
    except Exception as exc:
        raise RuntimeError("Unable to fetch the Supabase JWKS for token verification.") from exc

    try:
        payload = jwt.decode(
            token,
            signing_key,
            algorithms=[algorithm],
            audience=SUPABASE_JWT_AUDIENCE,
            issuer=f"{base_url}/auth/v1",
            options={"verify_signature": True, "require": ["exp", "sub", "aud", "iss"]},
        )
    except Exception as exc:  # validation is intentionally explicit.
        raise ValueError("The bearer token is invalid or expired.") from exc

    return payload


@lru_cache(maxsize=4)
def _jwks_client(jwks_url: str) -> PyJWKClient:
    """One cached JWKS client per URL (1 h lifespan; auto-refreshes on unknown kid)."""
    return PyJWKClient(jwks_url, cache_keys=True, lifespan=_JWKS_CACHE_LIFETIME_SECONDS)


def _jwks_signing_key(jwks_url: str, token: str) -> Any:
    """Public key for ``token`` from the Supabase JWKS.

    An unknown/rotated ``kid`` raises ValueError (→ 401); network and parse
    failures propagate so the caller maps them to a configuration error.
    """
    try:
        return _jwks_client(jwks_url).get_signing_key_from_jwt(token).key
    except PyJWKError as exc:
        raise ValueError("The bearer token is invalid or expired.") from exc
