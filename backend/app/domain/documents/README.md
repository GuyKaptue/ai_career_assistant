# Domain — Documents

## Purpose

Document persistence, versioning, and export for CVs, cover
letters, and resignation letters.

## Responsibilities

- Document CRUD scoped to the authenticated user
- Version history with bounded snapshots
- Export to HTML, PDF (ReportLab), and DOCX (python-docx)
- Template selection via `TemplateRegistry`

## Architecture

```
domain/documents/
├── __init__.py
├── models.py     # DocumentRecord, version history
└── schemas.py    # Pydantic request/result contracts
```

## Public API

- `CVGenerationRequest` / `CVGenerationResult`
- `CoverLetterGenerationRequest` / `CoverLetterGenerationResult`
- `ResumeAnalysisRequest` / `ResumeAnalysisResult`

## Data Contracts

`documents` table (Supabase):
`id, user_id, document_type, title, content, template_id,
version, version_history, created_at, updated_at`

## Dependencies

- `reportlab` (PDF)
- `python-docx` (DOCX)
- `app.domain.templates` (template registry)

## Security

- RLS enforces `auth.uid() = user_id`
- Export never includes other users' documents

## Error Handling

- `ValidationError` — invalid document type or template
- `ExportError` — export failure

## Testing

- `tests/test_document_management.py` — persistence + versioning
- `tests/test_cover_letter_docx.py` — DOCX export

## Related Modules

- `app.application.services.document_generation` — rendering
- `app.application.services.document_store` — persistence
