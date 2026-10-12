import React from 'react';
import { Button } from './ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from './ui/card';

/**
 * Shared async UI states (FE-03). Every data-driven panel renders
 * one of these so loading, empty, and error states are consistent
 * and announced to assistive technology.
 */

export function LoadingState({ label = 'Loading…' }) {
  return (
    <p className="text-center text-sm text-muted-foreground my-4" role="status">
      {label}
    </p>
  );
}

export function EmptyState({ label }) {
  return (
    <Card className="bg-muted/30">
      <CardContent className="py-6">
        <p className="text-center text-sm text-muted-foreground">{label}</p>
      </CardContent>
    </Card>
  );
}

export function ErrorState({ message, onRetry, retryLabel = 'Retry' }) {
  return (
    <Card className="bg-destructive/5">
      <CardContent className="py-4">
        <p className="text-sm text-destructive" role="alert">
          {message}
        </p>
        {onRetry && (
          <Button
            type="button"
            variant="ghost"
            size="sm"
            onClick={onRetry}
            className="mt-3"
          >
            {retryLabel}
          </Button>
        )}
      </CardContent>
    </Card>
  );
}
