# Images

This directory holds the rendered artifacts referenced by the root `README.md`
and `docs/README.md`. It contains two families:

- **Architecture diagrams** (11 PNGs) — rendered from the Graphviz sources in
  `docs/diagrams/`. See the re-render instructions in `docs/README.md`.
- **UI screenshots** (5 PNGs) — captured manually from the running app; no
  automated screenshot target exists in the Makefile (`make screenshot` is not
  defined, and browser/E2E infra is not configured in this environment).

## Catalog

### Architecture diagrams

| Image | Source | Description |
|-------|--------|-------------|
| `ai_routing_architecture.png` | `docs/diagrams/ai_routing_architecture.dot` | AI routing subsystem: model catalog, routing profiles, fallback chain |
| `authentication_architecture.png` | `docs/diagrams/authentication_architecture.dot` | Authentication subsystem: JWT, OAuth, session handling |
| `backend_architecture.png` | `docs/diagrams/backend_architecture.dot` | Backend FastAPI service layout and modules |
| `data_flow_pipeline.png` | `docs/diagrams/data_flow_pipeline.dot` | End-to-end data flow pipeline |
| `database_architecture.png` | `docs/diagrams/database_architecture.dot` | Database schema and storage subsystem |
| `deployment_architecture.png` | `docs/diagrams/deployment_architecture.dot` | Deployment and infrastructure |
| `frontend_architecture.png` | `docs/diagrams/frontend_architecture.dot` | Frontend React application structure |
| `job_api_architecture.png` | `docs/diagrams/job_api_architecture.dot` | Job API integration subsystem |
| `module_architecture.png` | `docs/diagrams/module_architecture.dot` | Module-level architecture |
| `system_architecture.png` | `docs/diagrams/system_architecture.dot` | Complete system architecture overview |
| `testing_cicd_pipeline.png` | `docs/diagrams/testing_cicd_pipeline.dot` | Testing and CI/CD pipeline |

### UI screenshots

| Image | Description |
|-------|-------------|
| `combo-chat.png` | Chat experience combining the job-search and career-coach views |
| `combo-dark.png` | Dark theme variant of the combined view |
| `combo-mobile.png` | Mobile responsive layout of the combined view |
| `final-laptop.png` | Final desktop layout of the application |
| `in-laptop-chat.png` | In-app chat view on a laptop viewport |

## Regenerating

Diagrams:

```bash
for f in docs/diagrams/*.dot; do
  dot -Tpng -Gdpi=110 "$f" -o "docs/images/$(basename "${f%.dot}").png"
done
```

Screenshots must be captured manually from a running instance; no `make screenshot`
target or browser/E2E harness is configured in this environment.
