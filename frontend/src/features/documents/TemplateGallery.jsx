import React, { useState } from 'react';

import { apiRequest } from '../../lib/api';
import { useI18n } from '../../i18n';
import { useAsync } from '../../hooks/useAsync';
import { ErrorState, LoadingState } from '../../components/AsyncStates';
import { Button } from '../../components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../components/ui/card';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '../../components/ui/dialog';

/**
 * Dialog showing a server-rendered sample for the selected template
 * (POST /api/v1/templates/preview). Sample values only — no PII is sent.
 * Same card as every dialog: header (title + X), scrolling content, footer.
 * Escape, overlay click and the X all close it (handled by the Dialog).
 */
function PreviewModal({ preview, onClose, t }) {
  return (
    <Dialog open={!!preview} onOpenChange={(open) => !open && onClose()} size="xl">
      <DialogHeader>
        <DialogTitle>
          {t('templates.previewTitle')} — {preview.name}
        </DialogTitle>
        <DialogDescription>{t('templates.previewSample')}</DialogDescription>
      </DialogHeader>
      <DialogContent>
        <pre
          className="overflow-x-auto whitespace-pre-wrap break-words rounded-xl bg-muted p-4 text-sm leading-relaxed"
        >
          {preview.content}
        </pre>
      </DialogContent>
      <DialogFooter>
        <Button variant="outline" onClick={onClose} data-autofocus="true">
          {t('templates.previewClose')}
        </Button>
      </DialogFooter>
    </Dialog>
  );
}

/**
 * Template gallery with per-template preview. Selection is owned by
 * the parent (the generation action needs the selected template id).
 */
export default function TemplateGallery({ templates, loading, selectedTemplate, onSelect, locale }) {
  const { t } = useI18n();
  const [previewTemplate, setPreviewTemplate] = useState(null);
  const preview = useAsync();

  async function loadPreview(template) {
    setPreviewTemplate(template);
    await preview.run(() =>
      apiRequest('/api/v1/templates/preview', {
        method: 'POST',
        body: {
          template_id: template.id,
          document_type: template.document_type || 'cv',
          locale,
        },
      }),
    );
  }

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle>{t('templates.galleryTitle')}</CardTitle>
        <CardDescription>{t('templates.galleryDescription')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-3">
          {templates.length > 0 ? (
            templates.map((template) => (
              <div
                key={template.id}
                className={`flex flex-col gap-2 rounded-xl border p-4 transition-colors sm:flex-row sm:items-center ${
                  selectedTemplate === template.id
                    ? 'border-primary bg-primary/5'
                    : 'border-border bg-card hover:bg-accent/50'
                }`}
              >
                <div className="flex-1">
                  <Button
                    type="button"
                    variant="ghost"
                    size="sm"
                    onClick={() => onSelect(template.id)}
                    aria-pressed={selectedTemplate === template.id}
                    aria-label={`Select template: ${template.name}`}
                    className="w-full justify-start h-auto p-0"
                  >
                    <div className="text-left">
                      <strong className="block font-medium">{template.name}</strong>
                      <span className="text-xs text-muted-foreground">
                        {template.document_type || t('templates.documentType')}
                      </span>
                    </div>
                  </Button>
                </div>
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => loadPreview(template)}
                  aria-label={`${t('templates.preview')}: ${template.name}`}
                  className="shrink-0"
                >
                  {t('templates.preview')}
                </Button>
              </div>
            ))
          ) : (
            <p className="text-center text-sm text-muted-foreground py-4">
              {t('templates.empty')}
            </p>
          )}
        </div>
        {loading && <LoadingState label={t('templates.loading')} />}
        {preview.phase === 'error' && (
          <ErrorState
            message={preview.error?.message || t('templates.previewError')}
            onRetry={preview.retry}
            retryLabel={t('templates.previewRetry')}
          />
        )}
        {preview.phase === 'success' && previewTemplate && (
          <PreviewModal
            preview={preview.data}
            onClose={() => {
              setPreviewTemplate(null);
              preview.reset();
            }}
            t={t}
          />
        )}
      </CardContent>
    </Card>
  );
}
