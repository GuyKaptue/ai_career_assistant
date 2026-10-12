import { createElement, forwardRef } from 'react';
import {
  BRAND_A,
  BRAND_COLORS,
  BRAND_CROSSBAR,
  BRAND_RADIUS,
  BRAND_SPARK,
  BRAND_STROKE,
  BRAND_VIEWBOX,
} from './brandPaths.js';

/**
 * AI Career Assistant brand mark.
 *
 * variant "badge"  Rounded square with the mark inside. Colours come from the CSS
 *                  variables --aca-brand-bg, --aca-brand-fg and --aca-brand-spark.
 *                  Point them at your theme tokens, for example
 *                  --aca-brand-bg: var(--accent); --aca-brand-fg: var(--accent-ink);
 * variant "glyph"  The mark alone, drawn in currentColor.
 */
export const BrandMark = forwardRef(function BrandMark(
  { size = 32, variant = 'badge', title, className, ...rest },
  ref,
) {
  const labelled = Boolean(title || rest['aria-label'] || rest['aria-labelledby']);
  const badge = variant === 'badge';

  const strokeStyle = badge ? { stroke: `var(--aca-brand-fg, ${BRAND_COLORS.fg})` } : { stroke: 'currentColor' };
  const sparkStyle = badge ? { fill: `var(--aca-brand-spark, ${BRAND_COLORS.spark})` } : { fill: 'currentColor' };

  return createElement(
    'svg',
    {
      ref,
      xmlns: 'http://www.w3.org/2000/svg',
      width: size,
      height: size,
      viewBox: BRAND_VIEWBOX,
      focusable: 'false',
      className: ['aca-brand-mark', className].filter(Boolean).join(' '),
      ...(labelled ? { role: 'img' } : { 'aria-hidden': true }),
      ...rest,
    },
    title ? createElement('title', { key: 'title' }, title) : null,
    badge
      ? createElement('rect', {
          key: 'bg',
          width: 64,
          height: 64,
          rx: BRAND_RADIUS,
          style: { fill: `var(--aca-brand-bg, ${BRAND_COLORS.bg})` },
        })
      : null,
    createElement('path', {
      key: 'a',
      d: BRAND_A,
      fill: 'none',
      strokeWidth: BRAND_STROKE,
      strokeLinecap: 'round',
      strokeLinejoin: 'round',
      style: strokeStyle,
    }),
    createElement('path', {
      key: 'bar',
      d: BRAND_CROSSBAR,
      fill: 'none',
      strokeWidth: BRAND_STROKE,
      strokeLinecap: 'round',
      style: strokeStyle,
    }),
    createElement('path', { key: 'spark', d: BRAND_SPARK, style: sparkStyle }),
  );
});
BrandMark.displayName = 'BrandMark';
