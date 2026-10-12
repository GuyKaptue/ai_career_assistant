import React from 'react';
import { fireEvent, render, screen } from '@testing-library/react';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import JobDiscovery, { failedProviders } from './JobDiscovery';
import { I18nProvider } from '../../i18n/index.jsx';
import { StatusProvider } from '../../hooks/useStatus.jsx';

vi.mock('../../lib/api', () => ({
  apiRequest: vi.fn(),
}));

const { apiRequest } = await import('../../lib/api');

const session = { user: { email: 'jane@example.com' }, access_token: 'token' };

function renderWithProviders(ui) {
  return render(
    <I18nProvider>
      <StatusProvider>{ui}</StatusProvider>
    </I18nProvider>,
  );
}

async function search() {
  fireEvent.click(screen.getByRole('button', { name: 'Search jobs' }));
  await screen.findByText('Data Analyst');
}

describe('JobDiscovery (JOB-07 / JOB-08)', () => {
  beforeEach(() => {
    apiRequest.mockReset();
  });

  it('renders provider attribution and only the metadata the provider supplied', async () => {
    apiRequest.mockResolvedValue({
      results: [
        {
          title: 'Data Analyst',
          company: 'Northwind',
          location: 'Berlin',
          url: 'https://jobs.example.test/1',
          provider: 'adzuna',
          remote: true,
          salary: '55000–65000',
          published_at: '2026-10-01T00:00:00Z',
        },
        {
          title: 'Reporting Analyst',
          company: 'Globex',
          location: null,
          url: null,
          provider: 'arbeitnow',
          remote: null,
          salary: null,
          published_at: null,
        },
      ],
      count: 2,
      page: 1,
      limit: 5,
      total: 2,
      partial: false,
      provider_status: [
        { provider: 'adzuna', status: 'succeeded', count: 1 },
        { provider: 'arbeitnow', status: 'succeeded', count: 1 },
      ],
    });

    renderWithProviders(<JobDiscovery session={session} onCreateApplication={vi.fn()} />);
    await search();

    expect(screen.getByText('via adzuna')).toBeInTheDocument();
    expect(screen.getByText('via arbeitnow')).toBeInTheDocument();
    expect(screen.getByText('Remote')).toBeInTheDocument();
    expect(screen.getByText(/Salary: 55000–65000/)).toBeInTheDocument();
    expect(screen.getByText(/Posted:/)).toBeInTheDocument();
    // Unknown salary/date/remote for the second job are not invented.
    expect(screen.queryByText(/Salary: null/)).not.toBeInTheDocument();
    expect(screen.queryAllByText(/Salary:/)).toHaveLength(1);
  });

  it('links to the original posting as an external, safe URL', async () => {
    apiRequest.mockResolvedValue({
      results: [
        {
          title: 'Data Analyst',
          company: 'Northwind',
          location: 'Berlin',
          url: 'https://jobs.example.test/1',
          provider: 'arbeitsagentur',
        },
        { title: 'Unsafe Analyst', company: 'X', url: 'javascript:alert(1)', provider: 'arbeitnow' },
      ],
      total: 2,
      provider_status: [],
    });

    renderWithProviders(<JobDiscovery session={session} onCreateApplication={vi.fn()} />);
    await search();

    const link = screen.getByRole('link', { name: /View role/ });
    expect(link).toHaveAttribute('href', 'https://jobs.example.test/1');
    expect(link).toHaveAttribute('target', '_blank');
    expect(link.getAttribute('rel')).toContain('noreferrer');
    expect(link.getAttribute('rel')).toContain('noopener');
    // Non-http(s) links are never rendered.
    expect(screen.getAllByRole('link', { name: /View role/ })).toHaveLength(1);
  });

  it('surfaces a partial-failure notice without discarding successful results', async () => {
    apiRequest.mockResolvedValue({
      results: [{ title: 'Data Analyst', company: 'Northwind', provider: 'arbeitnow' }],
      total: 1,
      partial: true,
      provider_status: [
        { provider: 'adzuna', status: 'failed', count: 0 },
        { provider: 'arbeitnow', status: 'succeeded', count: 1 },
      ],
    });

    renderWithProviders(<JobDiscovery session={session} onCreateApplication={vi.fn()} />);
    await search();

    expect(screen.getByRole('status')).toHaveTextContent('Some job sources were unavailable: adzuna');
    expect(screen.getByText('Data Analyst')).toBeInTheDocument();
  });

  it('loads the next page incrementally and appends results', async () => {
    apiRequest
      .mockResolvedValueOnce({
        results: [{ title: 'Data Analyst', company: 'Northwind', provider: 'adzuna' }],
        page: 1,
        total: 2,
        provider_status: [],
      })
      .mockResolvedValueOnce({
        results: [{ title: 'Second Analyst', company: 'Globex', provider: 'adzuna' }],
        page: 2,
        total: 2,
        provider_status: [],
      });

    renderWithProviders(<JobDiscovery session={session} onCreateApplication={vi.fn()} />);
    await search();

    expect(screen.getByText('Showing 1 of 2 results')).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Load more' }));

    await screen.findByText('Second Analyst');
    expect(screen.getByText('Data Analyst')).toBeInTheDocument();
    expect(apiRequest).toHaveBeenLastCalledWith(expect.stringContaining('page=2'));
  });

  it('flags provider failures from provider_status', () => {
    expect(failedProviders([{ provider: 'a', status: 'succeeded' }, { provider: 'b', status: 'failed' }])).toEqual(['b']);
    expect(failedProviders(undefined)).toEqual([]);
  });
});