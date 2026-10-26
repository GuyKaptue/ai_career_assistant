"""Contract tests for the Ollama compose stack (Sub-step 6 → committed 7a).

The compose file is deployment configuration and receives the same treatment as
the database schema: a contract test that parses the YAML and asserts every
guarantee the Ollama services rely on. No Docker daemon is required, so this
runs in any CI environment.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[3]
COMPOSE = REPO_ROOT / "docker-compose.yml"
GPU_OVERRIDE = REPO_ROOT / "docker-compose.gpu.yml"
ENV_EXAMPLE = REPO_ROOT / ".env.example"
CONFIG_PY = REPO_ROOT / "backend" / "app" / "core" / "config.py"

#: The exact env-var names ``AppSettings.from_env()`` reads for the Ollama config.
#: Kept in sync with backend/app/core/config.py.
CONFIG_OLLAMA_KEYS = (
    "USE_OLLAMA",
    "OLLAMA_BASE_URL",
    "OLLAMA_MODEL",
    "OLLAMA_TIMEOUT_SECONDS",
    "OLLAMA_CONNECT_TIMEOUT_SECONDS",
    "OLLAMA_KEEP_ALIVE",
    "OLLAMA_TEMPERATURE",
    "OLLAMA_NUM_CTX",
)

#: Variables forwarded by the backend service, with the default each source uses.
EXPECTED_DEFAULTS = {
    "USE_OLLAMA": "true",
    "OLLAMA_MODEL": "llama3.2:3b",
    "OLLAMA_TIMEOUT_SECONDS": "10",
    "OLLAMA_CONNECT_TIMEOUT_SECONDS": "3",
    "OLLAMA_KEEP_ALIVE": "5m",
    "OLLAMA_TEMPERATURE": "0.3",
    "OLLAMA_NUM_CTX": "8192",
    "OLLAMA_IMAGE_TAG": "0.40.3",
}


@pytest.fixture(scope="module")
def compose() -> dict:
    with COMPOSE.open() as handle:
        return yaml.safe_load(handle)


@pytest.fixture(scope="module")
def gpu() -> dict:
    with GPU_OVERRIDE.open() as handle:
        return yaml.safe_load(handle)


@pytest.fixture(scope="module")
def compose_text() -> str:
    return COMPOSE.read_text()


# ---------------------------------------------------------------------------
# The ollama service
# ---------------------------------------------------------------------------
class TestOllamaService:
    def test_image_is_official_and_tag_pinned(self, compose):
        image = compose["services"]["ollama"]["image"]
        assert image.startswith("ollama/ollama:")
        assert not image.endswith(":latest")

    def test_image_tag_is_a_semver_default_and_overridable(self, compose):
        image = compose["services"]["ollama"]["image"]
        match = re.search(r"\$\{OLLAMA_IMAGE_TAG:-([^}]+)\}", image)
        assert match, "the pin must be overridable through an env var"
        assert re.fullmatch(r"0\.\d+\.\d+", match.group(1))

    def test_port_is_bound_to_loopback_only(self, compose):
        assert compose["services"]["ollama"]["ports"] == ["127.0.0.1:11434:11434"]

    def test_no_service_binds_ollama_to_all_interfaces(self, compose):
        for name, service in compose["services"].items():
            for port in service.get("ports", []):
                assert not str(port).startswith("11434:"), f"{name} exposes ollama on all interfaces"

    def test_named_volume_is_mounted_at_the_expected_path(self, compose):
        volumes = compose["services"]["ollama"]["volumes"]
        assert "ollama_data:/root/.ollama" in volumes

    def test_volume_is_declared_at_the_top_level(self, compose):
        assert "ollama_data" in compose["volumes"]

    def test_restart_policy_is_unless_stopped(self, compose):
        assert compose["services"]["ollama"]["restart"] == "unless-stopped"

    def test_healthcheck_uses_the_images_own_cli(self, compose):
        healthcheck = compose["services"]["ollama"]["healthcheck"]
        assert healthcheck["test"] == ["CMD", "ollama", "list"]

    def test_healthcheck_tunings(self, compose):
        healthcheck = compose["services"]["ollama"]["healthcheck"]
        assert healthcheck["interval"] == "10s"
        assert healthcheck["timeout"] == "5s"
        assert healthcheck["retries"] == 10
        assert healthcheck["start_period"] == "10s"

    @pytest.mark.parametrize(
        ("forbidden", "yaml_key"),
        [
            ("privileged", "privileged"),
            ("host_network", "network_mode"),
            ("secrets", "secrets"),
            ("environment_api_keys", "environment"),
        ],
    )
    def test_no_secrets_no_privileged_no_host_network(self, compose, forbidden, yaml_key):
        service = compose["services"]["ollama"]
        if yaml_key == "environment":
            environment = service.get("environment") or {}
            for key in environment:
                lowered = str(key).lower()
                assert "key" not in lowered and "secret" not in lowered and "token" not in lowered
            return
        assert yaml_key not in service or not service[yaml_key]

    def test_base_file_has_no_gpu_block(self, compose):
        assert "deploy" not in compose["services"]["ollama"]


# ---------------------------------------------------------------------------
# The ollama-pull one-shot
# ---------------------------------------------------------------------------
class TestOllamaPullService:
    def test_uses_the_same_pinned_image(self, compose):
        assert compose["services"]["ollama-pull"]["image"] == compose["services"]["ollama"]["image"]

    def test_restart_is_no_so_the_exit_code_stays_visible(self, compose):
        assert compose["services"]["ollama-pull"]["restart"] == "no"

    def test_hard_depends_on_a_healthy_ollama(self, compose):
        dependency = compose["services"]["ollama-pull"]["depends_on"]["ollama"]
        assert dependency["condition"] == "service_healthy"

    def test_ollama_host_points_at_the_service_name(self, compose):
        assert compose["services"]["ollama-pull"]["environment"]["OLLAMA_HOST"] == "http://ollama:11434"

    def test_entrypoint_fails_closed(self, compose):
        entrypoint = compose["services"]["ollama-pull"]["entrypoint"]
        command = entrypoint[2]
        assert "set -eu;" in command
        assert "$$OLLAMA_MODEL" in command
        assert "ollama pull" in command

    def test_model_name_is_not_duplicated_in_compose(self, compose_text):
        """Both services read the one variable; the default appears twice max."""
        occurrences = len(re.findall(r"\$\{OLLAMA_MODEL:-", compose_text))
        # one in the backend's env, one in the pull service
        assert occurrences == 2


# ---------------------------------------------------------------------------
# The backend service
# ---------------------------------------------------------------------------
class TestBackendService:
    @pytest.fixture
    def env(self, compose) -> dict:
        return compose["services"]["backend"]["environment"]

    def test_dependency_is_soft_not_service_healthy(self, compose):
        dependency = compose["services"]["backend"]["depends_on"]["ollama"]
        assert dependency["condition"] == "service_started"
        assert dependency.get("required") is False

    def test_forwards_every_ollama_setting(self, env):
        for key in CONFIG_OLLAMA_KEYS:
            assert key in env, f"the backend must forward {key}"

    def test_base_url_points_at_the_service_name(self, env):
        assert env["OLLAMA_BASE_URL"] == "${OLLAMA_BASE_URL:-http://ollama:11434}"

    def test_defaults_match_config_py(self, env):
        config = CONFIG_PY.read_text()
        #: keys whose defaults are numbers, compared numerically
        numeric = {
            "OLLAMA_TIMEOUT_SECONDS",
            "OLLAMA_CONNECT_TIMEOUT_SECONDS",
            "OLLAMA_TEMPERATURE",
            "OLLAMA_NUM_CTX",
        }
        for key in (
            "OLLAMA_MODEL",
            "OLLAMA_TIMEOUT_SECONDS",
            "OLLAMA_CONNECT_TIMEOUT_SECONDS",
            "OLLAMA_KEEP_ALIVE",
            "OLLAMA_TEMPERATURE",
            "OLLAMA_NUM_CTX",
        ):
            # ``os.getenv("KEY", <default>)``, optionally wrapped in a parser
            # call such as ``parse_float_setting(os.getenv("KEY"), 120.0, ...)``
            match = re.search(rf'getenv\("{key}"(?:\s*\))?\s*,\s*([^)\s,]+)', config)
            assert match, f"{key} must be read by config.py"
            configured = match.group(1).strip('"')
            compose_value = env[key]
            default = re.search(r"\$\{" + key + r":-([^}]*)\}", compose_value)
            assert default, f"{key} must carry a default"
            compose_default = default.group(1)
            if key in numeric:
                assert float(compose_default) == float(configured), f"{key} default drifted"
            else:
                assert compose_default == configured, f"{key} default drifted"

    def test_use_ollama_defaults_to_true(self, env):
        assert env["USE_OLLAMA"].endswith(":-true}")

    def test_other_backend_settings_are_unchanged(self, env):
        # The Ollama block is additive; the pre-existing keys keep their values.
        assert env["JOB_PROVIDER"] == "${JOB_PROVIDER:-arbeitsagentur,arbeitnow}"
        assert env["LOG_LEVEL"] == "${LOG_LEVEL:-INFO}"

    def test_backend_port_and_healthcheck_are_unchanged(self, compose):
        service = compose["services"]["backend"]
        assert service["ports"] == ["8000:8000"]
        assert service["healthcheck"]["interval"] == "10s"


# ---------------------------------------------------------------------------
# GPU override
# ---------------------------------------------------------------------------
class TestGpuOverride:
    def test_file_exists(self):
        assert GPU_OVERRIDE.exists()

    def test_requests_the_nvidia_gpu(self, gpu):
        device = gpu["services"]["ollama"]["deploy"]["resources"]["reservations"]["devices"][0]
        assert device["driver"] == "nvidia"
        assert device["capabilities"] == ["gpu"]

    def test_override_only_targets_ollama(self, gpu):
        assert list(gpu["services"]) == ["ollama"]


# ---------------------------------------------------------------------------
# Cross-file consistency (requirement F, automated)
# ---------------------------------------------------------------------------
class TestConsistencyAcrossFiles:
    def test_env_example_declares_every_forwarded_variable(self):
        text = ENV_EXAMPLE.read_text()
        for key in CONFIG_OLLAMA_KEYS:
            assert re.search(rf"^{key}=", text, re.M), f".env.example must document {key}"
        assert "OLLAMA_IMAGE_TAG=0.40.3" in text

    def test_compose_defaults_match_env_example(self):
        text = ENV_EXAMPLE.read_text()
        for key, expected in EXPECTED_DEFAULTS.items():
            if key == "OLLAMA_BASE_URL":
                continue  # intentionally differs: container network vs localhost
            match = re.search(rf"^{key}=(.*)$", text, re.M)
            assert match, f".env.example must set {key}"
            assert match.group(1).split("#")[0].strip() == expected, f"{key} default drifted from .env.example"

    def test_compose_pin_matches_env_example(self, compose_text):
        assert "${OLLAMA_IMAGE_TAG:-0.40.3}" in compose_text
        assert "OLLAMA_IMAGE_TAG=0.40.3" in ENV_EXAMPLE.read_text()

    def test_no_latest_tag_anywhere(self, compose_text):
        for line in compose_text.splitlines():
            code = line.split("#", 1)[0]
            assert ":latest" not in code, f"'latest' is not a pin: {line.strip()}"

    @pytest.mark.parametrize("target", ["ollama-up", "ollama-pull", "ollama-logs", "ollama-gpu-up"])
    def test_ollama_targets_never_swallow_an_error(self, target):
        """The `clean` target legitimately uses `|| true` for a missing file;
        the Ollama targets must not, so a failure is always visible."""
        makefile = (REPO_ROOT / "Makefile").read_text()
        block = re.search(rf"^{target}:\n(?:\t.*\n)+", makefile, re.M)
        assert block, f"{target} must exist with a recipe"
        assert "|| true" not in block.group(0)

    def test_ollama_pull_propagates_the_one_shot_exit_code(self):
        makefile = (REPO_ROOT / "Makefile").read_text()
        block = re.search(r"^ollama-pull:\n(?:\t.*\n)+", makefile, re.M)
        assert "--exit-code-from ollama-pull" in block.group(0)

    def test_ollama_targets_exist_and_use_compose(self):
        makefile = (REPO_ROOT / "Makefile").read_text()
        for target in ("ollama-up", "ollama-pull", "ollama-logs"):
            assert re.search(rf"^{target}:", makefile, re.M), f"{target} must exist"
        assert "docker compose up -d --wait ollama" in makefile
        assert "--exit-code-from ollama-pull" in makefile
