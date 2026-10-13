"""Non-negotiable contracts and guards for the Ollama channel (Sub-step 7b).

These are the tests that make the *rules* permanent: the wrapper stays
signature-compatible with the Hugging Face router, the app never needs an
Ollama key, no Cline endpoint reaches the backend, nothing logs a prompt, and
the template fallback survives.
"""

from __future__ import annotations

import ast
import inspect
import pathlib
import subprocess

import pytest
from fastapi.testclient import TestClient

import app.api.routes.health as health_module
from app.application.services.ai_model_router import HuggingFaceModelRouter
from app.application.services.ollama_first_adapter import OllamaFirstAdapter
from app.core.config import REQUIRED_RUNTIME_ENV_KEYS
from app.core.errors import AIProviderError
from app.core.metrics import METRICS
from app.main import app
from tests.unit.ollama_helpers import (
    FailingHfAdapter,
    FakeHfAdapter,
    FakeOllamaServer,
    http,
    install_adapter,
    ok_chat,
    reset_shared_state,
    tags_response,
)

REPO_ROOT = pathlib.Path(__file__).resolve().parents[3]
BACKEND_APP = REPO_ROOT / "backend" / "app"

CV_PAYLOAD = {
    "use_ai": True,
    "full_name": "Ada Lovelace",
    "target_role": "Data Analyst",
    "company": "Analytic Engines Ltd",
    "skills": ["python", "sql"],
    "language": "en",
    "template": "professional",
}


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset():
    reset_shared_state()
    yield
    reset_shared_state()


# ---------------------------------------------------------------------------
# Wrapper contract
# ---------------------------------------------------------------------------
class TestWrapperContract:
    def test_signature_matches_the_hf_router_exactly(self):
        """The wrapper must be a drop-in replacement for the HF router."""
        hf = HuggingFaceModelRouter()
        wrapper = OllamaFirstAdapter(_StubHf(), _StubOllama())

        hf_signature = inspect.signature(hf.generate_with_fallback)
        wrapper_signature = inspect.signature(wrapper.generate_with_fallback)

        assert list(wrapper_signature.parameters) == list(hf_signature.parameters)
        for name, parameter in hf_signature.parameters.items():
            assert wrapper_signature.parameters[name].default == parameter.default, name
        assert hf_signature.return_annotation == wrapper_signature.return_annotation

    def test_returned_keys_equal_the_hf_key_set_on_success(self):
        hf = _RecordingHf(keys=_HF_KEYS)
        wrapper = OllamaFirstAdapter(hf, _OllamaOk())
        result = wrapper.generate_with_fallback("cv_generation", "prompt")
        assert set(result) == _HF_KEYS

    def test_returned_keys_equal_the_hf_key_set_on_fallback(self):
        hf = _RecordingHf(keys=_HF_KEYS)
        wrapper = OllamaFirstAdapter(hf, _Ollama404())
        result = wrapper.generate_with_fallback("cv_generation", "prompt")
        assert set(result) == _HF_KEYS
        assert result["fallback_chain"][0].startswith("ollama:")

    def test_generation_adapter_protocol_is_satisfied(self):
        """Every method the ``GenerationAdapter`` Protocol declares exists."""

        from app.application.services.ollama_first_adapter import GenerationAdapter

        protocol_members = {
            name
            for name, member in vars(GenerationAdapter).items()
            if not name.startswith("_") and callable(getattr(member, "__get__", None))
        }
        wrapper = OllamaFirstAdapter(_StubHf(), _StubOllama())
        for name in protocol_members:
            assert hasattr(wrapper, name), name

    @pytest.mark.parametrize(
        "name",
        ["generate_with_fallback", "close", "ollama_model_id", "ollama_adapter", "circuit_state"],
    )
    def test_public_surface_is_available(self, name):
        wrapper = OllamaFirstAdapter(_StubHf(), _StubOllama())
        assert hasattr(wrapper, name), name

    def test_half_initialised_wrapper_raises_attributeerror(self):
        """A half-built instance must not recurse through ``__getattr__``."""
        wrapper = OllamaFirstAdapter.__new__(OllamaFirstAdapter)
        with pytest.raises(AttributeError):
            wrapper.generate_with_fallback("cv_generation", "prompt")


# ---------------------------------------------------------------------------
# No billing, no key
# ---------------------------------------------------------------------------
class TestNoBillingNoKey:
    def test_no_ollama_key_is_required_at_runtime(self):
        for key in REQUIRED_RUNTIME_ENV_KEYS:
            assert not key.startswith("OLLAMA_"), key

    def test_config_declares_no_ollama_credential(self):
        from app.core.config import AppSettings

        secretish = {
            name
            for name in vars(AppSettings.from_env())
            if name.startswith("OLLAMA_") and any(part in name for part in ("KEY", "TOKEN", "SECRET"))
        }
        assert not secretish

    def test_env_example_declares_no_ollama_credential(self):
        text = (REPO_ROOT / ".env.example").read_text()
        import re

        for match in re.finditer(r"^(OLLAMA_[A-Z_]+)=", text, re.M):
            name = match.group(1)
            assert not any(part in name for part in ("KEY", "TOKEN", "SECRET")), name

    @pytest.mark.parametrize(
        ("label", "script"),
        [
            ("success", [ok_chat()]),
            ("failure", [http(502), http(502), http(502)]),
        ],
        ids=["success", "failure"],
    )
    def test_no_authorization_header_is_ever_sent(self, monkeypatch, label, script):
        server = FakeOllamaServer(chat_script=script)
        wrapper = install_adapter(monkeypatch, server, FakeHfAdapter())

        try:
            wrapper.generate_with_fallback("cv_generation", "prompt")
        except AIProviderError:
            pass  # the point is the headers, not the outcome

        assert server.chat_requests, "the adapter must have made a request"
        for request in server.chat_requests:
            assert not [k for k in request.headers if k.lower() == "authorization"]


# ---------------------------------------------------------------------------
# No Cline in the backend
# ---------------------------------------------------------------------------
class TestNoCline:
    def test_no_backend_file_references_cline(self):
        offenders: list[str] = []
        for path in sorted(BACKEND_APP.rglob("*")):
            if not path.is_file():
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            lowered = text.lower()
            if "api.cline.bot" in lowered or "cline_api_key" in lowered:
                offenders.append(str(path.relative_to(REPO_ROOT)))
        assert not offenders, f"Cline references found in: {offenders}"

    def test_no_cline_dependency_in_requirements(self):
        for name in ("requirements.txt", "pyproject.toml"):
            path = REPO_ROOT / name
            if not path.exists():
                path = REPO_ROOT / "backend" / name
            if not path.exists():
                continue
            text = path.read_text().lower()
            assert "cline" not in text, f"{name} mentions cline"

    def test_no_cline_import_anywhere(self):
        import re

        offenders: list[str] = []
        for path in sorted(BACKEND_APP.rglob("*.py")):
            text = path.read_text(encoding="utf-8")
            if re.search(r"^\s*(import|from)\s+cline", text, re.M):
                offenders.append(str(path.relative_to(REPO_ROOT)))
        assert not offenders, f"cline imports in: {offenders}"


# ---------------------------------------------------------------------------
# Privacy guard — static, over the AST
# ---------------------------------------------------------------------------
PRIVATE_NAMES = {"messages", "content", "prompt", "system_prompt", "base_url"}


class TestPrivacyGuard:
    def test_no_logging_call_receives_a_private_name_or_attribute(self):
        """No logger/print call may be handed a private attribute or name.

        This turns the Sub-step 3 grep proof into a permanent test: a future edit
        that logs `messages[0].get("content")` or the base URL fails here.
        """
        targets = [
            BACKEND_APP / "infrastructure" / "ai" / "ollama_adapter.py",
            BACKEND_APP / "application" / "services" / "ollama_first_adapter.py",
            BACKEND_APP / "application" / "services" / "ollama_status_probe.py",
        ]
        offenders: list[str] = []
        for path in targets:
            tree = ast.parse(path.read_text(), filename=str(path))
            for node in ast.walk(tree):
                if not isinstance(node, ast.Call):
                    continue
                func = node.func
                is_logger = isinstance(func, ast.Attribute) and _is_logger_call(func)
                is_print = isinstance(func, ast.Name) and func.id == "print"
                if not (is_logger or is_print):
                    continue
                for arg in node.args:
                    for bad in _private_attribute_or_name(arg, PRIVATE_NAMES):
                        offenders.append(f"{path.name}:{arg.lineno}: {bad}")
        assert not offenders, f"private data reaches a log call: {offenders}"

    def test_health_payload_carries_no_prompt_or_url(self, monkeypatch, client):
        server = FakeOllamaServer(tags_script=[tags_response(["llama3.2:3b"])])
        install_adapter(monkeypatch, server, FakeHfAdapter())
        monkeypatch.setattr(health_module, "_config_check", lambda: {"ok": True, "missing": []})
        monkeypatch.setattr(health_module, "_database_check", lambda: {"status": "ok"})

        body = client.get("/api/ready").text

        assert "ollama.test" not in body
        assert "messages" not in body
        assert "11434" not in body


# ---------------------------------------------------------------------------
# Template fallback preserved
# ---------------------------------------------------------------------------
class TestTemplateFallbackPreserved:
    @pytest.mark.parametrize(
        ("path", "payload"),
        [
            ("/api/v1/documents/cv/generate", CV_PAYLOAD),
            (
                "/api/v1/documents/cover-letter/generate",
                {
                    "use_ai": True,
                    "name": "Ada Lovelace",
                    "company": "Analytic Engines Ltd",
                    "target_role": "Data Analyst",
                    "summary": "Analytical engineer.",
                    "language": "en",
                },
            ),
        ],
        ids=["cv", "cover_letter"],
    )
    def test_deterministic_fallback_when_both_providers_fail(self, monkeypatch, client, path, payload):
        import app.application.services.shared_router as shared_router_module
        from app.application.services.ollama_first_adapter import OllamaFirstAdapter
        from tests.unit.ollama_helpers import make_adapter

        server = FakeOllamaServer([http(404)])
        wrapper = OllamaFirstAdapter(FailingHfAdapter(), make_adapter(server))
        monkeypatch.setattr(shared_router_module, "build_generation_adapter", lambda _: wrapper)
        shared_router_module.set_adapter_for_testing(wrapper)
        reset_shared_state()

        response = client.post(path, json=payload)

        assert response.status_code == 200, response.text
        body = response.json()
        assert body["ai_generated"] is False
        assert body["content"]
        assert body.get("fallback_reason")


# ---------------------------------------------------------------------------
# HF modules untouched
# ---------------------------------------------------------------------------
class TestHfIntact:
    def test_hf_modules_have_no_diff_against_head(self):
        """The HF stack must still be exactly what was committed.

        ``git`` is invoked through ``subprocess`` with a fixed argument list.
        If git cannot run the test FAILS LOUDLY rather than silently skipping.
        """
        paths = [
            "backend/app/application/services/ai_model_router.py",
            "backend/app/application/services/ai_registry.py",
            "backend/app/infrastructure/ai/hf_inference.py",
            "backend/app/infrastructure/ai/prompts/cv.py",
            "backend/tests/unit/test_ai_infrastructure.py",
        ]
        result = subprocess.run(
            ["git", "diff", "--quiet", "HEAD", "--", *paths],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert result.returncode in (0, 1), result.stderr.strip() or "git could not run"
        changed = subprocess.run(
            ["git", "diff", "--name-only", "HEAD", "--", *paths],
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        assert changed.stdout.strip().splitlines() == [], changed.stdout.strip()

    def test_public_surface_is_unchanged(self):
        """A complement to the git check: the HF surface is still callable."""
        router = HuggingFaceModelRouter()
        for name in ("select_model", "fallback_chain", "list_models", "generate_with_fallback", "route"):
            assert hasattr(router, name), name

    def test_error_taxonomy_is_unchanged(self):
        from app.application.services import ai_model_router as router_module

        for name in (
            "MODEL_UNAVAILABLE",
            "RATE_LIMITED",
            "TIMEOUT",
            "QUOTA_EXCEEDED",
            "SCHEMA_VALIDATION_FAILED",
        ):
            assert hasattr(router_module, name), name


# ---------------------------------------------------------------------------
# Metrics
# ---------------------------------------------------------------------------
class TestMetrics:
    def test_exact_counters_after_ok_failure_and_skip(self, monkeypatch):
        from app.application.services.ai_model_router import CircuitBreaker

        METRICS.reset()

        server = FakeOllamaServer([ok_chat(), http(404), http(404), http(404), http(404), http(404)])
        wrapper = OllamaFirstAdapter(
            FakeHfAdapter(), _metrics_adapter(monkeypatch, server), CircuitBreaker(failure_threshold=3)
        )
        import app.application.services.shared_router as shared_router_module

        monkeypatch.setattr(shared_router_module, "build_generation_adapter", lambda _: wrapper)
        shared_router_module.set_adapter_for_testing(wrapper)

        # 1. a success — Ollama answers, no fallback.
        wrapper.generate_with_fallback("cv_generation", "p")
        # 2-3. two availability failures: still CLOSED (threshold is 3).
        wrapper.generate_with_fallback("cv_generation", "p")
        wrapper.generate_with_fallback("cv_generation", "p")
        assert wrapper.circuit_state == "CLOSED"
        # 4. the third failure reaches the threshold and opens the breaker.
        wrapper.generate_with_fallback("cv_generation", "p")
        assert wrapper.circuit_state == "OPEN"
        # 5. with the breaker open, Ollama is skipped and never contacted.
        requests_before_skip = METRICS.get_counter("ollama_requests_total")
        wrapper.generate_with_fallback("cv_generation", "p")

        # Four attempts reached Ollama; the fifth was skipped, so the request
        # counter does not move.
        assert METRICS.get_counter("ollama_requests_total") == 4
        assert METRICS.get_counter("ollama_requests_total") == requests_before_skip
        assert METRICS.get_counter("ollama_success_total") == 1
        assert METRICS.get_counter("ollama_failed_total") == 3
        # A breaker skip is itself a fallback to Hugging Face.
        assert METRICS.get_counter("ollama_fallback_total") == 4

        METRICS.reset()


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------
_HF_KEYS = {
    "content",
    "model_id",
    "fallback_reason",
    "fallback_chain",
    "routing_score",
    "required_context",
}


class _StubHf:
    def generate_with_fallback(self, task, prompt, **kwargs):
        return {key: None for key in _HF_KEYS}


class _StubOllama:
    model = "llama3.2:3b"
    _connect_timeout = 3.0

    def chat(self, *args, **kwargs):
        from app.infrastructure.ai.ollama_adapter import OllamaResult

        return OllamaResult(content="ok", model="llama3.2:3b", latency_ms=1, prompt_tokens=1, completion_tokens=1)

    def close(self):
        pass


class _OllamaOk(_StubOllama):
    pass


class _Ollama404(_StubOllama):
    def chat(self, *args, **kwargs):
        raise AIProviderError("MODEL_UNAVAILABLE: not installed")


class _RecordingHf:
    """Records calls and replies with exactly the HF key set."""

    def __init__(self, keys):
        self._keys = set(keys)
        self.calls = 0

    def generate_with_fallback(self, task, prompt, **kwargs):
        self.calls += 1
        return {key: None for key in self._keys}


def _metrics_adapter(monkeypatch, server):
    """An adapter over the scripted server whose contribute is tracked."""
    from tests.unit.ollama_helpers import make_adapter

    return make_adapter(server)


def _is_logger_call(func: ast.Attribute) -> bool:
    """True for ``logger.*``, ``logging.*`` and a module logger call."""
    value = func.value
    if isinstance(value, ast.Name):
        return value.id in {"logger", "logging", "logging_module"}
    return False


def _private_attribute_or_name(node: ast.AST, names: set) -> list[str]:
    """Yield ``str`` descriptions of private names/attributes used in ``node``."""
    found: list[str] = []
    for child in ast.walk(node):
        if isinstance(child, ast.Attribute) and child.attr in names:
            found.append(f".{child.attr}")
        elif isinstance(child, ast.Name) and child.id in names:
            found.append(child.id)
    return found
