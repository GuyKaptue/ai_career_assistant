# Documents Feature

## Purpose

Document creation: the studio form, the template
gallery, and the server-rendered template preview
(FE-02, FE-04 template preview).

## Modules

- `DocumentStudio` — presentational form for name,
  target role, company, and summary. The shell owns
  the form state and the generation action.
- `TemplateGallery` — template selection plus a
  preview modal that calls
  `POST /api/v1/templates/preview` (sample values
  only, no PII). Escape closes the dialog.

## Key Exports

- `DocumentStudio({ form, onFieldChange, onGenerate, generating })`
- `TemplateGallery({ templates, loading, selectedTemplate, onSelect, locale })`
- `PreviewModal` (internal)

## Testing

- `TemplateGallery.test.jsx` — list rendering,
  selection state, empty/loading states
