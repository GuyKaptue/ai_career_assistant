/**
 * TemplateCarousel — template picker for the document studio.
 *
 * Renders one card per template from ``GET /api/v1/templates?document_type=…``.
 * Each card shows a lazy-loaded sample image from
 * ``GET /api/v1/templates/{id}/sample`` (built with the current design:
 * theme_id, country, sidebar, locale, document_type) with a CSS-thumbnail
 * fallback built from ``layout`` + ``color_scheme`` + ``columns``.
 *
 * Cards whose ``supported_locales`` lacks the current locale are disabled
 * (not hidden). The carousel is a ``role="listbox"`` with arrow-key focus
 * movement and Enter/Space selection.
 *
 * @param {string} documentType   "cv" | "cover_letter" | "resignation"
 * @param {string} locale         current i18n locale ("en" | "de" | "fr")
 * @param {string|null} selectedId  id of the currently selected template
 * @param {function(string)} onSelect  called with the chosen template id
 * @param {{themeId?: string, country?: string, sidebar?: string}} design  client-side design choices
 */

import React, { useState, useEffect, useCallback, useMemo } from 'react';

import { apiRequest, getApiBase } from '../../lib/api';
import { useSession } from '../../hooks/useSession';
import { toApiCountry } from '../../hooks/useDesignOptions';
import { useI18n } from '../../i18n';
import {
  Carousel,
  CarouselContent,
  CarouselItem,
  CarouselPrevious,
  CarouselNext,
  useCarousel,
} from '../../components/ui/carousel';
import { LoadingState, ErrorState } from '../../components/AsyncStates';
import { Button } from '../../components/ui/button';
import {
  Card,
  CardContent,
  CardTitle,
  CardDescription,
} from '../../components/ui/card';
import { Badge } from '../../components/ui/badge';
import { cn } from '../../lib/utils';

/** Map a color_scheme value to an accent colour for CSS thumbnails. */
const SCHEME_ACCENT = {
  blue: '#2563eb',
  slate: '#64748b',
  dark: '#0f172a',
  neutral: '#71717a',
  maroon: '#991b1b',
  teal: '#0d9488',
  coral: '#ef4444',
  indigo: '#4f46e5',
  olive: '#658300',
  steel: '#4a6fa5',
  orange: '#ea580c',
  charcoal: '#262626',
  ivory: '#f7f5f0',
  gray: '#9ca3af',
  violet: '#7c3aed',
  cyan: '#0891b2',
};

/** Build the absolute sample-image URL for a template card. */
function sampleUrl(templateId, documentType, locale, design = {}) {
  const base = getApiBase();
  const params = new URLSearchParams({
    document_type: documentType,
    locale,
    format: 'png',
  });
  if (design.themeId) params.set('theme_id', design.themeId);
  if (design.country) params.set('country', toApiCountry(design.country));
  if (design.sidebar) params.set('sidebar', design.sidebar);
  return `${base}/api/v1/templates/${encodeURIComponent(templateId)}/sample?${params}`;
}

/** Build the public sample-download URL (PDF) for a card's "download sample". */
function sampleDownloadUrl(templateId, documentType, locale, design = {}) {
  const base = getApiBase();
  const params = new URLSearchParams({
    document_type: documentType,
    locale,
    format: 'pdf',
  });
  if (design.themeId) params.set('theme_id', design.themeId);
  if (design.country) params.set('country', toApiCountry(design.country));
  if (design.sidebar) params.set('sidebar', design.sidebar);
  return `${base}/api/v1/templates/${encodeURIComponent(templateId)}/sample?${params}`;
}

/** Inline style for the CSS thumbnail fallback from layout + color_scheme. */
function thumbnailStyle(template) {
  const accent =
    SCHEME_ACCENT[template.color_scheme || 'blue'] || SCHEME_ACCENT.blue;
  const isTwoCol = template.columns === 2;
  return {
    background: isTwoCol
      ? `linear-gradient(90deg, ${accent}22 0%, ${accent}22 30%, transparent 30%, transparent 100%)`
      : accent + '15',
    border: `2px solid ${accent}`,
  };
}

/**
 * TemplateCarousel — fetches templates and renders them in an Embla carousel.
 */
export default function TemplateCarousel({
  documentType,
  locale,
  selectedId,
  onSelect,
  design = {},
}) {
  const { t } = useI18n();
  const { session } = useSession();
  const [templates, setTemplates] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [filter, setFilter] = useState('all');
  const [focusedIndex, setFocusedIndex] = useState(0);

  const {
    emblaRef,
    emblaNodeRef,
    canScrollPrev,
    canScrollNext,
    scrollPrev,
    scrollNext,
  } = useCarousel();

  const filtered = useMemo(() => {
    if (filter === 'all') return templates;
    if (filter === 'mine') return templates.filter((t) => t.source === 'user');
    const cols = filter === 'one' ? 1 : 2;
    return templates.filter((t) => (t.columns || 1) === cols);
  }, [templates, filter]);

  useEffect(() => {
    let isMounted = true;

    async function load() {
      setLoading(true);
      setError(null);
      try {
        const payload = await apiRequest(
          `/api/v1/templates?document_type=${encodeURIComponent(documentType)}`,
          { session },
        );
        if (!isMounted) return;
        setTemplates(Array.isArray(payload.items) ? payload.items : []);
      } catch (fetchError) {
        if (!isMounted) return;
        setError(fetchError);
        setTemplates([]);
      } finally {
        if (isMounted) setLoading(false);
      }
    }

    load();
    return () => {
      isMounted = false;
    };
  }, [documentType, session]);

  const isDisabled = (template) =>
    template.supported_locales &&
    !template.supported_locales.includes(locale);

  const handleSelect = (template) => {
    if (isDisabled(template)) return;
    onSelect(template.id);
    setFocusedIndex(filtered.indexOf(template));
  };

  const handleKeyDown = (event, index) => {
    if (event.key === 'ArrowRight') {
      event.preventDefault();
      setFocusedIndex((i) => Math.min(i + 1, filtered.length - 1));
    } else if (event.key === 'ArrowLeft') {
      event.preventDefault();
      setFocusedIndex((i) => Math.max(i - 1, 0));
    } else if (event.key === 'Enter' || event.key === ' ') {
      event.preventDefault();
      const template = filtered[index];
      if (template && !isDisabled(template)) {
        onSelect(template.id);
      }
    }
  };

  if (loading) {
    return <LoadingState label={t('templates.carousel.loading')} />;
  }

  if (error) {
    return (
      <ErrorState
        message={error.message || t('templates.carousel.error')}
        onRetry={() => {
          setLoading(true);
          setError(null);
        }}
        retryLabel={t('templates.carousel.retry')}
      />
    );
  }

  if (filtered.length === 0) {
    return (
      <div role="listbox" aria-label={t('templates.carousel.title')}>
        <p className="text-center text-sm text-muted-foreground py-4">
          {t('templates.carousel.empty')}
        </p>
      </div>
    );
  }

  return (
    <div role="listbox" aria-label={t('templates.carousel.title')}>
      <div className="flex flex-wrap gap-2 mb-4">
        <Button
          variant={filter === 'all' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setFilter('all')}
        >
          {t('templates.carousel.all')}
        </Button>
        <Button
          variant={filter === 'one' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setFilter('one')}
        >
          {t('templates.carousel.oneColumn')}
        </Button>
        <Button
          variant={filter === 'two' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setFilter('two')}
        >
          {t('templates.carousel.twoColumns')}
        </Button>
        <Button
          variant={filter === 'mine' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setFilter('mine')}
        >
          {t('templates.carousel.mine')}
        </Button>
      </div>

      <Carousel ref={emblaRef} className="relative">
        <CarouselPrevious
          onClick={scrollPrev}
          disabled={!canScrollPrev}
          aria-label={t('templates.carousel.prev')}
        >
          ‹
        </CarouselPrevious>
        <CarouselContent
          ref={emblaNodeRef}
          className="flex gap-2 overflow-hidden"
        >
          {filtered.map((template, index) => {
            const disabled = isDisabled(template);
            const selected = selectedId === template.id;
            const focused = focusedIndex === index;
            return (
              <CarouselItem
                key={template.id}
                className="min-w-[200px] shrink-0"
                role="option"
                aria-selected={selected}
                aria-disabled={disabled || undefined}
                tabIndex={focused ? 0 : -1}
                onKeyDown={(event) => handleKeyDown(event, index)}
                onClick={() => handleSelect(template)}
              >
                <Card
                  className={cn(
                    'w-full cursor-pointer transition-all duration-200',
                    disabled
                      ? 'opacity-50 border-border'
                      : selected
                      ? 'border-primary ring-2 ring-primary'
                      : 'border-border hover:border-primary',
                  )}
                >
                  <CardContent className="p-3">
                    {!disabled && (
                      <img
                        src={sampleUrl(
                          template.id,
                          documentType,
                          locale,
                          design,
                        )}
                        alt={template.name}
                        loading="lazy"
                        className="w-full h-32 object-cover rounded-lg mb-2"
                      />
                    )}
                    <div
                      className="h-32 rounded-lg flex items-center justify-center mb-2 text-xs"
                      style={thumbnailStyle(template)}
                    >
                      {disabled
                        ? t('templates.carousel.disabledLocale')
                        : template.layout || template.color_scheme || ''}
                    </div>
                    <CardTitle className="text-sm leading-tight">
                      {template.name}
                    </CardTitle>
                    <CardDescription className="text-xs">
                      {template.description || t('templates.documentType')}
                    </CardDescription>
                    {template.columns === 2 && template.sidebar && (
                      <Badge variant="outline" className="text-xs mt-1">
                        {`Sidebar ${template.sidebar}`}
                      </Badge>
                    )}
                    {!disabled && (
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="mt-1 h-7 px-2 text-xs"
                        aria-label={t('templates.carousel.downloadSample')}
                        onClick={(event) => {
                          // Keep the click from selecting the card as well.
                          event.stopPropagation();
                          window.open(
                            sampleDownloadUrl(template.id, documentType, locale, design),
                            '_blank',
                          );
                        }}
                      >
                        {t('templates.carousel.downloadSample')}
                      </Button>
                    )}
                  </CardContent>
                </Card>
              </CarouselItem>
            );
          })}
        </CarouselContent>
        <CarouselNext
          onClick={scrollNext}
          disabled={!canScrollNext}
          aria-label={t('templates.carousel.next')}
        >
          ›
        </CarouselNext>
      </Carousel>
    </div>
  );
}