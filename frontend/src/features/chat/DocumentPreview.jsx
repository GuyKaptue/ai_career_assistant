import React, { useState } from 'react';
import { useI18n } from '../../i18n';
import { apiBlob } from '../../lib/api';

const FORMATS = [
  { value: 'pdf', label: 'PDF' },
  { value: 'docx', label: 'DOCX' },
  { value: 'html', label: 'HTML' },
];

export default function DocumentPreview({ data, session }) {
  const { t } = useI18n();
  const doc = data?.document || {};
  const isCover = doc.type === 'cover_letter';
  const [content, setContent] = useState(doc.content || '');
  const [format, setFormat] = useState('pdf');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const removed = data?.grounding?.removed || 0;
  const gaps = Array.isArray(data?.gaps) ? data.gaps : [];

  async function handleDownload() {
    setLoading(true);
    setError(null);
    try {
      const body = {
        content,
        document_type: isCover ? 'cover_letter' : 'cv',
        format,
        title: isCover ? t('chat.documentTitleCover') : t('chat.documentTitleCv'),
      };
      if (doc.template_id) body.template_id = doc.template_id;
      const blob = await apiBlob('/api/v1/documents/render', { session, method: 'POST', body });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${isCover ? 'cover-letter' : 'cv'}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      setError(t('chat.renderFailed'));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-2xl border border-border bg-card p-4">
      {removed > 0 && (
        <p className="text-xs text-muted-foreground">{t('chat.removedStatements', { count: removed })}</p>
      )}
      {gaps.length > 0 && (
        <div className="mt-2">
          <p className="text-xs font-medium">{t('chat.gapsTitle')}</p>
          <ul className="list-disc pl-5 text-xs">{gaps.map((g, i) => <li key={i}>{g}</li>)}</ul>
        </div>
      )}
      <textarea
        aria-label={t('chat.editDraft')}
        className="mt-3 w-full rounded border p-2 text-sm"
        rows={10}
        value={content}
        onChange={(e) => setContent(e.target.value)}
      />
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <select aria-label={t('chat.downloadFormat')} value={format} onChange={(e) => setFormat(e.target.value)} className="rounded border px-2 py-1 text-xs">
          {FORMATS.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
        </select>
        <button type="button" onClick={handleDownload} disabled={loading} className="rounded bg-primary px-3 py-1.5 text-xs text-primary-foreground disabled:opacity-60">
          {loading ? t('chat.downloading') : t('chat.download')}
        </button>
      </div>
      {error && <p className="mt-2 text-xs text-destructive" role="alert">{error}</p>}
    </div>
  );
}
