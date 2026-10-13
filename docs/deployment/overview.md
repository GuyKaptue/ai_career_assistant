# Deployment overview

The project is designed for straightforward deployment in a container-based environment. The root Docker Compose file brings up the backend and frontend services together, while the individual Dockerfiles allow each part of the stack to be built independently.

For local development, a simple environment file and a single Compose command are enough to start the system. For a production deployment, the same structure can be adapted to a managed VM, a VPS, or a hosted platform that supports Docker containers.

The deployment model remains intentionally simple: the app should be easy to run and easy to understand, with configuration held outside the repository and explicit service dependencies declared in the environment.

## Services

| Service | Image / build | Purpose | Depends on |
|---------|---------------|---------|------------|
| `backend` | `docker/Dockerfile.backend` | FastAPI REST API on `:8000` | `ollama` (soft: `service_started`, `required: false`) |
| `frontend` | `docker/Dockerfile.frontend` | Vite build, static assets on `:5173` | `backend` (healthy) |
| `ollama` | `ollama/ollama:${OLLAMA_IMAGE_TAG:-0.40.3}` | Local model inference, model weights in the `ollama_data` volume, bound to `127.0.0.1:11434` only | — |
| `ollama-pull` | same image as `ollama` | One-shot `ollama pull "${OLLAMA_MODEL}"` at deploy time; `restart: "no"` so its exit code stays visible | `ollama` (healthy) |

The backend starts even when Ollama is slow, still downloading a model, or
absent — the inference chain falls back to Hugging Face and then to the
deterministic template, and `/api/ready` reports the local channel without
letting it change the readiness verdict. See
[`ollama.md`](ollama.md) for setup, GPU, security and troubleshooting.
