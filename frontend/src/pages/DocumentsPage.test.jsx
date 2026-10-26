import React from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

const { mockReport, sessionRef, templatesRef } = vi.hoisted(() => ({
  mockReport: vi.fn(),
  sessionRef: { current: { access_token: 'token' } },
  // The public (built-in) catalog. A test can drop an id to simulate a user template.
  templatesRef: {
    current: [
      { id: 'professional', name: 'Professional', document_type: 'cv', source: 'builtin' },
      { id: 'modern', name: 'Modern', document_type: 'cv', source: 'builtin' },
    ],
  },
}));

vi.mock('../lib/api', () => ({ apiRequest: vi.fn(), apiBlob: vi.fn(), getApiBase: () => '' }));
vi.mock('../hooks/useSession', () => ({
  useSession: () => ({ session: sessionRef.current, authLoading: false }),
}));
vi.mock('../hooks/useStatus.jsx', () => ({
  useStatus: () => ({ status: 'Ready', summary: '', report: mockReport }),
}));
vi.mock('../hooks/useTemplates', () => ({
  useTemplates: () => ({ templates: templatesRef.current, loading: false, error: null }),
}));
vi.mock('../hooks/useDesignOptions', () => ({
  toApiCountry: (c) => (c === 'other' ? 'XX' : c || ''),
  useDesignOptions: () => ({
    design: { themeId: '', country: '', sidebar: '' },
    setDesign: vi.fn(),
    themes: [],
    countryProfile: null,
    themesLoading: false,
    countryLoading: false,
    fetchCountryProfile: vi.fn(),
    isCv: true,
  }),
}));
vi.mock('../components/WorkspaceShell', () => ({ default: ({ children }) => <div>{children}</div> }));
// Drive the page's REAL handlers through lightweight stubs (avoids embla/supabase).
vi.mock('../features/documents/TemplateCarousel', () => ({
  default: ({ selectedId, onSelect }) => (
    <div>
      {['professional', 'modern'].map((id) => (
        <button key={id} type="button" onClick={() => onSelect(id)}>
          select-{id}
        </button>
      ))}
      <span data-testid="selected-id">{selectedId}</span>
    </div>
  ),
}));
vi.mock('../features/documents/DocumentStudio', () => ({
  default: ({ onGenerate, onPreview, onDownload, generating, canExport }) => (
    <div>
      <button type="button" disabled={generating} onClick={() => onGenerate()}>
        generate
      </button>
      {canExport && (
        <>
          <button type="button" onClick={() => onPreview()}>preview</button>
          <button type="button" onClick={() => onDownload('pdf')}>download-pdf</button>
        </>
      )}
    </div>
  ),
}));

import DocumentsPage from './DocumentsPage';
import { I18nProvider } from '../i18n/index.jsx';
import { apiRequest, apiBlob } from '../lib/api';

function renderPage() {
  render(
    <I18nProvider>
      <DocumentsPage />
    </I18nProvider>,
  );
}

// The generate request returns a promise we control so we can resolve/abort it
// mid-flight. `signal` is honoured so an abort rejects like the real fetch.
function mockGenerate({ mode }) {
  apiRequest.mockImplementation((path, opts = {}) => {
    if (!path.includes('/generate')) return Promise.resolve({});
    if (mode === 'pending') {
      return new Promise((resolve) => {
        mockGenerate.resolve = resolve;
      });
    }
    if (mode === 'abortable') {
      return new Promise((_, reject) => {
        opts.signal?.addEventListener('abort', () => {
          const err = new Error('aborted');
          err.name = 'AbortError';
          reject(err);
        });
      });
    }
    return Promise.resolve({ content: 'CV BODY', template_id: 'professional' });
  });
}

const CATALOG = [
  { id: 'professional', name: 'Professional', document_type: 'cv', source: 'builtin' },
  { id: 'modern', name: 'Modern', document_type: 'cv', source: 'builtin' },
];

beforeEach(() => {
  vi.clearAllMocks();
  window.localStorage.clear();
  sessionRef.current = { access_token: 'token' };
  templatesRef.current = CATALOG;
});

describe('DocumentsPage generate flow (sub-step 7)', () => {
  it('sends the call-time template_id in the generate payload', async () => {
    mockGenerate({ mode: 'immediate' });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'generate' }));
    await waitFor(() => expect(apiRequest).toHaveBeenCalled());
    const [path, opts] = apiRequest.mock.calls.find(([p]) => p.includes('/generate'));
    expect(path).toBe('/api/v1/documents/cv/generate');
    expect(opts.body.template_id).toBe('professional');
  });

  it('discards a stale response when the template changes mid-flight', async () => {
    mockGenerate({ mode: 'pending' });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'generate' }));
    await waitFor(() => expect(apiRequest).toHaveBeenCalled());

    // Switch template mid-flight (aborts + updates selectedIdRef synchronously).
    fireEvent.click(screen.getByRole('button', { name: 'select-modern' }));
    expect(screen.getByTestId('selected-id')).toHaveTextContent('modern');

    // The abort came too late: the OLD request resolves. Id comparison catches it.
    await act(async () => mockGenerate.resolve({ content: 'stale', template_id: 'professional' }));

    await waitFor(() =>
      expect(mockReport).toHaveBeenCalledWith('Ready', 'Template changed, regenerate.'),
    );
    const summaries = mockReport.mock.calls.map(([, s]) => s);
    expect(summaries).not.toContain('Document generated successfully.');
  });

  it('swallows AbortError silently (no error toast) and reports templateChanged', async () => {
    mockGenerate({ mode: 'abortable' });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'generate' }));
    await waitFor(() => expect(apiRequest).toHaveBeenCalled());

    // Changing selection aborts the in-flight request -> AbortError -> silent.
    fireEvent.click(screen.getByRole('button', { name: 'select-modern' }));

    await waitFor(() =>
      expect(mockReport).toHaveBeenCalledWith('Ready', 'Template changed, regenerate.'),
    );
    const statuses = mockReport.mock.calls.map(([s]) => s);
    expect(statuses).not.toContain('Generation failed');
  });

  it('renders via the stateless render endpoint (no persist, no document id)', async () => {
    mockGenerate({ mode: 'immediate' });
    apiBlob.mockResolvedValue(new Blob(['%PDF'], { type: 'application/pdf' }));
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:x');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    const clickSpy = vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'generate' }));

    // generate succeeds -> canExport -> the download button appears.
    const dl = await screen.findByRole('button', { name: 'download-pdf' });
    fireEvent.click(dl);

    await waitFor(() => expect(apiBlob).toHaveBeenCalled());
    // No persist step: we never POST /api/v1/documents to obtain a document id.
    expect(apiRequest).not.toHaveBeenCalledWith('/api/v1/documents', expect.anything());
    // The render call carries the content, call-time template and design options.
    const [path, opts] = apiBlob.mock.calls[0];
    expect(path).toBe('/api/v1/documents/render');
    expect(opts.method).toBe('POST');
    expect(opts.session).toEqual({ access_token: 'token' });
    expect(opts.body).toMatchObject({
      content: 'CV BODY',
      document_type: 'cv',
      template_id: 'professional',
      format: 'pdf',
      theme_id: '',
      country: '',
      sidebar: '',
    });
    expect(clickSpy).toHaveBeenCalled();
  });

  it('generates a built-in template while signed out (no sign-in gate)', async () => {
    sessionRef.current = null;
    mockGenerate({ mode: 'immediate' });
    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'generate' }));
    await waitFor(() =>
      expect(apiRequest).toHaveBeenCalledWith('/api/v1/documents/cv/generate', expect.anything()),
    );
    const statuses = mockReport.mock.calls.map(([s]) => s);
    expect(statuses).not.toContain('Sign in required');
  });

  it('lets a built-in template download while signed out', async () => {
    sessionRef.current = null;
    mockGenerate({ mode: 'immediate' });
    apiBlob.mockResolvedValue(new Blob(['%PDF'], { type: 'application/pdf' }));
    vi.spyOn(URL, 'createObjectURL').mockReturnValue('blob:x');
    vi.spyOn(URL, 'revokeObjectURL').mockImplementation(() => {});
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});

    renderPage();
    fireEvent.click(await screen.findByRole('button', { name: 'generate' }));

    const dl = await screen.findByRole('button', { name: 'download-pdf' });
    fireEvent.click(dl);

    await waitFor(() => expect(apiBlob).toHaveBeenCalled());
    const [, opts] = apiBlob.mock.calls[0];
    expect(opts.session).toBeNull();
    const statuses = mockReport.mock.calls.map(([s]) => s);
    expect(statuses).not.toContain('Sign in required');
  });

  it('requires sign-in to generate a user template while signed out', async () => {
    // 'modern' is the user's OWN template (source: 'user') -> it needs a token.
    templatesRef.current = [
      { id: 'professional', name: 'Professional', document_type: 'cv', source: 'builtin' },
      { id: 'modern', name: 'Modern', document_type: 'cv', source: 'user' },
    ];
    sessionRef.current = null;
    mockGenerate({ mode: 'immediate' });
    renderPage();

    fireEvent.click(await screen.findByRole('button', { name: 'select-modern' }));
    fireEvent.click(screen.getByRole('button', { name: 'generate' }));

    await waitFor(() =>
      expect(mockReport).toHaveBeenCalledWith(
        'Sign in required',
        'Sign in with Supabase to generate and save your documents.',
      ),
    );
    expect(apiRequest).not.toHaveBeenCalledWith('/api/v1/documents/cv/generate', expect.anything());
  });
});