import os
import sys
from dataclasses import dataclass
from pathlib import Path

import httpx

# Option 3 runtime policy: only Supabase is required at boot; HF_TOKEN and
# Ollama are optional (degraded readiness, never 503 gating).
REQUIRED_RUNTIME_ENV_KEYS = (
    "SUPABASE_URL",
    "SUPABASE_SERVICE_ROLE_KEY",
    "SUPABASE_JWT_SECRET",
)


def load_environment(file_path: str | os.PathLike[str] | None = None) -> None:
    env_path = Path(file_path) if file_path is not None else Path(__file__).resolve().parents[3] / ".env"
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        os.environ.setdefault(key, value)


def _running_under_pytest() -> bool:
    """True when this process is a pytest run, regardless of how it was launched.

    ``python -m pytest`` sets ``sys.argv[0]`` to the pytest package's
    ``__main__.py`` (so a basename check for "pytest" misses it), and
    ``PYTEST_CURRENT_TEST`` is only populated *while* a test executes — never
    during module import, which is exactly when ``settings = AppSettings.from_env()``
    runs. Checking ``sys.modules`` is reliable for every launch style, because
    pytest has already imported itself before it imports our test modules.
    """
    if "pytest" in sys.modules:
        return True
    if "PYTEST_CURRENT_TEST" in os.environ:
        return True
    return "pytest" in os.path.basename(sys.argv[0]).lower()


if not _running_under_pytest():
    load_environment()

# Both host spellings are listed because the browser sends the origin exactly
# as it was typed in the address bar — "127.0.0.1" and "localhost" are
# distinct origins for CORS. Vite falls back to 5174/5175… when 5173 is taken,
# so the common fallback ports are included too; the dev server also proxies
# /api so CORS is usually not involved at all (see frontend/vite.config.js).
DEFAULT_CORS_ORIGINS: tuple[str, ...] = (
    "http://localhost:5173",
    "http://localhost:5174",
    "http://localhost:5175",
    "http://localhost:4173",
    "http://localhost:3000",
    "http://127.0.0.1:5173",
    "http://127.0.0.1:5174",
    "http://127.0.0.1:5175",
    "http://127.0.0.1:4173",
    "http://127.0.0.1:3000",
)


def parse_cors_origins(raw: str | None) -> tuple[str, ...]:
    """Comma-separated CORS_ORIGINS env var -> tuple. Explicit allowlist only (§26)."""
    if not raw:
        return DEFAULT_CORS_ORIGINS
    origins = tuple(origin.strip() for origin in raw.split(",") if origin.strip())
    return origins or DEFAULT_CORS_ORIGINS


DEFAULT_RATE_LIMIT_PER_MINUTE = 600


def parse_rate_limit(raw: str | None) -> int:
    """RATE_LIMIT_PER_MINUTE env var -> int; 0 disables, invalid falls back to the default (§12)."""
    if raw is None or not raw.strip():
        return DEFAULT_RATE_LIMIT_PER_MINUTE
    try:
        value = int(raw.strip())
    except ValueError:
        return DEFAULT_RATE_LIMIT_PER_MINUTE
    return max(0, value)


def parse_int_setting(raw: str | None, default: int, minimum: int = 0) -> int:
    """Generic int env var with fail-safe fallback (DYNAMIC_HF_PROMPT §41)."""
    if raw is None or not raw.strip():
        return default
    try:
        value = int(raw.strip())
    except ValueError:
        return default
    return max(minimum, value)


def parse_id_list(raw: str | None) -> tuple[str, ...]:
    """Comma-separated id list env var -> tuple (empty when unset)."""
    if not raw:
        return ()
    return tuple(item.strip() for item in raw.split(",") if item.strip())


def parse_float_setting(raw: str | None, default: float, minimum: float = 0.0) -> float:
    """Generic float env var with fail-safe fallback (same style as parse_int_setting)."""
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw.strip())
    except ValueError:
        return default
    return max(minimum, value)


@dataclass(frozen=True)
class AppSettings:
    app_name: str = "AI Career Assistant"
    environment: str = "development"
    debug: bool = False
    supabase_url: str | None = None
    supabase_anon_key: str | None = None
    supabase_service_role_key: str | None = None
    supabase_jwt_secret: str | None = None
    huggingface_token: str | None = None
    database_url: str | None = None
    default_template: str = "professional"
    cors_origins: tuple[str, ...] = DEFAULT_CORS_ORIGINS
    rate_limit_per_minute: int = DEFAULT_RATE_LIMIT_PER_MINUTE
    log_level: str = "INFO"
    # --- AI router (DYNAMIC_HF_PROMPT §6/§9/§12/§26) ---
    ai_approved_model_ids: tuple[str, ...] = ()  # models cleared for REQUIRES_REVIEW licenses
    context_safety_margin: int = 256  # tokens added on top of required_context (§9)
    ai_max_fallback_depth: int = 5  # bounded fallback chain (§16)
    routing_weights: str = ""  # "task=0.3,language=0.2,..." — parsed by ai_scoring
    # --- AI discovery (DYNAMIC_HF_PROMPT §5) ---
    ai_enable_discovery: bool = True  # enable dynamic model discovery at startup
    ai_discovery_query: str = "instruct"  # search query for HF Hub
    ai_discovery_limit: int = 20  # max models to discover
    ai_max_parameters: int | None = None  # max parameter count for discovered models
    # --- Ollama local inference (RD-01; no API key, no billing) ---
    use_ollama: bool = True  # try local Ollama first, then Hugging Face, then template
    ollama_base_url: str = "http://localhost:11434"  # in Docker: http://ollama:11434
    ollama_model: str = "llama3.2:3b"  # alternatives: mistral:7b, qwen3:8b
    ollama_timeout_seconds: float = 10.0  # full generation timeout
    ollama_connect_timeout_seconds: float = 3.0  # fast fail so HF fallback stays snappy
    ollama_keep_alive: str = "5m"  # how long Ollama keeps the model loaded
    ollama_temperature: float = 0.3  # low for factual career documents
    ollama_num_ctx: int = 8192  # context window (tokens) per Ollama call (F1)
    # --- Ollama remote access (tunnel). Header is sent only when both are set.
    ollama_auth_header: str | None = None
    ollama_auth_token: str | None = None

    @classmethod
    def from_env(cls) -> "AppSettings":
        return cls(
            app_name=os.getenv("APP_NAME", "AI Career Assistant"),
            environment=os.getenv("APP_ENV", "development"),
            debug=os.getenv("APP_DEBUG", "false").lower() == "true",
            supabase_url=os.getenv("SUPABASE_URL"),
            supabase_anon_key=os.getenv("SUPABASE_ANON_KEY"),
            supabase_service_role_key=os.getenv("SUPABASE_SERVICE_ROLE_KEY"),
            supabase_jwt_secret=os.getenv("SUPABASE_JWT_SECRET"),
            huggingface_token=os.getenv("HF_TOKEN") or os.getenv("HUGGINGFACE_TOKEN"),
            database_url=os.getenv("DATABASE_URL") or os.getenv("SUPABASE_DB_URL"),
            default_template=os.getenv("DEFAULT_TEMPLATE", "professional"),
            cors_origins=parse_cors_origins(os.getenv("CORS_ORIGINS")),
            rate_limit_per_minute=parse_rate_limit(os.getenv("RATE_LIMIT_PER_MINUTE")),
            log_level=(os.getenv("LOG_LEVEL") or "INFO").upper(),
            ai_approved_model_ids=parse_id_list(os.getenv("AI_APPROVED_MODEL_IDS")),
            context_safety_margin=parse_int_setting(os.getenv("CONTEXT_SAFETY_MARGIN"), 256),
            ai_max_fallback_depth=parse_int_setting(os.getenv("AI_MAX_FALLBACK_DEPTH"), 5, minimum=1),
            routing_weights=(os.getenv("ROUTING_WEIGHTS") or "").strip(),
            ai_enable_discovery=os.getenv("AI_ENABLE_DISCOVERY", "true").lower() == "true",
            ai_discovery_query=os.getenv("AI_DISCOVERY_QUERY", "instruct"),
            ai_discovery_limit=parse_int_setting(os.getenv("AI_DISCOVERY_LIMIT"), 20),
            ai_max_parameters=parse_int_setting(os.getenv("AI_MAX_PARAMETERS"), 0) or None,
            use_ollama=os.getenv("USE_OLLAMA", "true").lower() == "true",
            ollama_base_url=(os.getenv("OLLAMA_BASE_URL", "http://localhost:11434") or "").strip()
            or "http://localhost:11434",
            ollama_model=(os.getenv("OLLAMA_MODEL", "llama3.2:3b") or "").strip() or "llama3.2:3b",
            ollama_timeout_seconds=parse_float_setting(os.getenv("OLLAMA_TIMEOUT_SECONDS"), 10.0, minimum=1.0),
            ollama_connect_timeout_seconds=parse_float_setting(
                os.getenv("OLLAMA_CONNECT_TIMEOUT_SECONDS"), 3.0, minimum=0.5
            ),
            ollama_keep_alive=(os.getenv("OLLAMA_KEEP_ALIVE", "5m") or "").strip() or "5m",
            ollama_temperature=parse_float_setting(os.getenv("OLLAMA_TEMPERATURE"), 0.3),
            ollama_num_ctx=parse_int_setting(os.getenv("OLLAMA_NUM_CTX"), 8192, minimum=512),
            ollama_auth_header=(os.getenv("OLLAMA_AUTH_HEADER") or "").strip() or None,
            ollama_auth_token=(os.getenv("OLLAMA_AUTH_TOKEN") or "").strip() or None,
        )


def validate_runtime_environment() -> None:
    missing: list[str] = []
    for key in REQUIRED_RUNTIME_ENV_KEYS:
        value = os.getenv(key)
        if value is None or not value.strip() or value.startswith("your_") or value.startswith("replace_with_"):
            missing.append(key)

    if missing:
        joined = ", ".join(missing)
        raise RuntimeError(
            "Missing or placeholder runtime configuration for: "
            f"{joined}. Copy .env.example to .env and replace the placeholder values before starting the app."
        )


def validate_supabase_storage() -> None:
    validate_runtime_environment()

    supabase_url = (os.getenv("SUPABASE_URL") or "").rstrip("/")
    service_role_key = os.getenv("SUPABASE_SERVICE_ROLE_KEY") or ""
    if not supabase_url or not service_role_key:
        raise RuntimeError("Supabase storage validation failed: missing SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY.")

    try:
        with httpx.Client(timeout=15.0) as client:
            response = client.get(
                f"{supabase_url}/rest/v1/profiles",
                headers={
                    "apikey": service_role_key,
                    "Authorization": f"Bearer {service_role_key}",
                    "Accept": "application/json",
                },
                params={"select": "user_id", "limit": "1"},
            )
    except httpx.HTTPError as exc:
        raise RuntimeError(f"Supabase storage validation failed: {exc}") from exc

    if response.status_code >= 400:
        raise RuntimeError(
            "Supabase storage validation failed: "
            f"HTTP {response.status_code} from {supabase_url}/rest/v1/profiles ({response.text[:200]})."
        )


settings = AppSettings.from_env()
