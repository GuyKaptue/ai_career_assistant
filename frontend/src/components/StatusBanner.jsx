import React from 'react';
import { useI18n } from '../i18n';
import { useStatus } from '../hooks/useStatus.jsx';
import { Card, CardContent, CardHeader, CardTitle } from './ui/card';
import { Badge } from './ui/badge';

/**
 * Renders the global status channel in an aria-live region so
 * screen readers announce generation, ATS, and tracker results
 * without moving focus.
 */
export default function StatusBanner() {
  const { t } = useI18n();
  const { status, summary } = useStatus();

  return (
    <Card className="mt-6" aria-live="polite" aria-atomic="false">
      <CardHeader>
        <CardTitle className="text-lg">{t('generation.title')}</CardTitle>
        <Badge variant="secondary" className="text-sm font-normal">
          {status}
        </Badge>
      </CardHeader>
      <CardContent>
        <p className="text-sm">{summary || t('generation.placeholder')}</p>
      </CardContent>
    </Card>
  );
}
