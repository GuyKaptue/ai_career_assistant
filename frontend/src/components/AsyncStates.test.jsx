import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { EmptyState, ErrorState, LoadingState } from './AsyncStates';

describe('AsyncStates', () => {
  it('LoadingState announces itself with role="status"', () => {
    render(<LoadingState label="Loading templates…" />);

    const status = screen.getByRole('status');
    expect(status).toHaveTextContent('Loading templates…');
  });

  it('EmptyState renders the empty message', () => {
    render(<EmptyState label="No applications tracked yet." />);

    expect(screen.getByText('No applications tracked yet.')).toBeInTheDocument();
  });

  it('ErrorState announces itself with role="alert" and offers retry', () => {
    const onRetry = vi.fn();
    render(<ErrorState message="Request failed" onRetry={onRetry} retryLabel="Retry preview" />);

    const alert = screen.getByRole('alert');
    expect(alert).toHaveTextContent('Request failed');

    const retry = screen.getByRole('button', { name: 'Retry preview' });
    retry.click();
    expect(onRetry).toHaveBeenCalledTimes(1);
  });

  it('ErrorState renders without a retry button when no handler is given', () => {
    render(<ErrorState message="Request failed" />);

    expect(screen.getByRole('alert')).toBeInTheDocument();
    expect(screen.queryByRole('button')).not.toBeInTheDocument();
  });
});
