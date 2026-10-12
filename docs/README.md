# Project documentation

This documentation set explains the product requirement, the technical architecture, the template model, and the legal boundaries of the implementation. It is intended to show how the project works and how the components relate to each other without depending on hidden instructions or internal prompts.

The documentation is written as a working project guide rather than as a collection of implementation notes. It should remain human-readable and approachable for contributors and maintainers.

## Documentation areas

| Area | Contents |
|------|----------|
| `requirements/` | product requirements, traceability matrix, implementation roadmap |
| `architecture/` | architecture decisions and system design |
| `api/` | API documentation |
| `security/` | security model and controls |
| `privacy/` | data flow, AI transmission table, GDPR rights |
| `academic/` | system, mathematical, ATS, and evaluation methodology |
| `templates/` | template catalog, rendering architecture, third-party assets |
| `deployment/` | deployment and operations guides |
| `development/` | developer guides |
| `legal/` | licensing and legal notices |

## Architecture diagrams

Editable Graphviz sources live in `docs/diagrams/`; rendered PNGs live in
`docs/images/` and are embedded in the root `README.md`.

| Diagram | Source | Image |
|---------|--------|-------|
| Complete system architecture | `diagrams/system_architecture.dot` | `images/system_architecture.png` |
| Frontend architecture | `diagrams/frontend_architecture.dot` | `images/frontend_architecture.png` |
| Backend architecture | `diagrams/backend_architecture.dot` | `images/backend_architecture.png` |
| Module architecture | `diagrams/module_architecture.dot` | `images/module_architecture.png` |
| Data flow pipeline | `diagrams/data_flow_pipeline.dot` | `images/data_flow_pipeline.png` |
| Deployment & infrastructure | `diagrams/deployment_architecture.dot` | `images/deployment_architecture.png` |
| Testing & CI/CD pipeline | `diagrams/testing_cicd_pipeline.dot` | `images/testing_cicd_pipeline.png` |
| Authentication subsystem | `diagrams/authentication_architecture.dot` | `images/authentication_architecture.png` |
| Database subsystem | `diagrams/database_architecture.dot` | `images/database_architecture.png` |
| AI routing subsystem | `diagrams/ai_routing_architecture.dot` | `images/ai_routing_architecture.png` |
| Job API integration | `diagrams/job_api_architecture.dot` | `images/job_api_architecture.png` |

### Re-rendering the diagrams

The diagrams are authored in Graphviz DOT (installed via `brew install
graphviz` / `apt install graphviz`). Re-render every diagram after editing
a source:

```bash
for f in docs/diagrams/*.dot; do
  dot -Tpng -Gdpi=110 "$f" -o "docs/images/$(basename "${f%.dot}").png"
done
```

Mermaid or PlantUML sources can be added alongside the DOT files in the
future; the PNGs above are the rendered artifacts referenced by the
documentation.
