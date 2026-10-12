from pathlib import Path

import httpx
import pytest

from app.core import config


def test_environment_templates_include_required_keys() -> None:
    root_example = Path(__file__).resolve().parents[3] / ".env.example"
    frontend_example = Path(__file__).resolve().parents[3] / "frontend" / ".env.example"

    assert root_example.exists()
    assert frontend_example.exists()

    root_contents = root_example.read_text(encoding="utf-8")
    frontend_contents = frontend_example.read_text(encoding="utf-8")

    for key in (
        "SUPABASE_URL",
        "SUPABASE_ANON_KEY",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_JWT_SECRET",
        "SUPABASE_DB_URL",
        "HF_TOKEN",
    ):
        assert f"{key}=" in root_contents

    assert "VITE_API_URL=" in frontend_contents


def test_validate_runtime_environment_requires_essential_keys(monkeypatch) -> None:
    for key in (
        "SUPABASE_URL",
        "SUPABASE_SERVICE_ROLE_KEY",
        "SUPABASE_JWT_SECRET",
        "HF_TOKEN",
    ):
        monkeypatch.delenv(key, raising=False)

    try:
        config.validate_runtime_environment()
    except RuntimeError as exc:
        message = str(exc)
        assert (
            "SUPABASE_URL" in message
            or "SUPABASE_SERVICE_ROLE_KEY" in message
            or "SUPABASE_JWT_SECRET" in message
            or "HF_TOKEN" in message
        )
    else:
        raise AssertionError("validate_runtime_environment() should fail when crucial env keys are missing")


def test_validate_supabase_storage_fails_fast_for_invalid_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-key")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "a-very-long-test-secret-for-jwt-validation")
    monkeypatch.setenv("HF_TOKEN", "hf_token_123")

    class FakeResponse:
        status_code = 401
        text = "Unauthorized"

        def json(self):
            return {"message": "Unauthorized"}

    def fake_get(self, *args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(httpx.Client, "get", fake_get)

    with pytest.raises(RuntimeError, match="Supabase storage validation failed"):
        config.validate_supabase_storage()
