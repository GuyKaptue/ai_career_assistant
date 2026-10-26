import { renderHook, act } from '@testing-library/react';
import { beforeEach, describe, expect, it } from 'vitest';

import { useTemplateSelection } from './useTemplateSelection';

const CV_TEMPLATES = [
  { id: 'professional', document_type: 'cv' },
  { id: 'sidebar-left-navy', document_type: 'cv' },
];

const CL_TEMPLATES = [
  { id: 'classic-letter', document_type: 'cover_letter' },
];

beforeEach(() => {
  window.localStorage.clear();
});

describe('useTemplateSelection', () => {
  it('defaults to professional for CVs when nothing is stored', () => {
    const { result } = renderHook(() => useTemplateSelection('cv', CV_TEMPLATES, 'en'));
    expect(result.current.selectedId).toBe('professional');
    expect(result.current.isValidated).toBe(true);
  });

  it('defaults to classic-letter for cover letters when nothing is stored', () => {
    const { result } = renderHook(() =>
      useTemplateSelection('cover_letter', CL_TEMPLATES, 'en')
    );
    expect(result.current.selectedId).toBe('classic-letter');
  });

  it('keeps a valid stored selection and persists new choices', () => {
    window.localStorage.setItem('studio.template.cv', 'sidebar-left-navy');
    const { result } = renderHook(() => useTemplateSelection('cv', CV_TEMPLATES, 'en'));
    expect(result.current.selectedId).toBe('sidebar-left-navy');

    act(() => result.current.setSelectedId('professional'));
    expect(result.current.selectedId).toBe('professional');
    expect(window.localStorage.getItem('studio.template.cv')).toBe('professional');
  });

  it('falls back to the default when the stored id is not in the fetched list', () => {
    window.localStorage.setItem('studio.template.cv', 'ghost-template');
    const { result } = renderHook(() => useTemplateSelection('cv', CV_TEMPLATES, 'en'));
    expect(result.current.selectedId).toBe('professional');
    expect(result.current.isValidated).toBe(true);
  });

  it('revalidates when the template list changes (e.g. failed fetch / empty list)', () => {
    window.localStorage.setItem('studio.template.cv', 'sidebar-left-navy');
    const { result, rerender } = renderHook(
      ({ templates }) => useTemplateSelection('cv', templates, 'en'),
      { initialProps: { templates: CV_TEMPLATES } }
    );
    expect(result.current.selectedId).toBe('sidebar-left-navy');

    // Fetch fails / list becomes empty -> fall back to default.
    rerender({ templates: [] });
    expect(result.current.selectedId).toBe('professional');

    // List returns with the id present again -> still default (no ghost re-select).
    rerender({ templates: CV_TEMPLATES });
    expect(result.current.selectedId).toBe('professional');
  });

  it('revalidates on locale change when the stored id is invalid', () => {
    window.localStorage.setItem('studio.template.cv', 'ghost-template');
    const { result, rerender } = renderHook(
      ({ locale }) => useTemplateSelection('cv', CV_TEMPLATES, locale),
      { initialProps: { locale: 'en' } }
    );
    expect(result.current.selectedId).toBe('professional');

    rerender({ locale: 'de' });
    expect(result.current.selectedId).toBe('professional');
    expect(window.localStorage.getItem('studio.template.cv')).toBe('professional');
  });

  it('persists selections per document type (independent storage keys)', () => {
    const { result: cv } = renderHook(() => useTemplateSelection('cv', CV_TEMPLATES, 'en'));
    const { result: cl } = renderHook(() =>
      useTemplateSelection('cover_letter', CL_TEMPLATES, 'en')
    );

    act(() => cv.current.setSelectedId('sidebar-left-navy'));
    act(() => cl.current.setSelectedId('classic-letter'));

    expect(window.localStorage.getItem('studio.template.cv')).toBe('sidebar-left-navy');
    expect(window.localStorage.getItem('studio.template.cover_letter')).toBe('classic-letter');
  });
});
