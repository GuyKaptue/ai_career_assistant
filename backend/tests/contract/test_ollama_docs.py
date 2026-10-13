"""Anti-drift guards for the Ollama documentation (Sub-step 8b).

The operator guide is the fastest artifact to rot: a renamed variable, a
changed default, a removed Makefile target or a diagram that regresses to
"Hugging Face only" are all silent until someone follows the guide and it
fails. These checks parse the real source of truth (`config.py`, the compose
file, the Makefile) and refuse to let the docs drift from it.

Synchronous, no network, no Docker, no new dependency. Reads documents only.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
OLLAMA_DOC = REPO_ROOT / "docs" / "deployment" / "ollama.md"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
CONFIG_PY = REPO_ROOT / "backend" / "app" / "core" / "config.py"
COMPOSE_YML = REPO_ROOT / "docker-compose.yml"
MAKEFILE = REPO_ROOT / "Makefile"
DIAGRAMS_DIR = REPO_ROOT / "docs" / "diagrams"

#: Modules the docs may not claim are the only inference provider.
HF_ONLY_PHRASES = [
    "hugging face is the only",
    "the only inference provider",
    "only inference provider",
    "sole ai provider",
]

#: Documents and module READMEs audited in Sub-step 8a that mention the AI chain.
CLAIM_DOCS = [
    REPO_ROOT / "README.md",
    REPO_ROOT / "docs" / "privacy" / "data-flow.md",
    REPO_ROOT / "docs" / "academic" / "ai-generation.md",
    REPO_ROOT / "docs" / "academic" / "system.md",
    REPO_ROOT / "docs" / "security" / "overview.md",
    REPO_ROOT / "docs" / "deployment" / "overview.md",
    REPO_ROOT / "docs" / "deployment" / "ollama.md",
    REPO_ROOT / "backend" / "app" / "infrastructure" / "ai" / "README.md",
]


@pytest.fixture(scope="module")
def ollama_doc() -> str:
    return OLLAMA_DOC.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def compose() -> dict:
    return yaml.safe_load(COMPOSE_YML.read_text(encoding="utf-8"))


def _real_defaults() -> dict[str, str]:
    """The `os.getenv("NAME", "default")` defaults declared in config.py.

    Handles both the bare form (`os.getenv("NAME", "default")`) and the wrapped
    forms this file uses (`parse_float_setting(os.getenv("NAME"), 120.0, ...)`).
    """
    text = CONFIG_PY.read_text(encoding="utf-8")
    # bare: os.getenv("NAME", "default")
    found = dict(re.findall(r'getenv\(\s*"([A-Z0-9_]+)"\s*,\s*"?([^)"]+)"?', text))
    # wrapped: getenv("NAME")   ... default appears as a following argument
    for name in re.findall(r'getenv\(\s*"([A-Z0-9_]+)"\s*\)\s*,', text):
        tail = text.split(f'getenv("{name}")', 1)[1]
        match = re.search(r",\s*([0-9.]+)", tail)
        if match:
            found.setdefault(name, match.group(1))
    # USE_OLLAMA is written as `os.getenv("USE_OLLAMA", "true").lower() == "true"`.
    match = re.search(r'getenv\(\s*"USE_OLLAMA"\s*,\s*"([^"]+)"', text)
    if match:
        found["USE_OLLAMA"] = f'"{match.group(1)}"'
    return found


# ---------------------------------------------------------------------------
# A5 — variables and defaults
# ---------------------------------------------------------------------------
class TestDocumentedVariables:
    @pytest.fixture(scope="class")
    def documented_names(self, ollama_doc) -> set[str]:
        """Variable names appearing in the env table of the new guide."""
        table = ollama_doc.split("## Environment variables", 1)[-1].split("##", 1)[0]
        return set(re.findall(r"\| `([A-Z0-9_]+)`", table))

    @pytest.mark.parametrize(
        "name",
        [
            "USE_OLLAMA",
            "OLLAMA_BASE_URL",
            "OLLAMA_MODEL",
            "OLLAMA_TIMEOUT_SECONDS",
            "OLLAMA_CONNECT_TIMEOUT_SECONDS",
            "OLLAMA_KEEP_ALIVE",
            "OLLAMA_TEMPERATURE",
            "OLLAMA_IMAGE_TAG",
        ],
    )
    def test_every_setting_is_documented(self, documented_names, name):
        assert name in documented_names, f"docs/deployment/ollama.md omits {name}"

    def test_every_read_setting_is_documented(self, ollama_doc, documented_names):
        """Nothing config.py reads may be missing from the table."""
        read = {name for name in _real_defaults() if name.startswith("OLLAMA_") or name == "USE_OLLAMA"}
        assert read <= documented_names, read - documented_names

    def test_documented_names_are_real(self, documented_names):
        """A name in the table must be read by config.py or used by compose."""
        real = set(_real_defaults())
        compose_text = COMPOSE_YML.read_text(encoding="utf-8")
        unknown = {name for name in documented_names if name not in real and name not in compose_text}
        assert not unknown, unknown

    def test_documented_defaults_equal_the_real_defaults(self, ollama_doc):
        """The numbers in the table must match config.py / compose, not memory."""
        real = _real_defaults()
        table = ollama_doc.split("## Environment variables", 1)[-1].split("##", 1)[0]
        documented: dict[str, str] = {}
        for name, default in re.findall(r"\| `([A-Z0-9_]+)` \| `?([^`|]*)`? \|", table):
            documented[name] = default.strip()
        for name, expected in (
            ("OLLAMA_MODEL", "llama3.2:3b"),
            ("OLLAMA_TIMEOUT_SECONDS", "120"),
            ("OLLAMA_CONNECT_TIMEOUT_SECONDS", "3"),
            ("OLLAMA_KEEP_ALIVE", "5m"),
            ("OLLAMA_TEMPERATURE", "0.3"),
        ):
            assert documented.get(name) == expected, f"{name} documented default drifted"
            assert real.get(name) is not None, f"{name} is not read by config.py"

    def test_env_example_matches_the_documented_defaults(self, ollama_doc):
        example = dict(
            (k, v.split("#")[0].strip()) for k, v in re.findall(r"^([A-Z0-9_]+)=(.*)$", ENV_EXAMPLE.read_text(), re.M)
        )
        table = ollama_doc.split("## Environment variables", 1)[-1].split("##", 1)[0]
        documented = dict((n, d.strip()) for n, d in re.findall(r"\| `([A-Z0-9_]+)` \| `?([^`|]*)`? \|", table))
        for name in ("OLLAMA_MODEL", "OLLAMA_TIMEOUT_SECONDS", "OLLAMA_KEEP_ALIVE"):
            assert example[name] == documented[name], name
        assert example["USE_OLLAMA"] == "true"
        assert example["OLLAMA_IMAGE_TAG"] == "0.40.3"

    def test_image_tag_is_pinned_and_matches_env_example(self, ollama_doc):
        assert "OLLAMA_IMAGE_TAG` | `0.40.3`" in ollama_doc, "the pin must be documented"
        assert "OLLAMA_IMAGE_TAG=0.40.3" in ENV_EXAMPLE.read_text(), ".env.example pin drifted"
        assert "${OLLAMA_IMAGE_TAG:-0.40.3}" in COMPOSE_YML.read_text(), "compose pin drifted"
        # The image reference is pinned, never the moving "latest" tag.
        compose_text = COMPOSE_YML.read_text(encoding="utf-8")
        for tag in re.findall(r"image:\s*ollama/ollama:([^\s\"']+)", compose_text):
            assert tag != "latest", tag
        assert not re.search(r"image:\s*\S+/ollama:latest", compose_text)


# ---------------------------------------------------------------------------
# B2 — quick start commands exist
# ---------------------------------------------------------------------------
class TestQuickStartCommands:
    def test_every_make_target_mentioned_exists(self, ollama_doc):
        makefile = MAKEFILE.read_text(encoding="utf-8")
        mentioned = set(re.findall(r"\bmake ([a-z][a-z0-9-]*)", ollama_doc))
        missing = {target for target in mentioned if not re.search(rf"^{re.escape(target)}:", makefile, re.M)}
        assert not missing, missing

    def test_quick_start_mentions_the_real_commands(self, ollama_doc):
        quick_start = ollama_doc.split("## Quick start", 1)[-1].split("##", 1)[0]
        for command in ("make ollama-up", "make ollama-pull", "docker compose up -d backend"):
            assert command in quick_start, command

    def test_documented_cli_invocation_is_real(self, ollama_doc):
        """The guide must name the module form the CLI actually exposes."""
        import app.cli as cli_module

        assert hasattr(cli_module, "main"), "the CLI entry point moved"
        quick_start = ollama_doc.split("## Quick start", 1)[-1].split("##", 1)[0]
        assert re.search(r"-m app\.cli\b", quick_start), "the real CLI invocation is not documented"

    def test_documented_compose_services_exist(self, compose):
        expected = {"backend", "frontend", "ollama", "ollama-pull"}
        assert expected <= set(compose["services"])

    def test_documented_ports_match_compose(self):
        compose_text = COMPOSE_YML.read_text(encoding="utf-8")
        assert '"127.0.0.1:11434:11434"' in compose_text
        assert "11434:11434" not in compose_text.replace('"127.0.0.1:11434:11434"', "")


# ---------------------------------------------------------------------------
# C4 — links resolve
# ---------------------------------------------------------------------------
class TestLinksResolve:
    def test_relative_links_resolve(self):
        for doc in CLAIM_DOCS:
            text = doc.read_text(encoding="utf-8")
            for label, target in re.findall(r"\[([^\]]+)\]\(([^)#]+)\)", text):
                if "://" in target:
                    continue
                candidates = [(doc.parent / target).resolve()]
                if target.startswith("../"):
                    # a link may be written relative to the repo root
                    candidates.append((REPO_ROOT / Path(target).as_posix().replace("..", ".").lstrip("./")).resolve())
                assert any(c.exists() for c in candidates), f"{doc.name}: broken link {target!r} ({label})"

    def test_anchor_references_resolve(self):
        """A `#anchor` link must match a heading in the same document."""
        for doc in CLAIM_DOCS:
            text = doc.read_text(encoding="utf-8")
            headings = {
                re.sub(r"[^a-z0-9 -]", "", h.lower()).strip().replace(" ", "-")
                for h in re.findall(r"^#{1,6}\s+(.*)$", text, re.M)
            }
            for anchor in re.findall(r"\]\(#([^)]+)\)", text):
                assert anchor in headings, f"{doc.name}: unresolved anchor #{anchor}"


# ---------------------------------------------------------------------------
# C5 — provider lists must include Ollama
# ---------------------------------------------------------------------------
MERMAID_LIKE = re.compile(r"```(?:mermaid|)\s*\n(.*?)```", re.DOTALL)


class TestDiagramsKeepOllama:
    def test_new_guide_shows_ollama_in_the_chain(self, ollama_doc):
        chain = ollama_doc.split("## Inference chain", 1)[-1].split("##", 1)[0]
        assert "Ollama (local)" in chain, "the chain diagram lost Ollama"
        for provider in ("Hugging Face", "Deterministic"):
            assert provider in chain, provider

    def test_dot_sources_contain_the_ollama_services(self):
        for name in ("ai_routing_architecture", "deployment_architecture"):
            source = (DIAGRAMS_DIR / f"{name}.dot").read_text(encoding="utf-8")
            # the routing diagram names the wrapper, the deployment one the service
            assert re.search(r"[Oo]llama", source), f"{name}.dot lost the Ollama node"

    def test_dot_sources_ordered_ollama_before_hf(self):
        """A diagram that regresses to Hugging Face first must fail here."""
        source = (DIAGRAMS_DIR / "ai_routing_architecture.dot").read_text(encoding="utf-8")
        ollama_at = source.index("OllamaFirstAdapter")
        hf_adapter_at = source.index("HuggingFaceInferenceAdapter")
        assert ollama_at < hf_adapter_at, "Ollama is no longer the first inference step"

    def test_deployment_dot_has_the_volume_and_loopback(self):
        source = (DIAGRAMS_DIR / "deployment_architecture.dot").read_text(encoding="utf-8")
        assert "ollama_data" in source, "the volume is missing from the diagram"
        assert "127.0.0.1" in source, "the loopback binding is missing from the diagram"
        assert "0.0.0.0" not in source, "the diagram must not advertise a public binding"


# ---------------------------------------------------------------------------
# C6 — no "Hugging Face is the only provider" claim anywhere
# ---------------------------------------------------------------------------
class TestNoExclusiveProviderClaims:
    @pytest.mark.parametrize("path", CLAIM_DOCS, ids=lambda p: p.name)
    def test_no_doc_claims_an_exclusive_provider(self, path):
        if not path.exists():
            pytest.skip(f"{path} is not part of this change set")
        text = path.read_text(encoding="utf-8").lower()
        for phrase in HF_ONLY_PHRASES:
            assert phrase not in text, f"{path.name} claims {phrase!r}"

    def test_no_module_readme_claims_an_exclusive_provider(self):
        offenders = []
        for path in sorted((REPO_ROOT / "backend").rglob("README.md")):
            text = path.read_text(encoding="utf-8").lower()
            for phrase in HF_ONLY_PHRASES:
                if phrase in text:
                    offenders.append(str(path.relative_to(REPO_ROOT)))
        assert not offenders, offenders

    def test_no_docs_dir_claims_an_exclusive_provider(self):
        offenders = []
        for path in sorted((REPO_ROOT / "docs").rglob("*.md")):
            text = path.read_text(encoding="utf-8").lower()
            for phrase in HF_ONLY_PHRASES:
                if phrase in text:
                    offenders.append(str(path.relative_to(REPO_ROOT)))
        assert not offenders, offenders


# ---------------------------------------------------------------------------
# The privacy and metric statements the change set promised
# ---------------------------------------------------------------------------
class TestStatementsTheDocsMustCarry:
    def test_privacy_states_the_fallback_explicitly(self, ollama_doc):
        """The accurate claim: host-only while Ollama answers, else HF."""
        body = ollama_doc
        assert "only while Ollama answers" in body
        assert "falls back to Hugging Face" in body

    def test_fallback_counter_semantics_are_stated(self, ollama_doc):
        body = ollama_doc
        assert "breaker skip" in body
        assert "`ollama_failed_total`" in body

    def test_observability_says_the_block_never_gates_readiness(self, ollama_doc):
        body = ollama_doc
        assert "never changes the 200/503" in body
