"""`/api/ready` with the Ollama channel (Sub-step 7b).

Drives the real route through ``TestClient`` with the shared adapter stubbed to
a scripted Ollama, so the readiness contract — and above all the *isolation* of
the 200/503 decision from Ollama — is verified end to end.
"""

from __future__ import annotations

import json
import time

import httpx
import pytest
from fastapi.testclient import TestClient

import app.api.routes.health as health_module
import app.application.services.ollama_status_probe as probe_module
import app.application.services.shared_router as shared_router_module
from app.api.schemas import ReadyResponse
from app.main import app
from tests.unit.ollama_helpers import (
    FakeHfAdapter,
    FakeOllamaServer,
    RecordingClock,
    connect_refused,
    http,
    install_adapter,
    make_adapter,
    make_settings,
    ok_chat,  # noqa: F401 - unused import kept out via re-export discipline
    reset_shared_state,
    tags_response,
)

#: The real ``_database_check``, captured once so a test can reinstall it.
_REAL_DATABASE_CHECK = health_module._database_check

CHECK_KEYS = {"enabled", "reachable", "model", "model_installed", "circuit", "latency_ms"}

#: Every Ollama state the probe can report, with the script that produces it.
OLLAMA_STATES = [
    ("up_model_installed", [tags_response(["llama3.2:3b"])]),
    ("up_model_missing", [tags_response(["mistral:7b"])]),
    ("connect_error", [connect_refused()]),
    ("read_timeout", [httpx.ReadTimeout("black hole")]),
    ("http_500", [http(500)]),
    ("invalid_json", [http(200, {"unexpected": True})]),
]


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _reset():
    reset_shared_state()
    yield
    reset_shared_state()


@pytest.fixture(autouse=True)
def _healthy_other_checks(monkeypatch):
    """Keep every non-Ollama readiness check healthy.

    That is what makes the Ollama block the only variable, so a 503 can only
    come from a test that deliberately breaks another check.
    """
    monkeypatch.setattr(health_module, "_config_check", lambda: {"ok": True, "missing": []})
    monkeypatch.setattr(health_module, "_database_check", lambda: {"status": "ok"})


def _bind_probe(monkeypatch, wrapper, *, clock=None, ttl: float = 5.0, use_ollama: bool = True):
    """Bind the module probe to ``wrapper`` with an injectable clock."""
    probe = probe_module.OllamaStatusProbe(
        settings_obj=make_settings(use_ollama=use_ollama),
        adapter_getter=lambda: wrapper,
        circuit_state=lambda: wrapper.circuit_state,
        cache_ttl_seconds=ttl,
        clock=clock or RecordingClock(),
    )
    probe_module.configure_probe(probe)
    return probe


def _install(monkeypatch, server, *, clock=None, use_ollama: bool = True) -> object:
    """Install a wrapper over ``server`` and bind a probe to it."""
    wrapper = install_adapter(monkeypatch, server, FakeHfAdapter())
    _bind_probe(monkeypatch, wrapper, clock=clock, use_ollama=use_ollama)
    return wrapper


def _ollama_block(response) -> dict:
    return response.json()["checks"]["ollama"]


@pytest.mark.parametrize(
    ("label", "tags_script"),
    OLLAMA_STATES,
    ids=[row[0] for row in OLLAMA_STATES],
)
class TestOllamaStateTable:
    def test_reports_every_documented_field(self, monkeypatch, client, label, tags_script):
        _install(monkeypatch, FakeOllamaServer(tags_script=tags_script))
        response = client.get("/api/ready")

        assert response.status_code == 200
        block = _ollama_block(response)
        assert block["enabled"] is True
        assert set(block) == CHECK_KEYS
        assert isinstance(block["latency_ms"], int) or block["latency_ms"] is None

    def test_reachable_model_and_circuit_values(self, monkeypatch, client, label, tags_script):
        _install(monkeypatch, FakeOllamaServer(tags_script=tags_script))
        block = _ollama_block(client.get("/api/ready"))

        if label.startswith("up_model_installed"):
            assert block["reachable"] is True and block["model_installed"] is True
        elif label.startswith("up_model_missing"):
            assert block["reachable"] is True and block["model_installed"] is False
        else:
            assert block["reachable"] is False
            assert block["model_installed"] is None

        # The cold-start contract: circuit is null ONLY when disabled.
        assert block["circuit"] == "closed"

    def test_circuit_is_never_null_when_enabled(self, monkeypatch, client, label, tags_script):
        _install(monkeypatch, FakeOllamaServer(tags_script=tags_script))
        block = _ollama_block(client.get("/api/ready"))
        assert block["circuit"] in {"closed", "open", "half_open"}


class TestBlackHoleBound:
    def test_read_timeout_is_bounded_by_the_connect_timeout(self, monkeypatch, client):
        """A server that accepts then never answers cannot hang readiness."""
        server = FakeOllamaServer(tags_script=[httpx.ReadTimeout("black hole")])
        wrapper = install_adapter(monkeypatch, server, FakeHfAdapter())
        # The adapter uses the connect timeout as the WHOLE request timeout;
        # make it tiny so the bound is observable without a real network wait.
        wrapper._ollama._connect_timeout = 0.05
        _bind_probe(monkeypatch, wrapper)

        started = time.monotonic()
        response = client.get("/api/ready")
        elapsed = time.monotonic() - started

        assert response.status_code == 200
        assert _ollama_block(response)["reachable"] is False
        # Well inside the 3.5 s endpoint bound the contract guarantees.
        assert elapsed <= 3.5

    def test_the_frozen_model_is_not_reachable_but_endpoint_answers(self, monkeypatch, client):
        """A hung socket surfaces as unreachable, not as a hang."""
        import socket

        class BlackHoleAdapter:
            model = "llama3.2:3b"
            _connect_timeout = 0.05

            def list_models(self):
                raise httpx.ReadTimeout("never resolves")

            def close(self):
                pass

        from app.application.services.ollama_first_adapter import OllamaFirstAdapter

        wrapper = OllamaFirstAdapter(FakeHfAdapter(), BlackHoleAdapter())
        monkeypatch.setattr(shared_router_module, "build_generation_adapter", lambda _: wrapper)
        shared_router_module.set_adapter_for_testing(wrapper)
        probe_module.reset_probe_cache()
        _bind_probe(monkeypatch, wrapper)

        started = time.monotonic()
        response = client.get("/api/ready")
        assert response.status_code == 200
        assert _ollama_block(response)["reachable"] is False
        assert time.monotonic() - started <= 3.5
        assert socket is not None  # the hung-socket path is a read timeout


class TestDisabled:
    def test_enabled_false_with_zero_upstream_requests(self, monkeypatch, client):
        server = FakeOllamaServer(tags_script=[tags_response(["llama3.2:3b"])])
        _install(monkeypatch, server, use_ollama=False)

        response = client.get("/api/ready")
        block = _ollama_block(response)

        assert response.status_code == 200
        assert block == {
            "enabled": False,
            "reachable": None,
            "model": None,
            "model_installed": None,
            "circuit": None,
            "latency_ms": None,
        }
        assert server.total_requests == 0


class TestBreakerOpen:
    def test_reports_open_without_mutating_the_breaker(self, monkeypatch, client):
        from app.application.services.ollama_first_adapter import OllamaFirstAdapter

        server = FakeOllamaServer(tags_script=[tags_response(["llama3.2:3b"])])
        wrapper = OllamaFirstAdapter(FakeHfAdapter(), make_adapter(server))
        wrapper._breaker._state = "OPEN"
        wrapper._breaker._failure_count = 4
        state_before = wrapper.circuit_state

        _bind_probe(monkeypatch, wrapper)

        block = _ollama_block(client.get("/api/ready"))

        assert block["circuit"] == "open"
        assert wrapper.circuit_state == state_before == "OPEN"
        assert wrapper._breaker._failure_count == 4


class TestCache:
    def test_two_requests_inside_the_ttl_are_one_upstream_request(self, monkeypatch, client):
        clock = RecordingClock()
        server = FakeOllamaServer(tags_script=[tags_response(["llama3.2:3b"])])
        _install(monkeypatch, server, clock=clock)

        first = client.get("/api/ready")
        second = client.get("/api/ready")

        assert first.status_code == second.status_code == 200
        assert len(server.tags_requests) == 1

    def test_re_probes_after_the_ttl(self, monkeypatch, client):
        clock = RecordingClock()
        server = FakeOllamaServer(tags_script=[tags_response(["llama3.2:3b"])])
        _install(monkeypatch, server, clock=clock)

        client.get("/api/ready")
        assert len(server.tags_requests) == 1

        clock.advance(6.0)  # past the 5 s TTL
        client.get("/api/ready")
        assert len(server.tags_requests) == 2


@pytest.mark.parametrize(
    ("label", "tags_script"),
    OLLAMA_STATES,
    ids=[row[0] for row in OLLAMA_STATES],
)
class TestDecisionIsolation:
    """The guard: Ollama must never decide the 200/503 verdict.

    ``_healthy_other_checks`` (module scope) keeps the other checks green, so
    these tests control the verdict by breaking a specific check.
    """

    def test_all_other_checks_healthy_means_200(self, monkeypatch, client, label, tags_script):
        _install(monkeypatch, FakeOllamaServer(tags_script=tags_script))
        response = client.get("/api/ready")
        assert response.status_code == 200, label
        assert response.json()["checks"]["ollama"]["enabled"] is True

    def test_a_failing_check_means_503_for_every_ollama_state(self, monkeypatch, client, label, tags_script):
        monkeypatch.setattr(health_module, "_database_check", lambda: {"status": "unavailable", "detail": "db down"})
        _install(monkeypatch, FakeOllamaServer(tags_script=tags_script))

        response = client.get("/api/ready")

        assert response.status_code == 503, label
        # Ollama is still reported, healthily or not — it just never decides.
        assert "ollama" in response.json()["checks"]

    def test_disabling_a_non_ollama_check_flips_back_to_200(self, monkeypatch, client, label, tags_script):
        """A 503 caused by the database must disappear when it recovers."""
        broken = {"status": "unavailable"}
        monkeypatch.setattr(health_module, "_database_check", lambda: broken)
        _install(monkeypatch, FakeOllamaServer(tags_script=tags_script))

        assert client.get("/api/ready").status_code == 503

        broken["status"] = "ok"
        assert client.get("/api/ready").status_code == 200


class TestPrivacy:
    def test_body_carries_no_url_hostname_or_port(self, monkeypatch, client):
        server = FakeOllamaServer(tags_script=[tags_response(["llama3.2:3b"]), connect_refused()])
        _install(monkeypatch, server)

        for _ in range(2):
            body = client.get("/api/ready").text

        for forbidden in ("ollama.test", "localhost", "11434", "127.0.0.1"):
            assert forbidden not in body, forbidden

    def test_serialized_block_is_exactly_the_six_keys(self, monkeypatch, client):
        server = FakeOllamaServer(tags_script=[connect_refused()])
        _install(monkeypatch, server)
        body = client.get("/api/ready").text
        block = json.loads(body)["checks"]["ollama"]
        assert set(block) == CHECK_KEYS
        assert json.dumps(block) == json.dumps(
            {
                "enabled": True,
                "reachable": False,
                "model": "llama3.2:3b",
                "model_installed": None,
                "circuit": "closed",
                "latency_ms": None,
            }
        )


class TestResponseModel:
    def test_ready_response_accepts_the_block(self, monkeypatch, client):
        _install(monkeypatch, FakeOllamaServer(tags_script=[tags_response(["llama3.2:3b"])]))
        payload = client.get("/api/ready").json()

        validated = ReadyResponse.model_validate(payload)
        assert set(validated.checks["ollama"]) == CHECK_KEYS

    def test_openapi_declares_the_ready_schema(self, monkeypatch, client):
        spec = client.get("/openapi.json").json()
        schema = spec["paths"]["/api/ready"]["get"]["responses"]["200"]["content"]["application/json"]["schema"]
        assert "ReadyResponse" in json.dumps(schema)


class TestOtherChecksUnaffected:
    def test_config_and_database_checks_keep_their_shape(self, monkeypatch, client):
        monkeypatch.setattr(health_module, "_config_check", lambda: {"ok": True, "missing": ["X"]})
        monkeypatch.setattr(health_module, "_database_check", lambda: {"status": "ok"})
        _install(monkeypatch, FakeOllamaServer(tags_script=[tags_response(["llama3.2:3b"])]))

        checks = client.get("/api/ready").json()["checks"]

        assert checks["config"] == {"ok": True, "missing": ["X"]}
        assert checks["database"] == {"status": "ok"}


class _RespondingClient:
    """A stand-in for the PostgREST client the readiness probe uses."""

    def __init__(self, response: httpx.Response) -> None:
        self._response = response

    def get(self, *args, **kwargs) -> httpx.Response:
        return self._response


class _OkClient:
    """A PostgREST client whose probe succeeds."""

    def __init__(self, *args, **kwargs):
        pass

    def __enter__(self):
        return _RespondingClient(httpx.Response(200, request=httpx.Request("GET", "http://db.test")))

    def __exit__(self, *args):
        return False


class TestDatabaseCheckBranches:
    """The branches that *do* decide readiness, so the surface is fully covered.

    ``TestDecisionIsolation`` proves Ollama never decides readiness; these cases
    cover the two database branches that do.

    Note the module-level ``_healthy_other_checks`` fixture stubs
    ``_database_check`` for the rest of the file, so these tests reinstall the
    real function before exercising it.
    """

    @pytest.fixture(autouse=True)
    def _healthy_config(self, monkeypatch):
        monkeypatch.setattr(health_module, "_config_check", lambda: {"ok": True, "missing": []})

    def _restore_real_database_check(self, monkeypatch) -> None:
        monkeypatch.setattr(health_module, "_database_check", _REAL_DATABASE_CHECK)

    @pytest.mark.parametrize(
        ("label", "raise_error", "status_code", "expected_detail"),
        [
            ("unreachable", httpx.ConnectError("no database"), None, "The database could not be reached."),
            ("rejected_probe", None, 401, "The database rejected the readiness probe."),
        ],
        ids=["unreachable", "rejected_probe"],
    )
    def test_database_check_degrades_in_both_branches(
        self, monkeypatch, label, raise_error, status_code, expected_detail
    ):
        class FakeClient:
            def __init__(self, *args, **kwargs):
                pass

            def __enter__(self):
                if raise_error is not None:
                    raise raise_error
                return _RespondingClient(httpx.Response(status_code, request=httpx.Request("GET", "http://db.test")))

            def __exit__(self, *args):
                return False

        monkeypatch.setattr(health_module.httpx, "Client", FakeClient)
        self._restore_real_database_check(monkeypatch)
        monkeypatch.setenv("SUPABASE_URL", "http://db.test")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")

        check = _REAL_DATABASE_CHECK()

        assert check["status"] == "unavailable"
        assert check["detail"] == expected_detail
        assert "service-key" not in check["detail"]

    def test_database_check_reports_ok_when_the_probe_succeeds(self, monkeypatch):
        monkeypatch.setattr(health_module.httpx, "Client", _OkClient)
        self._restore_real_database_check(monkeypatch)
        monkeypatch.setenv("SUPABASE_URL", "http://db.test")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-key")

        check = _REAL_DATABASE_CHECK()

        assert check == {"status": "ok"}

    def test_database_not_configured_is_not_an_outage(self, monkeypatch):
        """Missing Supabase credentials are reported, not treated as a failure."""
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
        self._restore_real_database_check(monkeypatch)

        check = _REAL_DATABASE_CHECK()

        assert check["status"] == "not_configured"

    def test_database_failure_means_503(self, monkeypatch, client):
        """A failing database check produces 503 with Ollama still reported."""
        monkeypatch.setattr(
            health_module,
            "_database_check",
            lambda: {"status": "unavailable", "detail": "The database could not be reached."},
        )
        _install(monkeypatch, FakeOllamaServer(tags_script=[tags_response(["llama3.2:3b"])]))

        response = client.get("/api/ready")

        assert response.status_code == 503
        assert response.json()["checks"]["database"]["detail"] == "The database could not be reached."
        assert response.json()["checks"]["ollama"]["enabled"] is True
