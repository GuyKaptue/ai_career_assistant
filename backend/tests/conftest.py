from collections.abc import Callable
from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.application.services import application_tracking, profile_service
from app.application.services import chat_store as chat_store_module
from app.application.services import document_store as document_store_module
from app.application.services import project_store as project_store_module
from app.core.config import AppSettings, settings
from app.core.security import auth
from app.infrastructure.knowledge import knowledge_store as knowledge_store_module
from app.infrastructure.knowledge import semantic_store as semantic_store_module
from app.infrastructure.knowledge.embeddings import EmbeddingService

TEST_JWT_SECRET = "backend-tests-signing-secret-2026-abc"
JOB_PROVIDER_ENV_KEYS = (
    "JOB_PROVIDER",
    "JOB_PROVIDERS",
    "ADZUNA_APP_ID",
    "ADZUNA_APP_KEY",
)

# §12 rate limiting: disabled for the shared suite (a per-IP window would make
# tests order-dependent as the suite grows). Limiter behavior itself is enabled
# explicitly with a low limit in tests/test_observability.py.
object.__setattr__(settings, "rate_limit_per_minute", 0)


@pytest.fixture(autouse=True)
def isolate_job_provider_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    """Prevent project `.env` credentials from enabling real provider traffic."""
    for key in JOB_PROVIDER_ENV_KEYS:
        monkeypatch.delenv(key, raising=False)

    def reject_live_provider_request(*args, **kwargs):
        raise AssertionError("Live job-provider HTTP is forbidden in tests; install a mocked transport.")

    monkeypatch.setattr(
        "app.infrastructure.job_providers.http.httpx.get",
        reject_live_provider_request,
    )


@pytest.fixture(autouse=True)
def isolate_model_overrides(monkeypatch: pytest.MonkeyPatch, tmp_path) -> None:
    """Never read or write the developer's real ``models enable/disable`` files."""
    monkeypatch.setenv("AI_MODEL_OVERRIDES_FILE", str(tmp_path / "model_overrides.json"))
    monkeypatch.setenv("AI_DISCOVERED_MODELS_FILE", str(tmp_path / "discovered_models.json"))


@pytest.fixture(autouse=True)
def isolate_stores_in_memory(monkeypatch: pytest.MonkeyPatch) -> None:
    """Keep unit tests hermetic: never hit live Supabase for CRUD.

    Service stores branch on settings.supabase_url at call time, so we
    force unconfigured settings in each service module. This keeps the
    local dict path (string test user_ids like "alice-user" work) and
    avoids network/FK dependencies.
    """
    memory_settings = AppSettings(supabase_jwt_secret=TEST_JWT_SECRET)
    monkeypatch.setattr(profile_service, "settings", memory_settings)
    monkeypatch.setattr(document_store_module, "settings", memory_settings)
    monkeypatch.setattr(application_tracking, "settings", memory_settings)
    monkeypatch.setattr(knowledge_store_module, "settings", memory_settings)
    monkeypatch.setattr(semantic_store_module, "settings", memory_settings)
    monkeypatch.setattr(chat_store_module, "settings", memory_settings)
    monkeypatch.setattr(project_store_module, "settings", memory_settings)

    for store in (
        profile_service.profile_store,
        document_store_module.document_store,
        application_tracking.application_tracker,
        project_store_module.project_store,
    ):
        for cache_attr in ("_profiles", "_documents", "_applications", "_projects"):
            if hasattr(store, cache_attr):
                getattr(store, cache_attr).clear()

    # Reset the chat store's singleton caches so threads never leak between tests.
    chat_store_module.chat_store._sessions.clear()


def _remote_embeddings_disabled(self, text: str):
    """Force the deterministic embedding path in tests.

    The remote HF path is reachable but payment-gated
    (402) in this environment; every call would add a
    network round-trip. Tests exercise the deterministic
    fallback, which is the offline-safe path.
    """
    raise RuntimeError("Remote embeddings are disabled in tests.")


@pytest.fixture(autouse=True)
def force_deterministic_embeddings(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(EmbeddingService, "_embed_remote", _remote_embeddings_disabled)


@pytest.fixture
def auth_headers(monkeypatch: pytest.MonkeyPatch) -> Callable[[str], dict[str, str]]:
    monkeypatch.setattr(auth, "settings", AppSettings(supabase_jwt_secret=TEST_JWT_SECRET))

    def build_headers(user_id: str = "test-user") -> dict[str, str]:
        token = jwt.encode(
            {
                "sub": user_id,
                "email": f"{user_id}@example.test",
                "exp": datetime.now(timezone.utc) + timedelta(minutes=5),
            },
            TEST_JWT_SECRET,
            algorithm="HS256",
        )
        return {"Authorization": f"Bearer {token}"}

    return build_headers
