# Infrastructure — Document Export

## Purpose

Structured cover-letter DOCX rendering.
Refactored from a one-off German Bewerbung script
into a data-driven, locale-aware formal-letter
renderer (roughly DIN-5008 order).

## Responsibilities

- Render a cover letter to DOCX bytes
- Locale-aware salutation/closing (de/en/fr)
- Structured overrides with classic fallback

## Architecture

```
infrastructure/document_export/
├── __init__.py
└── cover_letter_docx.py
```

## Public API

- `render_cover_letter_to_docx(document: dict) -> bytes`
- `from_document(document: dict) -> CoverLetterData`

## Letter Order (DIN-5008-inspired)

sender block → rule → recipient → date → subject →
salutation → body → closing → signature

## Configuration

- Margins: 0.6" top/bottom, 0.8" left/right
- Font: Calibri 10.5pt
- Locales: de, en, fr

## Data Contracts

`CoverLetterData` (Pydantic):
sender_name, sender_street, sender_city, sender_phone,
sender_email, recipient_lines, company, target_role,
subject, reference_no, salutation, body_paragraphs,
closing, signature, letter_date, locale

## Dependencies

- `python-docx` (DOCX generation)

## Error Handling

- No PII defaults, no hardcoded employer, dynamic date

## Testing

- `tests/test_cover_letter_docx.py` — DOCX export

## Related Modules

- `app.domain.documents` — document model
- `app.api.routes.documents` — export endpoints
