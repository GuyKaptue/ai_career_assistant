"""Ollama surface in the CLI (Sub-step 7b).

Extends ``tests/unit/test_cli_models.py`` (the existing home of the CLI tests).
Ollama is a scripted server behind the shared adapter, so the commands run
offline: no real server, no ports, no network.
"""

from __future__ import annotations

import json
import pathlib

import pytest

import app.application.services.ollama_status_probe as probe_module
import app.application.services.shared_router as shared_router_module
from app import cli, cli_ai
from app.application.services.ollama_first_adapter import OLLAMA_MODEL_ID_PREFIX
from app.core.config import AppSettings
from tests.unit.ollama_helpers import (
    FailingHfAdapter,
    FakeHfAdapter,
    FakeOllamaServer,
    connect_refused,
    http,
    install_adapter,
    ok_chat,
    reset_shared_state,
    tags_response,
)

GOLDEN = pathlib.Path(__file__).with_name("fixtures") / "cli_ai_test_dry_run.json"

PROMPT_SENTINEL = "PROMPT_SHOULD_NOT_BE_PRINTED"
ANSWER_SENTINEL = "ANSWER_SHOULD_NOT_BE_PRINTED"


def run(argv, capsys):
    code = cli.main(argv)
    captured = capsys.readouterr()
    return code, captured.out, captured.err


@pytest.fixture(autouse=True)
def _reset():
    reset_shared_state()
    yield
    reset_shared_state()


@pytest.fixture
def token(monkeypatch):
    monkeypatch.setattr(cli_ai, "settings", AppSettings(supabase_jwt_secret="x" * 40, huggingface_token="hf_test"))


def _hf_table(output: str) -> str:
    """The Hugging Face table portion of ``models list`` output.

    The Ollama section is a separate block after a blank line, so splitting on
    it isolates the table that must stay byte-identical.
    """
    head, _, _tail = output.partition("\n\nOllama:")
    return head


def _hf_result(**overrides):
    base = {
        "content": "hf answer",
        "model_id": "fake/hf-model",
        "fallback_reason": None,
        "fallback_chain": ["fake/hf-model"],
        "routing_score": 0.5,
        "required_context": 64,
    }
    base.update({k: v for k, v in overrides.items() if v is not None})
    return base


def _ollama_status(monkeypatch, server=None, *, use_ollama: bool = True, model: str = "llama3.2:3b"):
    """Bind the CLI's probe to the *shared* wrapper.

    It must be the same instance the CLI reaches through ``get_adapter()``, or a
    test that trips the breaker on one wrapper would observe the other.
    """
    from tests.unit.ollama_helpers import make_settings

    wrapper = shared_router_module.get_adapter()
    probe = probe_module.OllamaStatusProbe(
        settings_obj=make_settings(use_ollama=use_ollama, ollama_model=model),
        adapter_getter=lambda: wrapper,
        circuit_state=lambda: wrapper.circuit_state,
        cache_ttl_seconds=5.0,
        clock=lambda: 1000.0,
    )
    probe_module.configure_probe(probe)
    return probe


# ---------------------------------------------------------------------------
# models list — the Ollama section
# ---------------------------------------------------------------------------
class TestModelsList:
    def test_up_and_model_installed_lists_provider_rows(self, monkeypatch, capsys):
        server = FakeOllamaServer(tags_script=[tags_response(["llama3.2:3b"])])
        wrapper = install_adapter(monkeypatch, server, FakeHfAdapter())
        _ollama_status(monkeypatch)

        code, out, _ = run(["models", "list"], capsys)

        assert code == 0
        assert "provider=ollama" in out
        assert "installed=yes" in out
        assert wrapper.ollama_model_id.endswith("llama3.2:3b")

    def test_the_hugging_face_table_is_untouched(self, monkeypatch, capsys):
        """The Ollama block is additive: the HF table keeps its exact format.

        Only the table itself is compared — the Ollama section that follows it
        is expected to change, because the two runs deliberately put the channel
        in different states.
        """
        code, baseline, _ = run(["models", "list"], capsys)
        assert code == 0
        expected = _hf_table(baseline)
        assert "MODEL" in expected

        server = FakeOllamaServer(tags_script=[tags_response(["llama3.2:3b"])])
        install_adapter(monkeypatch, server, FakeHfAdapter())
        _ollama_status(monkeypatch)

        code2, with_ollama, _ = run(["models", "list"], capsys)
        assert code2 == 0

        assert _hf_table(with_ollama) == expected
        # and the Ollama section is genuinely present in the second run
        assert "Ollama:" in with_ollama

    def test_model_missing_flags_the_fix(self, monkeypatch, capsys):
        server = FakeOllamaServer(tags_script=[tags_response(["mistral:7b"])])
        install_adapter(monkeypatch, server, FakeHfAdapter())
        _ollama_status(monkeypatch)

        code, out, _ = run(["models", "list"], capsys)

        assert code == 0
        assert "installed=no" in out
        assert "NOT INSTALLED" in out
        assert "ollama pull llama3.2:3b" in out

    def test_unreachable_prints_typed_state_and_keeps_the_exit_code(self, monkeypatch, capsys):
        server = FakeOllamaServer(tags_script=[connect_refused()])
        install_adapter(monkeypatch, server, FakeHfAdapter())
        _ollama_status(monkeypatch)

        code, out, err = run(["models", "list"], capsys)

        assert code == 0
        assert "Ollama: unreachable" in out
        assert "Traceback" not in out and "Traceback" not in err
        # no base URL or hostname reaches the console
        assert "ollama.test" not in out
        assert "11434" not in out

    def test_disabled_prints_disabled(self, monkeypatch, capsys):
        server = FakeOllamaServer(tags_script=[tags_response(["llama3.2:3b"])])
        install_adapter(monkeypatch, server, FakeHfAdapter())
        _ollama_status(monkeypatch, use_ollama=False)

        code, out, _ = run(["models", "list"], capsys)

        assert code == 0
        assert "Ollama: disabled" in out
        assert server.total_requests == 0

    def test_reachable_without_a_model_reports_installed_unknown(self, monkeypatch, capsys):
        """Reachable but nothing to compare: `unknown`, not a guessed yes/no."""
        server = FakeOllamaServer(tags_script=[tags_response(["llama3.2:3b"])])
        install_adapter(monkeypatch, server, FakeHfAdapter())
        _ollama_status(monkeypatch, model="")

        code, out, _ = run(["models", "list"], capsys)

        assert code == 0
        assert "installed=unknown" in out

    def test_open_breaker_is_shown_in_the_section(self, monkeypatch, capsys):
        server = FakeOllamaServer(tags_script=[tags_response(["llama3.2:3b"])])
        wrapper = install_adapter(monkeypatch, server, FakeHfAdapter())
        wrapper._breaker._state = "OPEN"
        _ollama_status(monkeypatch)

        code, out, _ = run(["models", "list"], capsys)

        assert code == 0
        assert "installed=yes" in out
        assert "circuit=open" in out

    def test_half_open_breaker_is_shown_in_the_section(self, monkeypatch, capsys):
        server = FakeOllamaServer(tags_script=[tags_response(["llama3.2:3b"])])
        wrapper = install_adapter(monkeypatch, server, FakeHfAdapter())
        wrapper._breaker._state = "HALF_OPEN"
        _ollama_status(monkeypatch)

        code, out, _ = run(["models", "list"], capsys)

        assert code == 0
        assert "circuit=half_open" in out


# ---------------------------------------------------------------------------
# ai test --live
# ---------------------------------------------------------------------------
class TestAiTestLive:
    def test_ollama_answering_reports_provider_ollama(self, monkeypatch, token, capsys):
        server = FakeOllamaServer([ok_chat(content="## Summary\nHere.\n\n## Steps\n- Start.", model="llama3.2:3b")])
        install_adapter(monkeypatch, server, FakeHfAdapter(_hf_result(content=ANSWER_SENTINEL)))

        code, out, err = run(["ai", "test", "--task", "career_advice", "--live", "--json"], capsys)

        assert code == 0, err
        live = json.loads(out)["live"]
        assert live["provider"] == "ollama"
        assert live["model_id"].startswith(OLLAMA_MODEL_ID_PREFIX)
        assert live["latency_ms"] >= 0
        # privacy: neither the prompt nor the model's answer is printed
        assert ANSWER_SENTINEL not in out and ANSWER_SENTINEL not in err
        assert "output_preview" not in out

    def test_ollama_down_falls_back_to_hf_and_reports_the_chain(self, monkeypatch, token, capsys):
        # Hugging Face answers (with a marker we can prove never leaks), so the
        # chain exercises the Ollama -> HF fallback rather than a total outage.
        server = FakeOllamaServer([http(404)])
        install_adapter(monkeypatch, server, FakeHfAdapter(_hf_result(content=ANSWER_SENTINEL)))

        code, out, err = run(["ai", "test", "--task", "career_advice", "--live", "--json"], capsys)

        assert code == 0, err
        live = json.loads(out)["live"]
        assert live["provider"] == "huggingface"
        assert live["fallback_chain"][0].startswith(OLLAMA_MODEL_ID_PREFIX)
        assert live.get("fallback_reason")
        # the answer still never reaches the console
        assert ANSWER_SENTINEL not in out and ANSWER_SENTINEL not in err

    def test_both_down_reports_the_typed_failure_and_exit_1(self, monkeypatch, token, capsys):
        server = FakeOllamaServer([http(404)])
        install_adapter(monkeypatch, server, FailingHfAdapter())

        code, out, err = run(["ai", "test", "--live", "--json"], capsys)

        assert code == 1
        payload = json.loads(out)
        assert payload["failure_class"]
        assert "Failure class:" in err
        assert "Traceback" not in out and "Traceback" not in err

    def test_human_readable_form_also_reports_the_provider(self, monkeypatch, token, capsys):
        server = FakeOllamaServer([ok_chat(content="## Summary\nHere.\n\n## Steps\n- Start.", model="llama3.2:3b")])
        install_adapter(monkeypatch, server, FakeHfAdapter())

        code, out, _ = run(["ai", "test", "--task", "career_advice", "--live"], capsys)

        assert code == 0
        # the human-readable form reports the model id, whose prefix is the provider
        assert f"model={OLLAMA_MODEL_ID_PREFIX}" in out

    def test_no_content_is_printed_in_any_form(self, monkeypatch, token, capsys):
        for extra in (["--json"], []):
            server = FakeOllamaServer([ok_chat(content=ANSWER_SENTINEL, model="llama3.2:3b")])
            install_adapter(monkeypatch, server, FakeHfAdapter())

            code, out, err = run(["ai", "test", "--live", *extra], capsys)

            assert code == 0
            assert ANSWER_SENTINEL not in out
            assert ANSWER_SENTINEL not in err


# ---------------------------------------------------------------------------
# ai test without --live — the golden output
# ---------------------------------------------------------------------------
class TestDryRunIsGolden:
    """The pre-change dry-run behaviour must stay exactly as captured."""

    def test_golden_fixture_exists(self):
        assert GOLDEN.exists(), f"missing golden fixture: {GOLDEN}"

    def test_text_form_matches_the_golden_output(self, monkeypatch, token, capsys):
        golden = json.loads(GOLDEN.read_text())["text"]

        monkeypatch.setattr(
            cli_ai.HuggingFaceInferenceAdapter,
            "_call_model",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("dry run must not call the provider")),
        )
        code, out, err = run(["ai", "test", "--task", "career_advice"], capsys)

        assert code == golden["exit_code"]
        assert out == golden["stdout"]
        assert "Traceback" not in err

    def test_json_form_matches_the_golden_output(self, monkeypatch, token, capsys):
        golden = json.loads(GOLDEN.read_text())["json"]

        monkeypatch.setattr(
            cli_ai.HuggingFaceInferenceAdapter,
            "_call_model",
            lambda *a, **k: (_ for _ in ()).throw(AssertionError("dry run must not call the provider")),
        )
        code, out, _ = run(["ai", "test", "--task", "career_advice", "--json"], capsys)

        payload = json.loads(out)
        assert code == golden["exit_code"]
        # compare the parsed payload, so formatting-only drift is ignored
        assert payload == golden["payload"]
        # and the dry run must never carry a live section
        assert "live" not in payload
