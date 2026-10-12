import os
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec

from app.application.services.application_tracking import ApplicationTracker
from app.application.services.document_store import DocumentStore
from app.application.services.profile_service import ProfileStore
from app.core import config
from app.core.config import AppSettings
from app.core.security import auth


def _token(secret: str, claims: dict | None = None) -> str:
    payload = claims or {
        "sub": "user-123",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    return jwt.encode(payload, secret, algorithm="HS256")


def test_validate_bearer_token_accepts_valid_signed_token(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "test-only-signing-secret-2026-abc"
    monkeypatch.setattr(auth, "settings", AppSettings(supabase_jwt_secret=secret))

    payload = auth.validate_bearer_token(_token(secret))

    assert payload["sub"] == "user-123"


def test_validate_bearer_token_rejects_short_signing_secret(monkeypatch: pytest.MonkeyPatch) -> None:
    short_secret = "too-short-secret"
    monkeypatch.setattr(auth, "settings", AppSettings(supabase_jwt_secret=short_secret))

    with pytest.raises(RuntimeError, match="at least 32 characters"):
        auth.validate_bearer_token(_token(short_secret))


def test_validate_bearer_token_rejects_invalid_signature(monkeypatch: pytest.MonkeyPatch) -> None:
    expected_secret = "expected-secret-value-for-jwt-2026"
    monkeypatch.setattr(auth, "settings", AppSettings(supabase_jwt_secret=expected_secret))

    with pytest.raises(ValueError, match="invalid or expired"):
        auth.validate_bearer_token(_token("different-secret-value-for-jwt-2026"))


def test_validate_bearer_token_requires_subject_and_expiry(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "test-only-signing-secret-2026-abc"
    monkeypatch.setattr(auth, "settings", AppSettings(supabase_jwt_secret=secret))

    with pytest.raises(ValueError, match="invalid or expired"):
        auth.validate_bearer_token(_token(secret, {"role": "authenticated"}))


def test_validate_bearer_token_does_not_use_supabase_api_keys_as_signing_secret(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        auth,
        "settings",
        AppSettings(supabase_anon_key="anon-key", supabase_service_role_key="service-role-key"),
    )

    with pytest.raises(RuntimeError, match="SUPABASE_JWT_SECRET"):
        auth.validate_bearer_token("token")


def _es256_keypair() -> tuple[ec.EllipticCurvePrivateKey, ec.EllipticCurvePublicKey]:
    private_key = ec.generate_private_key(ec.SECP256R1())
    return private_key, private_key.public_key()


def _es256_token(private_key: ec.EllipticCurvePrivateKey, claims: dict | None = None) -> str:
    payload = claims or {
        "sub": "user-es256",
        "aud": "authenticated",
        "iss": "https://example.supabase.co/auth/v1",
        "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
    }
    return jwt.encode(payload, private_key, algorithm="ES256")


def _use_es256(
    monkeypatch: pytest.MonkeyPatch,
    public_key: ec.EllipticCurvePublicKey,
    supabase_url: str = "https://example.supabase.co",
) -> None:
    monkeypatch.setattr(auth, "settings", AppSettings(supabase_url=supabase_url))
    # Seam: replace the real JWKS lookup so tests never hit the network.
    monkeypatch.setattr(auth, "_jwks_signing_key", lambda _url, _token: public_key)


def test_validate_bearer_token_accepts_es256_jwks_token(monkeypatch: pytest.MonkeyPatch) -> None:
    private_key, public_key = _es256_keypair()
    _use_es256(monkeypatch, public_key)

    payload = auth.validate_bearer_token(_es256_token(private_key))

    assert payload["sub"] == "user-es256"


def test_validate_bearer_token_rejects_es256_signed_by_wrong_key(monkeypatch: pytest.MonkeyPatch) -> None:
    private_key, _ = _es256_keypair()
    _, untrusted_public_key = _es256_keypair()
    _use_es256(monkeypatch, untrusted_public_key)

    with pytest.raises(ValueError, match="invalid or expired"):
        auth.validate_bearer_token(_es256_token(private_key))


def test_validate_bearer_token_rejects_es256_from_other_issuer(monkeypatch: pytest.MonkeyPatch) -> None:
    private_key, public_key = _es256_keypair()
    _use_es256(monkeypatch, public_key)
    token = _es256_token(
        private_key,
        {
            "sub": "user-es256",
            "aud": "authenticated",
            "iss": "https://attacker.example.co/auth/v1",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
    )

    with pytest.raises(ValueError, match="invalid or expired"):
        auth.validate_bearer_token(token)


def test_validate_bearer_token_rejects_es256_without_audience(monkeypatch: pytest.MonkeyPatch) -> None:
    private_key, public_key = _es256_keypair()
    _use_es256(monkeypatch, public_key)
    token = _es256_token(
        private_key,
        {
            "sub": "user-es256",
            "iss": "https://example.supabase.co/auth/v1",
            "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
        },
    )

    with pytest.raises(ValueError, match="invalid or expired"):
        auth.validate_bearer_token(token)


def test_validate_bearer_token_rejects_expired_es256_token(monkeypatch: pytest.MonkeyPatch) -> None:
    private_key, public_key = _es256_keypair()
    _use_es256(monkeypatch, public_key)
    token = _es256_token(
        private_key,
        {
            "sub": "user-es256",
            "aud": "authenticated",
            "iss": "https://example.supabase.co/auth/v1",
            "exp": datetime.now(timezone.utc) - timedelta(minutes=5),
        },
    )

    with pytest.raises(ValueError, match="invalid or expired"):
        auth.validate_bearer_token(token)


def test_validate_bearer_token_es256_requires_supabase_url(monkeypatch: pytest.MonkeyPatch) -> None:
    private_key, public_key = _es256_keypair()
    monkeypatch.setattr(auth, "settings", AppSettings())
    monkeypatch.setattr(auth, "_jwks_signing_key", lambda _url, _token: public_key)

    with pytest.raises(RuntimeError, match="SUPABASE_URL"):
        auth.validate_bearer_token(_es256_token(private_key))


def test_validate_bearer_token_maps_jwks_fetch_failure_to_configuration_error(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    private_key, public_key = _es256_keypair()
    monkeypatch.setattr(auth, "settings", AppSettings(supabase_url="https://example.supabase.co"))

    def _unreachable(_url: str, _token: str) -> object:
        raise OSError("network unreachable")

    monkeypatch.setattr(auth, "_jwks_signing_key", _unreachable)

    with pytest.raises(RuntimeError, match="JWKS"):
        auth.validate_bearer_token(_es256_token(private_key))


def test_validate_bearer_token_rejects_non_hs256_symmetric_algorithm(monkeypatch: pytest.MonkeyPatch) -> None:
    secret = "test-only-signing-secret-2026-abc"
    monkeypatch.setattr(auth, "settings", AppSettings(supabase_jwt_secret=secret))
    token = jwt.encode(
        {"sub": "user-123", "exp": datetime.now(timezone.utc) + timedelta(minutes=5)},
        secret,
        algorithm="HS512",
    )

    with pytest.raises(ValueError, match="invalid or expired"):
        auth.validate_bearer_token(token)


def test_settings_load_supabase_jwt_secret_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "configured-secret")

    assert AppSettings.from_env().supabase_jwt_secret == "configured-secret"


def test_load_environment_reads_project_dotenv(
    tmp_path: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch
) -> None:
    env_file = tmp_path / ".env"
    env_file.write_text("SUPABASE_URL=https://example.supabase.co\nSUPABASE_JWT_SECRET=dotenv-secret\n")

    monkeypatch.delenv("SUPABASE_URL", raising=False)
    monkeypatch.delenv("SUPABASE_JWT_SECRET", raising=False)

    config.load_environment(env_file)

    assert os.environ["SUPABASE_URL"] == "https://example.supabase.co"
    assert os.environ["SUPABASE_JWT_SECRET"] == "dotenv-secret"


def test_stores_require_explicit_user_id_for_real_data() -> None:
    with pytest.raises(ValueError, match="user_id"):
        ProfileStore().create({"email": "user@example.com", "full_name": "Jane Doe"})

    with pytest.raises(ValueError, match="user_id"):
        DocumentStore().create({"title": "Sample", "content": "Hello"})

    with pytest.raises(ValueError, match="user_id"):
        ApplicationTracker().create({"company": "Contoso", "position": "Analyst"})
