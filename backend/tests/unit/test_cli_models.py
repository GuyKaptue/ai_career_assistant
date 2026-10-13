"""``models`` and ``ai`` CLI commands + operator overrides."""

import json

import pytest

from app import cli, cli_ai
from app.application.services import model_overrides
from app.application.services.ai_discovery import DiscoveryReport, ModelDiscoveryService
from app.application.services.ai_model_router import HuggingFaceInferenceAdapter, HuggingFaceModelRouter
from app.application.services.ai_registry import AI_TASKS, ModelMetadata
from app.core.config import AppSettings


def run(argv, capsys):
    code = cli.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.fixture
def with_token(monkeypatch):
    monkeypatch.setattr(cli_ai, "settings", AppSettings(supabase_jwt_secret="x" * 40, huggingface_token="hf_test"))


def _candidate(model_id="acme/Open-Instruct-7B", license_name="apache-2.0"):
    return ModelMetadata(
        model_id=model_id,
        task_capabilities=("cv_generation",),
        context_window=32768,
        license=license_name,
        supported_languages=("en", "de"),
        capabilities=("instruction_following",),
    )


class TestList:
    def test_table_lists_registered_models(self, capsys):
        code, out, _ = run(["models", "list"], capsys)
        assert code == 0
        assert "MODEL" in out and "mistralai/Mistral-Small-3.1-24B-Instruct-2503" in out

    def test_json_output_is_machine_readable(self, capsys):
        _, out, _ = run(["models", "list", "--json"], capsys)
        data = json.loads(out)
        assert data["models"] and {"model_id", "enabled", "policy", "context_window"} <= set(data["models"][0])

    def test_task_filter(self, capsys):
        _, out, _ = run(["models", "list", "--task", "translation", "--json"], capsys)
        assert all(m["tasks"] == ["(any)"] or "translation" in m["tasks"] for m in json.loads(out)["models"])


class TestValidate:
    def test_default_registry_is_valid_and_covers_every_task(self, capsys):
        code, out, _ = run(["models", "validate", "--json"], capsys)
        report = json.loads(out)
        assert code == 0 and report["ok"]
        assert report["tasks_covered"] == report["tasks_total"] == len(AI_TASKS)
        assert any("requires review" in w for w in report["warnings"])

    def test_inconsistent_registry_fails_with_exit_1(self, monkeypatch, capsys):
        broken = HuggingFaceModelRouter(
            models=[ModelMetadata(model_id="x/tiny", context_window=100, max_output_tokens=512, license="apache-2.0")]
        )
        monkeypatch.setattr(cli_ai, "build_router", lambda: broken)
        code, out, _ = run(["models", "validate"], capsys)
        assert code == 1
        assert "context window 100 <= max output 512" in out


class TestEnableDisable:
    def test_disabled_model_is_never_routed_and_enable_restores_it(self, capsys):
        _, out, _ = run(["ai", "test", "--task", "cv_generation", "--json"], capsys)
        selected = json.loads(out)["routing"]["model_id"]

        code, text, _ = run(["models", "disable", selected], capsys)
        assert code == 0 and "Disabled" in text
        assert model_overrides.load_overrides()["disabled"] == [selected]
        _, out, _ = run(["ai", "test", "--task", "cv_generation", "--json"], capsys)
        assert json.loads(out)["routing"]["model_id"] != selected

        run(["models", "enable", selected], capsys)
        _, out, _ = run(["ai", "test", "--task", "cv_generation", "--json"], capsys)
        assert json.loads(out)["routing"]["model_id"] == selected
        assert model_overrides.load_overrides()["disabled"] == []

    def test_unknown_model_is_exit_2(self, capsys):
        code, _, err = run(["models", "disable", "nope/none"], capsys)
        assert code == 2 and "Unknown model" in err

    def test_overrides_reach_the_shared_runtime_router(self):
        from app.application.services import shared_router

        model_overrides.set_disabled("microsoft/phi-4", True)
        shared_router.reset_shared_state()
        try:
            router = shared_router.get_router()
            phi = next(m for m in router.models if m.model_id == "microsoft/phi-4")
            assert phi.enabled is False
        finally:
            shared_router.reset_shared_state()

    def test_corrupt_overrides_file_is_ignored_not_fatal(self):
        model_overrides.overrides_path().write_text("{not json")
        assert model_overrides.load_overrides() == {"disabled": [], "enabled_discovered": []}


class TestDiscoverRefresh:
    def _fake_discover(self, monkeypatch, approved):
        report = DiscoveryReport(12, 9, 5, 4, 3, 2, tuple(approved), (("bad/Model", "license_blocked"),))
        monkeypatch.setattr(ModelDiscoveryService, "discover", lambda self, **kw: report)

    def test_requires_a_token(self, capsys):
        for command in ("discover", "refresh"):
            code, _, err = run(["models", command], capsys)
            assert code == 1 and "HF_TOKEN" in err

    def test_discover_is_a_dry_run(self, with_token, monkeypatch, capsys):
        self._fake_discover(monkeypatch, [_candidate()])
        code, out, _ = run(["models", "discover", "--task", "cv_generation"], capsys)
        assert code == 0 and "acme/Open-Instruct-7B" in out and "Dry run" in out
        assert not model_overrides.discovered_path().exists()

    def test_refresh_saves_but_does_not_activate(self, with_token, monkeypatch, capsys):
        self._fake_discover(monkeypatch, [_candidate()])
        code, out, _ = run(["models", "refresh", "--task", "cv_generation"], capsys)
        assert code == 0 and "NOT routable yet" in out
        assert [m.model_id for m in model_overrides.load_discovered()] == ["acme/Open-Instruct-7B"]
        _, listing, _ = run(["models", "list", "--json"], capsys)
        assert "acme/Open-Instruct-7B" not in listing

    def test_enabling_a_cached_model_registers_it_with_policy_applied(self, with_token, monkeypatch, capsys):
        self._fake_discover(monkeypatch, [_candidate(), _candidate("acme/Review-Me-9B", license_name="llama3")])
        run(["models", "refresh", "--task", "cv_generation"], capsys)

        code, out, _ = run(["models", "enable", "acme/Open-Instruct-7B"], capsys)
        assert code == 0
        _, listing, _ = run(["models", "list", "--json"], capsys)
        row = next(m for m in json.loads(listing)["models"] if m["model_id"] == "acme/Open-Instruct-7B")
        assert row["enabled"] and row["policy"] == "APPROVED"

        _, out, _ = run(["models", "enable", "acme/Review-Me-9B"], capsys)
        assert "license policy status is REQUIRES_REVIEW" in out

    def test_unknown_task_is_exit_2(self, with_token, capsys):
        code, _, err = run(["models", "discover", "--task", "make_coffee"], capsys)
        assert code == 2 and "Unknown task" in err

    def test_hub_errors_become_a_clean_message(self, with_token, monkeypatch, capsys):
        def boom(self, **kw):
            raise ConnectionError("hub down")

        monkeypatch.setattr(ModelDiscoveryService, "discover", boom)
        code, _, err = run(["models", "discover", "--task", "cv_generation"], capsys)
        assert code == 1 and "ConnectionError" in err and "Traceback" not in err


class TestHealthAndBenchmark:
    def test_health_reports_circuit_state_offline(self, capsys):
        code, out, _ = run(["models", "health", "--json"], capsys)
        data = json.loads(out)
        assert code == 0 and not data["live"]
        assert {row["circuit"] for row in data["models"]} == {"CLOSED"}

    def test_live_health_needs_a_token(self, capsys):
        code, _, err = run(["models", "health", "--live"], capsys)
        assert code == 1 and "HF_TOKEN" in err

    def test_live_health_classifies_probe_failures(self, with_token, monkeypatch, capsys):
        def probe(self, model, prompt, max_new_tokens):
            if model.model_id == "microsoft/phi-4":
                raise RuntimeError("429 Too Many Requests")
            return "ok"

        monkeypatch.setattr(HuggingFaceInferenceAdapter, "_call_model", probe)
        _, out, _ = run(["models", "health", "--live", "--json"], capsys)
        probes = {m["model_id"]: m["probe"] for m in json.loads(out)["models"] if "probe" in m}
        assert probes["microsoft/phi-4"]["ok"] is False and probes["microsoft/phi-4"]["failure"] == "RATE_LIMITED"
        assert probes["deepseek-ai/DeepSeek-R1"]["ok"] is True

    def test_routing_benchmark_is_offline_and_deterministic(self, capsys):
        _, first, _ = run(["models", "benchmark", "--task", "cv_generation", "--json"], capsys)
        _, second, _ = run(["models", "benchmark", "--task", "cv_generation", "--json"], capsys)
        rows = json.loads(first)["rows"]
        assert first == second
        assert [r["budget"] for r in rows] == list(cli_ai.BENCHMARK_BUDGETS)
        assert all(r["model_id"] for r in rows)

    def test_live_benchmark_reports_median_latency(self, with_token, monkeypatch, capsys):
        monkeypatch.setattr(HuggingFaceInferenceAdapter, "_call_model", lambda self, m, p, n: "ok")
        code, out, _ = run(
            ["models", "benchmark", "--live", "--model", "microsoft/phi-4", "--runs", "3", "--json"], capsys
        )
        report = json.loads(out)
        assert code == 0 and report["ok"] == 3 and report["median_ms"] is not None

    def test_live_benchmark_needs_a_registered_model(self, with_token, capsys):
        code, _, err = run(["models", "benchmark", "--live", "--model", "nope/none"], capsys)
        assert code == 2 and "--model" in err


class TestAiTest:
    def test_dry_run_explains_the_decision_without_any_request(self, monkeypatch, capsys):
        monkeypatch.setattr(
            HuggingFaceInferenceAdapter,
            "_call_model",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("dry run must not call the provider")),
        )
        code, out, _ = run(["ai", "test", "--task", "cover-letter-generation", "--language", "de"], capsys)
        assert code == 0
        assert "Selected:" in out and "Eliminated:" in out and "Dry run" in out

    def test_unknown_task_is_exit_2(self, capsys):
        code, _, err = run(["ai", "test", "--task", "nonsense"], capsys)
        assert code == 2 and "Unknown task" in err

    def test_live_needs_a_token(self, capsys):
        code, _, err = run(["ai", "test", "--live"], capsys)
        assert code == 1 and "HF_TOKEN" in err

    def test_live_runs_the_real_fallback_chain(self, with_token, monkeypatch, capsys):
        monkeypatch.setattr(
            HuggingFaceInferenceAdapter, "_call_model", lambda self, model, prompt, max_new_tokens: "A concise tip."
        )
        code, out, err = run(["ai", "test", "--task", "career_advice", "--live", "--json"], capsys)
        assert code == 0 and "sends the prompt" in err
        payload = json.loads(out)
        live = payload["live"]
        # The answering model is reported…
        assert live["model_id"]
        # …and the provider is derived from it: an HF id means "huggingface".
        assert live["provider"] == "huggingface"
        assert live["latency_ms"] >= 0
        assert "fallback_chain" in live and "fallback_reason" in live
        # Privacy contract (RD-01): the generated content and the prompt must
        # never reach the CLI payload, in any field.
        blob = json.dumps(payload)
        assert "output_preview" not in blob
        assert "A concise tip." not in blob
        assert "career coach" not in blob.lower()

    def test_live_reports_the_typed_failure_class(self, with_token, monkeypatch, capsys):
        def fail(self, model, prompt, max_new_tokens):
            raise RuntimeError("503 Service Unavailable")

        monkeypatch.setattr(HuggingFaceInferenceAdapter, "_call_model", fail)
        code, out, err = run(["ai", "test", "--live", "--json"], capsys)
        payload = json.loads(out)
        assert code == 1
        assert "AIProviderError" in payload["error"]
        # The typed failure class is reported alongside the raw error, and the
        # exit code matches the CLI's existing failure convention.
        assert payload["failure_class"]
        assert "Failure class:" in err

    def test_live_failure_is_reported_not_raised(self, with_token, monkeypatch, capsys):
        def fail(self, model, prompt, max_new_tokens):
            raise RuntimeError("503 Service Unavailable")

        monkeypatch.setattr(HuggingFaceInferenceAdapter, "_call_model", fail)
        code, out, _ = run(["ai", "test", "--live", "--json"], capsys)
        assert code == 1 and "AIProviderError" in json.loads(out)["error"]


def test_jobs_search_cli_has_include_old(monkeypatch, capsys):
    seen = {}

    def fake(**kwargs):
        seen.update(kwargs)
        return {"results": []}

    monkeypatch.setattr("app.domain.jobs.service.search_jobs", fake)
    assert cli.main(["jobs", "search", "dev", "--include-old"]) == 0
    assert seen["include_old"] is True
