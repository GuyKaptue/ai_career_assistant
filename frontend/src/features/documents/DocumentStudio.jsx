import React, { useMemo } from 'react';
import { useI18n } from '../../i18n';
import { Button } from '../../components/ui/button';
import { Input } from '../../components/ui/input';
import { Textarea } from '../../components/ui/textarea';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '../../components/ui/card';
import { Label } from '../../components/ui/label';
import { Select } from '../../components/ui/select';
import { Badge } from '../../components/ui/badge';

/**
 * Document studio form. Presentational: the parent owns the form
 * state and the generation action so the header's generate button
 * and this form stay in sync.
 */
export default function DocumentStudio({
  form,
  onFieldChange,
  onGenerate,
  generating,
  selectedTemplate,
  design,
  isCv,
  themes,
  themesLoading,
  countryProfile,
  countryLoading,
  onDesignChange,
  onPreview,
  onDownload,
  canExport,
  exporting,
}) {
  const { t } = useI18n();

  // Sidebar applies only when the EFFECTIVE layout is two-column. When a
  // country is selected its profile wins (hybrid / single-column countries
  // force one column, so any template is disabled there); otherwise the
  // template's own columns decide. While the country profile is still
  // loading we keep the toggle disabled.
  const sidebarEnabled = useMemo(() => {
    if (!isCv) return false;
    if (design.country) {
      if (countryLoading) return false;
      return countryProfile?.cv_layout === 'two_column';
    }
    return selectedTemplate?.columns === 2;
  }, [isCv, design.country, countryProfile, countryLoading, selectedTemplate]);

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle>{t('documents.studioTitle')}</CardTitle>
        <CardDescription>{t('documents.studioDescription')}</CardDescription>
        {selectedTemplate && (
          <div className="flex items-center gap-2 pt-2 border-t">
            <Badge variant="secondary" className="text-xs">
              {t('documents.selectedTemplate', { name: selectedTemplate.name })}
            </Badge>
          </div>
        )}
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

        {isCv && (
          <fieldset className="border rounded-lg p-4">
            <legend className="text-xs font-medium px-2">
              {t('templates.carousel.design')}
            </legend>
            <div className="grid gap-3 sm:grid-cols-3">
              <div className="space-y-2">
                <Label htmlFor="theme-select">{t('templates.carousel.theme')}</Label>
                <Select
                  id="theme-select"
                  value={design.themeId || ''}
                  onChange={(event) =>
                    onDesignChange.theme(event.target.value || undefined)
                  }
                  disabled={themesLoading}
                >
                  <option value="">
                    {t('templates.carousel.themeDefault')}
                  </option>
                  {themes.map((theme) => (
                    <option key={theme.id} value={theme.id}>
                      {theme.name}
                    </option>
                  ))}
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="country-select">{t('templates.carousel.country')}</Label>
                <Select
                  id="country-select"
                  value={design.country || ''}
                  onChange={(event) =>
                    onDesignChange.country(event.target.value || undefined)
                  }
                  disabled={countryLoading}
                >
                  <option value="">{t('templates.carousel.countryNone')}</option>
                  <option value="DE">Germany</option>
                  <option value="AT">Austria</option>
                  <option value="CH">Switzerland</option>
                  <option value="FR">France</option>
                  <option value="BE">Belgium</option>
                  <option value="NL">Netherlands</option>
                  <option value="ES">Spain</option>
                  <option value="IT">Italy</option>
                  <option value="GB">United Kingdom</option>
                  <option value="US">United States</option>
                  <option value="CA">Canada</option>
                  <option value="AU">Australia</option>
                  <option value="other">Other</option>
                </Select>
              </div>
              <div className="space-y-2">
                <Label htmlFor="sidebar-toggle">{t('templates.carousel.sidebar')}</Label>
                <div className="flex gap-2">
                  <Button
                    variant={
                      design.sidebar === 'left' ? 'default' : 'outline'
                    }
                    size="sm"
                    onClick={() => onDesignChange.sidebar('left')}
                    disabled={!sidebarEnabled}
                  >
                    {t('templates.carousel.sidebarLeft')}
                  </Button>
                  <Button
                    variant={
                      design.sidebar === 'right' ? 'default' : 'outline'
                    }
                    size="sm"
                    onClick={() => onDesignChange.sidebar('right')}
                    disabled={!sidebarEnabled}
                  >
                    {t('templates.carousel.sidebarRight')}
                  </Button>
                </div>
                {!sidebarEnabled && (
                  <p className="text-xs text-muted-foreground">
                    {design.country
                      ? t('templates.carousel.singleColumnCountry')
                      : t('templates.carousel.twoColumnOnly')}
                  </p>
                )}
              </div>
            </div>
            {countryProfile && (
              <div className="bg-muted/30 rounded-lg p-3">
                <p className="text-xs text-muted-foreground">
                  {countryProfile.cv_layout} · {countryProfile.paper_size}
                  {countryProfile.caveats?.length
                    ? ` — ${countryProfile.caveats.join(', ')}`
                    : ''}
                </p>
              </div>
            )}
          </fieldset>
        )}

        <div className="flex flex-wrap items-center gap-2">
          <Button
            type="button"
            disabled={generating}
            onClick={() => onGenerate()}
            className="w-full sm:w-auto"
          >
            {generating ? t('documents.generating') : t('nav.generateCv')}
          </Button>
          {canExport && onPreview && onDownload && (
            <>
              <Button
                type="button"
                variant="outline"
                disabled={exporting}
                onClick={() => onPreview()}
              >
                {t('documents.preview')}
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={exporting}
                onClick={() => onDownload('pdf')}
              >
                {t('documents.downloadPdf')}
              </Button>
              <Button
                type="button"
                variant="outline"
                disabled={exporting}
                onClick={() => onDownload('docx')}
              >
                {t('documents.downloadDocx')}
              </Button>
            </>
          )}
        </div>
      </CardContent>
    </Card>
  );
}
