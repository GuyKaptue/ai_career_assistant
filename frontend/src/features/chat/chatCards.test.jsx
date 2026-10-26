import React from 'react';
import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { I18nProvider } from '../../i18n';
import en from '../../i18n/locales/en';
import de from '../../i18n/locales/de';
import fr from '../../i18n/locales/fr';
import * as api from '../../lib/api';
import ClarifyCard from './ClarifyCard';
import DocumentPreview from './DocumentPreview';
import MatchCard from './MatchCard';
import { detectJobText, detectJobUrl, quickActions } from './inputHints';

function wrap(ui, locale = 'en') {
  window.localStorage.setItem('aca-locale', locale);
  return render(<I18nProvider>{ui}</I18nProvider>);
}

afterEach(() => {
  window.localStorage.removeItem('aca-locale');
  vi.restoreAllMocks();
});

const MATCH = {
  match: { score: 72, label: 'Good match', matched_skills: ['Python', 'SQL'], missing_skills: ['Kubernetes'], reasons: ['Strong backend overlap'] },
  job: { title: 'Backend Engineer', company: 'Acme', source_host: 'jobs.example.com', company_unverified: true, the_role_fallback: true },
  input: { used_session_job: true },
};

describe('MatchCard', () => {
  it('shows score, skills and reasons', () => {
    wrap(<MatchCard data={MATCH} />);
    expect(screen.getByText('Python')).toBeInTheDocument();
    expect(screen.getByText('Kubernetes')).toBeInTheDocument();
    expect(screen.getByText('Strong backend overlap')).toBeInTheDocument();
    expect(screen.getByLabelText('Match score: 72 out of 100')).toBeInTheDocument();
    expect(screen.getByText('Backend Engineer · Acme')).toBeInTheDocument();
  });

  it('renders every UI string in German', () => {
    wrap(<MatchCard data={MATCH} />, 'de');
    expect(screen.getByText(de.chat.matchedSkills)).toBeInTheDocument();
    expect(screen.getByText(de.chat.missingSkills)).toBeInTheDocument();
    expect(screen.getByText(de.chat.companyUnverified)).toBeInTheDocument();
    expect(screen.getByText(de.chat.roleFallback)).toBeInTheDocument();
    expect(screen.getByText(de.chat.usedSessionJob)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: de.chat.tailorCv })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: de.chat.writeCover })).toBeInTheDocument();
    expect(screen.getByLabelText('Übereinstimmung: 72 von 100')).toBeInTheDocument();
  });

  it('calls the right callback for each button', () => {
    const onTailor = vi.fn();
    const onCover = vi.fn();
    wrap(<MatchCard data={MATCH} onTailor={onTailor} onCover={onCover} />);
    fireEvent.click(screen.getByRole('button', { name: en.chat.tailorCv }));
    expect(onTailor).toHaveBeenCalledTimes(1);
    expect(onCover).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole('button', { name: en.chat.writeCover }));
    expect(onCover).toHaveBeenCalledTimes(1);
  });

  it('omits optional notes when the flags are absent', () => {
    wrap(<MatchCard data={{ match: { score: 10, label: 'Low' }, job: { title: 'X' } }} />);
    expect(screen.queryByText(en.chat.companyUnverified)).toBeNull();
    expect(screen.queryByText(en.chat.matchedSkills)).toBeNull();
  });
});

describe('DocumentPreview', () => {
  const DOC = { document: { type: 'cover_letter', content: 'Dear team', template_id: 'tpl_x' }, grounding: { removed: 2 }, gaps: ['Add a date'] };
  const session = { access_token: 'tok-123' };
  let createUrl;
  let revoke;

  beforeEach(() => {
    createUrl = vi.fn(() => 'blob:fake');
    revoke = vi.fn();
    URL.createObjectURL = createUrl;
    URL.revokeObjectURL = revoke;
    vi.spyOn(HTMLAnchorElement.prototype, 'click').mockImplementation(() => {});
  });

  it('sends the real session and the exact edited payload to the render endpoint', async () => {
    const spy = vi.spyOn(api, 'apiBlob').mockResolvedValue(new Blob(['x']));
    wrap(<DocumentPreview data={DOC.document && { ...DOC, document: DOC.document }} session={session} />);
    fireEvent.change(screen.getByLabelText(en.chat.editDraft), { target: { value: 'Dear team, edited' } });
    fireEvent.change(screen.getByLabelText(en.chat.downloadFormat), { target: { value: 'docx' } });
    fireEvent.click(screen.getByRole('button', { name: en.chat.download }));
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(1));
    expect(spy).toHaveBeenCalledWith('/api/v1/documents/render', {
      session,
      method: 'POST',
      body: { content: 'Dear team, edited', document_type: 'cover_letter', template_id: 'tpl_x', format: 'docx', title: en.chat.documentTitleCover },
    });
    await waitFor(() => expect(revoke).toHaveBeenCalledWith('blob:fake'));
  });

  it('omits template_id when none was returned', async () => {
    const spy = vi.spyOn(api, 'apiBlob').mockResolvedValue(new Blob(['x']));
    wrap(<DocumentPreview data={{ document: { type: 'cv', content: 'CV text', template_id: '' } }} session={session} />);
    fireEvent.click(screen.getByRole('button', { name: en.chat.download }));
    await waitFor(() => expect(spy).toHaveBeenCalled());
    const body = spy.mock.calls[0][1].body;
    expect('template_id' in body).toBe(false);
    expect(body.title).toBe(en.chat.documentTitleCv);
  });

  it('shows the removed-statement count and gaps, localised', () => {
    wrap(<DocumentPreview data={DOC} session={session} />, 'fr');
    expect(screen.getByText(fr.chat.removedStatements.replace('{count}', '2'))).toBeInTheDocument();
    expect(screen.getByText(fr.chat.gapsTitle)).toBeInTheDocument();
    expect(screen.getByText('Add a date')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: fr.chat.download })).toBeInTheDocument();
  });

  it('shows a localised error and re-enables the button when render fails', async () => {
    vi.spyOn(api, 'apiBlob').mockRejectedValue(new Error('boom internal detail'));
    wrap(<DocumentPreview data={DOC} session={session} />, 'de');
    fireEvent.click(screen.getByRole('button', { name: de.chat.download }));
    expect(await screen.findByRole('alert')).toHaveTextContent(de.chat.renderFailed);
    expect(screen.getByRole('alert')).not.toHaveTextContent('boom');
    expect(screen.getByRole('button', { name: de.chat.download })).not.toBeDisabled();
    expect(createUrl).not.toHaveBeenCalled();
  });

  it('disables the button while rendering', async () => {
    let resolve;
    vi.spyOn(api, 'apiBlob').mockReturnValue(new Promise((r) => { resolve = r; }));
    wrap(<DocumentPreview data={DOC} session={session} />);
    fireEvent.click(screen.getByRole('button', { name: en.chat.download }));
    const busy = await screen.findByRole('button', { name: en.chat.downloading });
    expect(busy).toBeDisabled();
    resolve(new Blob(['x']));
    await waitFor(() => expect(screen.getByRole('button', { name: en.chat.download })).not.toBeDisabled());
  });
});

describe('ClarifyCard', () => {
  const STATUS_KEYS = {
    login_wall: 'loginWall', not_a_job_posting: 'notAJob', fetch_failed: 'fetchFailed', invalid_url: 'invalidUrl',
    too_large: 'tooLarge', unsupported_type: 'unsupportedType', needs_text: 'needsText', blocked: 'blocked', timeout: 'timeout',
  };

  it.each(Object.entries(STATUS_KEYS))('shows a distinct message for %s', (status, key) => {
    wrap(<ClarifyCard data={{ missing: ['job'], job_ingest_status: status }} />);
    expect(screen.getByText(en.chat.ingest[key])).toBeInTheDocument();
  });

  it('all status messages are different from each other', () => {
    const values = Object.values(STATUS_KEYS).map((k) => en.chat.ingest[k]);
    expect(new Set(values).size).toBe(values.length);
  });

  it('shows the CV upload prompt and calls onUploadCv', () => {
    const onUploadCv = vi.fn();
    wrap(<ClarifyCard data={{ missing: ['cv'] }} onUploadCv={onUploadCv} />, 'fr');
    expect(screen.getByText(fr.chat.needCv)).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: fr.chat.uploadCv }));
    expect(onUploadCv).toHaveBeenCalledTimes(1);
  });

  it('submits pasted text in preference to the link', () => {
    const onSubmitJob = vi.fn();
    wrap(<ClarifyCard data={{ missing: ['job'] }} onSubmitJob={onSubmitJob} />);
    fireEvent.change(screen.getByPlaceholderText(en.chat.jobTextPlaceholder), { target: { value: 'We are hiring' } });
    fireEvent.change(screen.getByPlaceholderText(en.chat.jobUrlPlaceholder), { target: { value: 'https://x.test/j' } });
    fireEvent.click(screen.getByRole('button', { name: en.chat.submitJob }));
    expect(onSubmitJob).toHaveBeenCalledTimes(1);
    expect(onSubmitJob).toHaveBeenCalledWith({ job_text: 'We are hiring' });
  });

  it('submits the link when no text was pasted and ignores empty submits', () => {
    const onSubmitJob = vi.fn();
    wrap(<ClarifyCard data={{ missing: ['job'] }} onSubmitJob={onSubmitJob} />);
    fireEvent.click(screen.getByRole('button', { name: en.chat.submitJob }));
    expect(onSubmitJob).not.toHaveBeenCalled();
    fireEvent.change(screen.getByPlaceholderText(en.chat.jobUrlPlaceholder), { target: { value: 'https://x.test/j' } });
    fireEvent.click(screen.getByRole('button', { name: en.chat.submitJob }));
    expect(onSubmitJob).toHaveBeenCalledWith({ job_url: 'https://x.test/j' });
  });

  it('shows no status message for ok or session', () => {
    wrap(<ClarifyCard data={{ missing: ['job'], job_ingest_status: 'ok' }} />);
    for (const v of Object.values(en.chat.ingest)) expect(screen.queryByText(v)).toBeNull();
  });
});

describe('inputHints', () => {
  const LONG = `We are hiring a Backend Engineer.\nRequirements: Python, SQL, five years.\nResponsibilities: build APIs.\n${'x'.repeat(200)}`;
  it('detects links and long postings only', () => {
    expect(detectJobUrl('see https://jobs.example.com/1')).toBe(true);
    expect(detectJobUrl('no link here')).toBe(false);
    expect(detectJobText(LONG)).toBe(true);
    expect(detectJobText('short')).toBe(false);
    expect(detectJobText('a\nb\nc\n' + 'x'.repeat(250))).toBe(false);
  });

  it('quick actions carry label and prefill keys that exist in every locale', () => {
    const actions = quickActions();
    expect(actions.map((a) => a.key)).toEqual(['match', 'tailor', 'cover', 'find']);
    for (const a of actions) {
      for (const loc of [en, de, fr]) {
        expect(typeof loc.chat[a.labelKey.replace('chat.', '')]).toBe('string');
        expect(typeof loc.chat[a.prefillKey.replace('chat.', '')]).toBe('string');
      }
    }
  });
});

describe('chat locale parity', () => {
  const flat = (o, p = '') => Object.entries(o).flatMap(([k, v]) => (typeof v === 'object' && v ? flat(v, `${p}${k}.`) : [`${p}${k}`])).sort();
  it('en, de and fr have identical chat key sets', () => {
    expect(flat(de.chat)).toEqual(flat(en.chat));
    expect(flat(fr.chat)).toEqual(flat(en.chat));
  });
  it('new job-flow strings are translated, not copied from English', () => {
    for (const k of ['matchedSkills', 'download', 'needCv', 'jobLinkDetected', 'quickMatch', 'removedStatements']) {
      expect(de.chat[k]).not.toBe(en.chat[k]);
      expect(fr.chat[k]).not.toBe(en.chat[k]);
    }
    for (const k of Object.keys(en.chat.ingest)) {
      expect(de.chat.ingest[k]).not.toBe(en.chat.ingest[k]);
      expect(fr.chat.ingest[k]).not.toBe(en.chat.ingest[k]);
    }
  });
});
