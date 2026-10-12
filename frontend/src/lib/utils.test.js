import { describe, expect, it } from 'vitest';

import { cn } from './utils';

/**
 * tailwind-merge must understand the custom `@theme` shadow tokens
 * (`shadow-soft`, `shadow-medium`, `shadow-strong`, `shadow-inset`).
 * Without that awareness a variant shadow and a caller override both
 * survive the merge, and the winner is decided by CSS source order —
 * which silently ate the shadows on the suggested-prompt cards.
 */
describe('cn', () => {
  it('lets a custom shadow override a built-in variant shadow', () => {
    const merged = cn('shadow-xs', 'shadow-soft');
    expect(merged).not.toMatch(/(^|\s)shadow-xs(\s|$)/);
    expect(merged).toMatch(/(^|\s)shadow-soft(\s|$)/);
  });

  it('lets a custom shadow override another custom shadow', () => {
    expect(cn('shadow-soft', 'shadow-medium')).toMatch(/(^|\s)shadow-medium(\s|$)/);
    expect(cn('shadow-soft', 'shadow-medium')).not.toMatch(/(^|\s)shadow-soft(\s|$)/);
  });

  it('honours the last shadow passed, whichever side it comes from', () => {
    // A built-in shadow after a custom one must win…
    expect(cn('shadow-soft', 'shadow-xs')).not.toContain('shadow-soft');
    expect(cn('shadow-soft', 'shadow-xs')).toContain('shadow-xs');
    // …and a custom shadow after a built-in one must win.
    expect(cn('shadow-xs', 'shadow-soft')).not.toContain('shadow-xs');
    expect(cn('shadow-xs', 'shadow-soft')).toContain('shadow-soft');
  });

  it('still dedupes ordinary Tailwind conflicts', () => {
    expect(cn('p-2', 'p-4')).toMatch(/(^|\s)p-4(\s|$)/);
    expect(cn('text-sm', 'text-lg')).toMatch(/(^|\s)text-lg(\s|$)/);
    expect(cn('rounded-lg', 'rounded-2xl')).toMatch(/(^|\s)rounded-2xl(\s|$)/);
  });

  it('drops falsy values', () => {
    expect(cn('block', false, undefined, null, '')).toBe('block');
  });

  it('resolves the exact class set used by the suggested-prompt cards', () => {
    const merged = cn(
      'inline-flex items-center justify-center rounded-lg text-sm font-medium transition-colors',
      'bg-background text-foreground shadow-xs transition-shadow hover:shadow-sm',
      'h-auto whitespace-normal justify-start rounded-2xl bg-card p-4 text-left shadow-soft transition-shadow hover:shadow-medium',
    );
    expect(merged).toContain('shadow-soft');
    expect(merged).toContain('hover:shadow-medium');
    expect(merged).not.toContain('shadow-xs');
    expect(merged).not.toContain('hover:shadow-sm');
  });
});
