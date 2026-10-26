import React, { useState, useMemo, useRef, useEffect } from 'react';

import { useSession } from '../hooks/useSession';
import { useI18n } from '../i18n';
import { useStatus } from '../hooks/useStatus.jsx';
import { apiRequest, apiBlob } from '../lib/api';
import { useTemplates } from '../hooks/useTemplates';
import { useTemplateSelection } from '../hooks/useTemplateSelection';
import { useDesignOptions, toApiCountry } from '../hooks/useDesignOptions';
import WorkspaceShell from '../components/WorkspaceShell';
import DocumentStudio from '../features/documents/DocumentStudio';
import TemplateCarousel from '../features/documents/TemplateCarousel';

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

/** Default template id per document type. */
const DEFAULT_TEMPLATE_ID = {
  cv: 'professional',
  cover_letter: 'classic-letter',
  resignation: 'formal-resignation',
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
 * Document generation page: template carousel + the studio form. The parent
 * owns form state so the template picker and the generate action stay in sync.
 * Template selection and design options are persisted per document type in
 * localStorage via dedicated hooks.
 */
export default function DocumentsPage() {
  const { session } = useSession();
  const { t, locale } = useI18n();
  const { report } = useStatus();
  const { templates, loading: templatesLoading, error: templatesError } = useTemplates();

  const [form, setForm] = useState(EMPTY_FORM);
  const [generating, setGenerating] = useState(false);

  // Sub-step 5 (second half): the last generated document (so Preview/Download
  // can render it). Rendering is stateless — no saved document id is kept.
  const [generatedDoc, setGeneratedDoc] = useState(null);
  const [exporting, setExporting] = useState(false);

  // Templates for the current document type (used for validation + chip label).
  const typeTemplates = useMemo(
    () => templates.filter((t) => t.document_type === form.document_type),
    [templates, form.document_type]
  );

  // The catalog tags each template with a `source` ("builtin" | "user"). Built-in
  // templates generate/render without a token; only the user's own template needs
  // the session (backend resolves it via get_optional_user).
  const isUserTemplate = (templateId) =>
    templates.some((tpl) => tpl.id === templateId && tpl.source === 'user');

  const defaultId = DEFAULT_TEMPLATE_ID[form.document_type] || 'professional';
  const { selectedId, setSelectedId, isValidated } = useTemplateSelection(
    form.document_type,
    typeTemplates,
    locale
  );

  // Sub-step 5: generate calls must read the selection at call time through a
  // ref, never from a stale closure. The ref is also written synchronously in
  // handleTemplateSelect so an in-flight request is aborted the instant the
  // user picks a new template (sub-step 6).
  const selectedIdRef = useRef(selectedId);
  useEffect(() => {
    selectedIdRef.current = selectedId;
  }, [selectedId]);

  // Sub-step 6: the in-flight generation's AbortController (if any). Aborting in
  // this effect's cleanup covers BOTH an unmount and a switch to a different
  // document type — a CV request must not survive a switch to a cover letter.
  const generateAbortRef = useRef(null);
  useEffect(() => {
    return () => {
      generateAbortRef.current?.abort();
      generateAbortRef.current = null;
    };
  }, [form.document_type]);

  // Design options are only meaningful for CVs.
  const {
    design,
    setDesign,
    themes,
    countryProfile,
    themesLoading,
    countryLoading,
    fetchCountryProfile,
    isCv,
  } = useDesignOptions(form.document_type);

  function handleFieldChange(event) {
    const { name, value } = event.target;
    setForm((current) => ({ ...current, [name]: value }));
  }

  async function handleGenerate() {
    // Built-in templates generate without a token; only the user's own template
    // needs the session (backend generate uses get_optional_user).
    if (isUserTemplate(selectedIdRef.current) && !session) {
      report(t('status.signInRequired'), t('summary.signInToGenerate'));
      return;
    }
    const endpoint =
      GENERATE_ENDPOINTS[form.document_type] || GENERATE_ENDPOINTS.cv;

    // Sub-step 6: capture the selection at request START and make the request
    // abortable, so a mid-flight template change can cancel it.
    const templateIdAtStart = selectedIdRef.current;
    const controller = new AbortController();
    generateAbortRef.current = controller;

    setGenerating(true);
    try {
      const result = await apiRequest(endpoint, {
        method: 'POST',
        session,
        body: buildGenerateBody(form, templateIdAtStart),
        signal: controller.signal,
      });
      // Compare ids again on completion — the abort may have come too late to
      // cancel, and we must never present old output as the new template. This
      // comparison is id-based and does NOT rely on the abort flag, so a late
      // abort that failed to cancel is still caught here.
      if (selectedIdRef.current !== templateIdAtStart) {
        report(t('status.ready'), t('templates.carousel.templateChanged'));
      } else {
        // Keep the freshly generated content so Preview/Download can export it.
        setGeneratedDoc({
          content: result?.content ?? '',
          // Keep the CALL-TIME selection (not the resolved built-in id) so a
          // user template still requires its owner's token when rendered.
          templateId: templateIdAtStart,
          documentType: form.document_type,
        });
        report(t('status.ready'), t('summary.documentGenerated'));
      }
    } catch (error) {
      // AbortError is silent (no error toast); just surface "Template changed".
      if (controller.signal.aborted) {
        report(t('status.ready'), t('templates.carousel.templateChanged'));
      } else {
        report(
          t('status.generationFailed'),
          error?.message || t('summary.unableToGenerate')
        );
      }
    } finally {
      setGenerating(false);
      if (generateAbortRef.current === controller) {
        generateAbortRef.current = null;
      }
    }
  }

  // --- Sub-step 5 (second half): preview + download via the render route -----
  // POST /documents/render is STATELESS: it takes the generated content plus the
  // call-time template and design options, returns the file, and stores nothing.
  // Built-in templates work without a token; a user template needs the session
  // (the backend 400s without it), so only user templates are gated here.
  const docTitle = `${form.document_type} — ${form.full_name || t('documents.untitled')}`;

  function renderBody(format) {
    return {
      content: generatedDoc.content,
      document_type: generatedDoc.documentType,
      template_id: generatedDoc.templateId,
      title: docTitle,
      format,
      theme_id: design.themeId,
      country: toApiCountry(design.country),
      sidebar: design.sidebar,
    };
  }

  function saveBlob(blob, filename) {
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement('a');
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    anchor.remove();
    URL.revokeObjectURL(url);
  }

  async function handlePreview() {
    if (!generatedDoc) return;
    // Only the user's own template needs a token; built-in previews work signed-out.
    if (isUserTemplate(generatedDoc.templateId) && !session) {
      report(t('status.signInRequired'), t('summary.signInToDownload'));
      return;
    }
    setExporting(true);
    try {
      const blob = await apiBlob('/api/v1/documents/render', {
        session,
        method: 'POST',
        body: renderBody('html'),
      });
      window.open(URL.createObjectURL(blob), '_blank');
      report(t('status.ready'), t('summary.documentExported'));
    } catch (error) {
      report(t('status.exportFailed'), error?.message || t('summary.unableToExport'));
    } finally {
      setExporting(false);
    }
  }

  async function handleDownload(format) {
    if (!generatedDoc) return;
    // Only the user's own template needs a token; built-in downloads work signed-out.
    if (isUserTemplate(generatedDoc.templateId) && !session) {
      report(t('status.signInRequired'), t('summary.signInToDownload'));
      return;
    }
    setExporting(true);
    try {
      const blob = await apiBlob('/api/v1/documents/render', {
        session,
        method: 'POST',
        body: renderBody(format),
      });
      saveBlob(blob, `${form.document_type}.${format === 'docx' ? 'docx' : 'pdf'}`);
      report(t('status.ready'), t('summary.documentExported'));
    } catch (error) {
      report(t('status.exportFailed'), error?.message || t('summary.unableToExport'));
    } finally {
      setExporting(false);
    }
  }

  const selectedTemplate = typeTemplates.find((t) => t.id === selectedId);

  // Picking a template (or a country) resets the sidebar to that template's
  // default side — spec line 41 "Default = the template's sidebar".
  const handleTemplateSelect = (templateId) => {
    // Write the ref SYNCHRONOUSLY so an in-flight generate aborts immediately
    // (the useEffect below only mirrors it after re-render).
    selectedIdRef.current = templateId;
    // Sub-step 6: a template change aborts any in-flight generation.
    if (generateAbortRef.current) {
      generateAbortRef.current.abort();
      generateAbortRef.current = null;
    }
    setSelectedId(templateId);
    const template = typeTemplates.find((t) => t.id === templateId);
    setDesign((current) => ({ ...current, sidebar: template?.sidebar || '' }));
  };

  const handleCountryChange = async (country) => {
    setDesign((current) => ({
      ...current,
      country,
      sidebar: selectedTemplate?.sidebar || '',
    }));
    if (country) {
      await fetchCountryProfile(country, locale);
    }
  };

  const handleSidebarChange = (sidebar) => {
    setDesign((current) => ({ ...current, sidebar }));
  };

  const handleThemeChange = (themeId) => {
    setDesign((current) => ({ ...current, themeId }));
  };

  return (
    <WorkspaceShell titleKey="nav.documents">
      <div className="grid gap-6 xl:grid-cols-[minmax(0,1fr)_minmax(0,1.1fr)]">
        <TemplateCarousel
          documentType={form.document_type}
          locale={locale}
          selectedId={selectedId}
          onSelect={handleTemplateSelect}
          design={design}
        />

        <DocumentStudio
          form={form}
          onFieldChange={handleFieldChange}
          onGenerate={handleGenerate}
          generating={generating}
          selectedTemplate={selectedTemplate}
          design={design}
          isCv={isCv}
          themes={themes}
          themesLoading={themesLoading}
          countryProfile={countryProfile}
          countryLoading={countryLoading}
          onDesignChange={{
            theme: handleThemeChange,
            country: handleCountryChange,
            sidebar: handleSidebarChange,
          }}
          onPreview={handlePreview}
          onDownload={handleDownload}
          canExport={Boolean(generatedDoc)}
          exporting={exporting}
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
