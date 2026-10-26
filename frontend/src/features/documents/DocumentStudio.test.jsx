import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import DocumentStudio from './DocumentStudio';
import { I18nProvider } from '../../i18n/index.jsx';

const baseForm = {
  full_name: '',
  target_role: '',
  company: '',
  summary: '',
  job_description: '',
  skills: '',
  document_type: 'cv',
};

function renderStudio(overrides = {}) {
  const props = {
    form: baseForm,
    onFieldChange: vi.fn(),
    onGenerate: vi.fn(),
    generating: false,
    selectedTemplate: { id: 'professional', name: 'Professional' },
    design: { themeId: '', country: '', sidebar: '' },
    isCv: true,
    themes: [],
    themesLoading: false,
    countryProfile: null,
    countryLoading: false,
    onDesignChange: { theme: vi.fn(), country: vi.fn(), sidebar: vi.fn() },
    ...overrides,
  };
  render(
    <I18nProvider>
      <DocumentStudio {...props} />
    </I18nProvider>
  );
  return props;
}

// The sidebar toggle's enabled state is gated on the EFFECTIVE column layout:
// country selected -> profile.cv_layout === 'two_column'; otherwise the
// template's own columns === 2.
describe('DocumentStudio sidebar gating (effective columns)', () => {
  it('disables design controls entirely for non-CV documents', () => {
    renderStudio({ isCv: false, form: { ...baseForm, document_type: 'cover_letter' } });
    expect(screen.queryByRole('button', { name: 'Left' })).toBeNull();
    expect(screen.queryByRole('button', { name: 'Right' })).toBeNull();
  });

  it('enables the sidebar for a two-column template with no country', () => {
    renderStudio({ selectedTemplate: { id: 'sidebar-left-navy', name: 'Navy', columns: 2 } });
    expect(screen.getByRole('button', { name: 'Left' })).toBeEnabled();
  });

  it('disables the sidebar for a one-column template with no country', () => {
    renderStudio({ selectedTemplate: { id: 'minimal', name: 'Minimal', columns: 1 } });
    expect(screen.getByRole('button', { name: 'Left' })).toBeDisabled();
  });

  it('disables the sidebar for the professional template (no columns field) with no country', () => {
    renderStudio({ selectedTemplate: { id: 'professional', name: 'Professional' } });
    expect(screen.getByRole('button', { name: 'Left' })).toBeDisabled();
  });

  it('enables the sidebar for the professional template in a two-column country (DE)', () => {
    renderStudio({
      selectedTemplate: { id: 'professional', name: 'Professional' },
      design: { themeId: '', country: 'DE', sidebar: '' },
      countryProfile: { cv_layout: 'two_column', paper_size: 'A4', caveats: [] },
    });
    expect(screen.getByRole('button', { name: 'Left' })).toBeEnabled();
  });

  it('keeps the sidebar disabled while the country profile is still loading', () => {
    renderStudio({
      selectedTemplate: { id: 'sidebar-left-navy', name: 'Navy', columns: 2 },
      design: { themeId: '', country: 'DE', sidebar: '' },
      countryProfile: { cv_layout: 'two_column', paper_size: 'A4', caveats: [] },
      countryLoading: true,
    });
    expect(screen.getByRole('button', { name: 'Left' })).toBeDisabled();
  });

  it('disables the sidebar for a two-column template in a single-column country (US)', () => {
    renderStudio({
      selectedTemplate: { id: 'sidebar-left-navy', name: 'Navy', columns: 2 },
      design: { themeId: '', country: 'US', sidebar: '' },
      countryProfile: { cv_layout: 'single_column', paper_size: 'Letter', caveats: [] },
    });
    expect(screen.getByRole('button', { name: 'Left' })).toBeDisabled();
  });

  it('disables the sidebar for a two-column template in a hybrid country (SE)', () => {
    renderStudio({
      selectedTemplate: { id: 'sidebar-left-navy', name: 'Navy', columns: 2 },
      design: { themeId: '', country: 'SE', sidebar: '' },
      countryProfile: { cv_layout: 'hybrid', paper_size: 'A4', caveats: [] },
    });
    expect(screen.getByRole('button', { name: 'Left' })).toBeDisabled();
  });

  it('shows the country hint (not the template hint) when a country disables the sidebar', () => {
    renderStudio({
      selectedTemplate: { id: 'sidebar-left-navy', name: 'Navy', columns: 2 },
      design: { themeId: '', country: 'US', sidebar: '' },
      countryProfile: { cv_layout: 'single_column', paper_size: 'Letter', caveats: [] },
    });
    expect(screen.getByText(/Single-column country/)).toBeInTheDocument();
  });

  it('shows the template hint when no country and a one-column template disables the sidebar', () => {
    renderStudio({ selectedTemplate: { id: 'minimal', name: 'Minimal', columns: 1 } });
    expect(screen.getByText(/Sidebar only for two-column templates/)).toBeInTheDocument();
  });
});
