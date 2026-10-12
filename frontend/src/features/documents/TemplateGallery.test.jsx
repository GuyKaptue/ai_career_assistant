import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import TemplateGallery from './TemplateGallery';
import { I18nProvider } from '../../i18n/index.jsx';
import { StatusProvider } from '../../hooks/useStatus.jsx';

vi.mock('../../../lib/supabase', () => ({
  supabase: {
    auth: {
      getSession: vi.fn().mockResolvedValue({ data: { session: null } }),
      onAuthStateChange: vi.fn().mockReturnValue({
        data: { subscription: { unsubscribe: vi.fn() } },
      }),
    },
  },
}));

const templates = [
  {
    id: 'professional',
    name: 'Professional',
    document_type: 'cv',
    supported_locales: ['en', 'fr', 'de'],
  },
  {
    id: 'classic-letter',
    name: 'Classic Letter',
    document_type: 'cover_letter',
    supported_locales: ['en', 'fr', 'de'],
  },
];

function renderWithProviders(ui) {
  return render(
    <I18nProvider>
      <StatusProvider>{ui}</StatusProvider>
    </I18nProvider>,
  );
}

describe('TemplateGallery', () => {
  it('renders every template with a select and preview action', () => {
    renderWithProviders(
      <TemplateGallery
        templates={templates}
        loading={false}
        selectedTemplate="professional"
        onSelect={vi.fn()}
        locale="en"
      />,
    );

    expect(screen.getByText('Professional')).toBeInTheDocument();
    expect(screen.getByText('Classic Letter')).toBeInTheDocument();
    expect(screen.getAllByRole('button', { name: /Preview/ })).toHaveLength(2);
  });

  it('marks the selected template with aria-pressed', () => {
    renderWithProviders(
      <TemplateGallery
        templates={templates}
        loading={false}
        selectedTemplate="professional"
        onSelect={vi.fn()}
        locale="en"
      />,
    );

    const selectButton = screen.getByRole('button', { name: 'Select template: Professional' });
    expect(selectButton).toHaveAttribute('aria-pressed', 'true');
  });

  it('shows the empty state when no templates are available', () => {
    renderWithProviders(
      <TemplateGallery
        templates={[]}
        loading={false}
        selectedTemplate=""
        onSelect={vi.fn()}
        locale="en"
      />,
    );

    expect(
      screen.getByText(/No templates are available yet/),
    ).toBeInTheDocument();
  });

  it('shows a loading state while templates load', () => {
    renderWithProviders(
      <TemplateGallery
        templates={[]}
        loading
        selectedTemplate=""
        onSelect={vi.fn()}
        locale="en"
      />,
    );

    expect(screen.getByRole('status')).toHaveTextContent('Loading templates…');
  });
});
