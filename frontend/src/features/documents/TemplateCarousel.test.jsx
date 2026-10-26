import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

// Embla needs layout/observers that jsdom lacks; a no-op keeps the component
// rendering its cards (api undefined => prev/next disabled, which is fine).
vi.mock('embla-carousel-react', () => ({ default: () => [() => {}, undefined] }));
vi.mock('../../lib/api', () => ({ apiRequest: vi.fn(), getApiBase: () => '' }));
vi.mock('../../hooks/useSession', () => {
  const session = { access_token: 'token' };
  return { useSession: () => ({ session, authLoading: false }) };
});

import TemplateCarousel from './TemplateCarousel';
import { I18nProvider } from '../../i18n/index.jsx';
import { apiRequest } from '../../lib/api';

function renderCarousel(props = {}) {
  render(
    <I18nProvider>
      <TemplateCarousel
        documentType="cv"
        locale="en"
        selectedId="professional"
        onSelect={vi.fn()}
        design={{ themeId: 'navy', country: 'DE', sidebar: 'left' }}
        {...props}
      />
    </I18nProvider>,
  );
}

const TEMPLATE = {
  id: 'professional',
  name: 'Professional',
  document_type: 'cv',
  supported_locales: ['en'],
  columns: 1,
  layout: 'single-column',
  color_scheme: 'blue',
};

beforeEach(() => vi.clearAllMocks());
afterEach(() => vi.restoreAllMocks());

describe('TemplateCarousel (sub-step 7)', () => {
  it('builds the sample image URL from theme/country/sidebar/locale + document type', async () => {
    apiRequest.mockResolvedValue({ items: [TEMPLATE] });
    renderCarousel();
    const img = await screen.findByAltText('Professional');
    const src = img.getAttribute('src');
    expect(src).toContain('/api/v1/templates/professional/sample');
    expect(src).toContain('document_type=cv');
    expect(src).toContain('locale=en');
    expect(src).toContain('format=png');
    expect(src).toContain('theme_id=navy');
    expect(src).toContain('country=DE');
    expect(src).toContain('sidebar=left');
  });

  it('disables (does not hide) a card whose supported_locales lack the locale', async () => {
    apiRequest.mockResolvedValue({ items: [{ ...TEMPLATE, supported_locales: ['de'] }] });
    renderCarousel();
    await screen.findByText('Not available in your language');
    expect(screen.getByRole('option', { name: /Not available/ })).toHaveAttribute(
      'aria-disabled',
      'true',
    );
    expect(screen.queryByAltText('Professional')).toBeNull();
  });

  it('keeps the CSS thumbnail fallback available when the image errors', async () => {
    apiRequest.mockResolvedValue({ items: [TEMPLATE] });
    renderCarousel();
    const img = await screen.findByAltText('Professional');
    fireEvent.error(img);
    expect(screen.getByText('single-column')).toBeInTheDocument();
  });

  it('filters cards via the column chips', async () => {
    apiRequest.mockResolvedValue({
      items: [
        TEMPLATE,
        { ...TEMPLATE, id: 'modern', name: 'Modern', columns: 2, sidebar: 'left' },
      ],
    });
    renderCarousel({ selectedId: 'modern' });
    await screen.findByText('Modern');
    fireEvent.click(screen.getByRole('button', { name: 'Two columns' }));
    await waitFor(() => expect(screen.queryByText('Professional')).toBeNull());
    expect(screen.getByText('Modern')).toBeInTheDocument();
  });

  it('offers a public sample download per enabled card (PDF, no token in URL)', async () => {
    apiRequest.mockResolvedValue({ items: [TEMPLATE] });
    const open = vi.spyOn(window, 'open').mockImplementation(() => {});
    renderCarousel();
    const btn = await screen.findByRole('button', { name: 'Download sample' });
    fireEvent.click(btn);
    expect(open).toHaveBeenCalledTimes(1);
    const [url, target] = open.mock.calls[0];
    expect(url).toContain('/api/v1/templates/professional/sample');
    expect(url).toContain('format=pdf');
    expect(target).toBe('_blank');
  });
});