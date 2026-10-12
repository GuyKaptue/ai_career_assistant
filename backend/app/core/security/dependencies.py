from __future__ import annotations

from typing import Any

from fastapi import Depends
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.errors import AuthenticationError, ConfigurationError
from app.core.security.auth import validate_bearer_token

bearer_scheme = HTTPBearer(auto_error=False)


def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any]:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationError("A valid bearer token is required.")

    try:
        claims = validate_bearer_token(credentials.credentials)
    except ValueError as exc:
        raise AuthenticationError("The bearer token is invalid or expired.") from exc
    except RuntimeError as exc:
        raise ConfigurationError("Authentication is not configured.", internal=str(exc)) from exc

    if not isinstance(claims.get("sub"), str) or not claims["sub"].strip():
        raise AuthenticationError("The bearer token does not identify a user.")
    return claims


def get_optional_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict[str, Any] | None:
    """Best-effort user resolution for public endpoints (RD-05).

    Returns the authenticated user's claims when a valid bearer
    token is presented, otherwise None. Used by generation
    endpoints that personalize output with the user's own
    documents when authenticated but remain usable anonymously.
    Invalid or expired tokens degrade to None rather than
    rejecting the request.
    """
    if credentials is None or credentials.scheme.lower() != "bearer":
        return None

    try:
        claims = validate_bearer_token(credentials.credentials)
    except (ValueError, RuntimeError):
        return None

    if not isinstance(claims.get("sub"), str) or not claims["sub"].strip():
        return None
    return claims
