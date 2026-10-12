import React from 'react';
import { useI18n } from '../../i18n';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Textarea } from '../../components/ui/textarea';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../components/ui/card';
import { Label } from '../../components/ui/label';

/**
 * Document studio form. Presentational: the parent owns the form
 * state and the generation action so the header's generate button
 * and this form stay in sync.
 */
export default function DocumentStudio({ form, onFieldChange, onGenerate, generating }) {
  const { t } = useI18n();

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle>{t('documents.studioTitle')}</CardTitle>
        <CardDescription>{t('documents.studioDescription')}</CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="grid gap-4 sm:grid-cols-2">
          <div className="space-y-2">
            <Label htmlFor="full_name">{t('documents.fullName')}</Label>
            <Input
              id="full_name"
              name="full_name"
              value={form.full_name}
              onChange={onFieldChange}
              placeholder={t('documents.fullNamePlaceholder')}
            />
          </div>
          <div className="space-y-2">
            <Label htmlFor="target_role">{t('documents.targetRole')}</Label>
            <Input
              id="target_role"
              name="target_role"
              value={form.target_role}
              onChange={onFieldChange}
              placeholder={t('documents.targetRolePlaceholder')}
            />
          </div>
          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="company">{t('documents.company')}</Label>
            <Input
              id="company"
              name="company"
              value={form.company}
              onChange={onFieldChange}
              placeholder={t('documents.companyPlaceholder')}
            />
          </div>
          <div className="space-y-2 sm:col-span-2">
            <Label htmlFor="summary">{t('documents.summary')}</Label>
            <Textarea
              id="summary"
              name="summary"
              value={form.summary}
              onChange={onFieldChange}
              placeholder={t('documents.summaryPlaceholder')}
              rows={4}
            />
          </div>
        </div>
        <Button
          type="button"
          disabled={generating}
          onClick={() => onGenerate()}
          className="w-full sm:w-auto"
        >
          {generating ? t('documents.generating') : t('nav.generateCv')}
        </Button>
      </CardContent>
    </Card>
  );
}
