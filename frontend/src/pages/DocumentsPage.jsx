import React, { useState } from 'react';

import { useSession } from '../hooks/useSession';
import { useI18n } from '../i18n';
import { useStatus } from '../hooks/useStatus.jsx';
import { apiRequest } from '../lib/api';
import { useTemplates } from '../hooks/useTemplates';
import WorkspaceShell from '../components/WorkspaceShell';
import DocumentStudio from '../features/documents/DocumentStudio';
import TemplateGallery from '../features/documents/TemplateGallery';

const EMPTY_FORM = {
  full_name: '',
  target_role: '',
  company: '',
  summary: '',
  job_description: '',
  skills: '',
  document_type: 'cv',
};

// The backend exposes one generation route per document type (see
// app/main.py and api/routes/README.md). The studio must call the matching
// route — there is intentionally no generic `/documents/generate` endpoint.
const GENERATE_ENDPOINTS = {
  cv: '/api/v1/documents/cv/generate',
  cover_letter: '/api/v1/documents/cover-letter/generate',
  resignation: '/api/v1/documents/resignation/generate',
};

/** Split a comma-separated skills string into the list the backend expects. */
function splitSkills(value) {
  return String(value || '')
    .split(',')
    .map((item) => item.trim())
    .filter(Boolean);
}

/**
 * Map the studio form onto the backend's loosely-typed generation payload.
 * Field names differ from the form (`full_name` -> `name`), skills arrive as a
 * comma-separated string, and the free-text box is `summary`. Unknown keys are
 * allowed by the backend payload model, so mapping explicitly keeps the request
 * clean while staying forward-compatible.
 */
function buildGenerateBody(form, selectedTemplate) {
  const body = {
    name: form.full_name,
    target_role: form.target_role,
    company: form.company,
    summary: form.summary || form.job_description || '',
  };
  if (selectedTemplate) {
    body.template_id = selectedTemplate;
  }
  const skills = splitSkills(form.skills);
  if (skills.length) {
    body.skills = skills;
  }
  if (form.document_type === 'resignation') {
    // The resignation generator reads `role` rather than `target_role`.
    body.role = form.target_role;
  }
  return body;
}

/**
 * Document generation page: template gallery + the studio form. The parent
 * owns form state so the template picker and the generate action stay in sync.
 */
export default function DocumentsPage() {
  const { session } = useSession();
  const { t, locale } = useI18n();
  const { report } = useStatus();
  const { templates, loading: templatesLoading, error: templatesError } = useTemplates();

  const [form, setForm] = useState(EMPTY_FORM);
  const [selectedTemplate, setSelectedTemplate] = useState(null);
  const [generating, setGenerating] = useState(false);

  function handleFieldChange(event) {
    const { name, value } = event.target;
    setForm((current) => ({ ...current, [name]: value }));
  }

  async function handleGenerate() {
    if (!session) {
      report(t('status.signInRequired'), t('summary.signInToGenerate'));
      return;
    }
    const endpoint = GENERATE_ENDPOINTS[form.document_type] || GENERATE_ENDPOINTS.cv;
    setGenerating(true);
    try {
      await apiRequest(endpoint, {
        method: 'POST',
        session,
        body: buildGenerateBody(form, selectedTemplate),
      });
      report(t('status.ready'), t('summary.documentGenerated'));
    } catch (error) {
      report(t('status.generationFailed'), error?.message || t('summary.unableToGenerate'));
    } finally {
      setGenerating(false);
    }
  }

  return (
    <WorkspaceShell titleKey="nav.documents">
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <TemplateGallery
          templates={templates}
          loading={templatesLoading}
          selectedTemplate={selectedTemplate}
          onSelect={setSelectedTemplate}
          locale={locale}
        />

        <DocumentStudio
          form={form}
          onFieldChange={handleFieldChange}
          onGenerate={handleGenerate}
          generating={generating}
        />

        {templatesError && (
          <p className="text-sm text-destructive" role="alert">
            {t('summary.templatesUnavailable')}
          </p>
        )}
      </div>
    </WorkspaceShell>
  );
}
