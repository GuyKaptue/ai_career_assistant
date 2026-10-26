import { describe, expect, it } from 'vitest';

import en from './locales/en.js';
import de from './locales/de.js';
import fr from './locales/fr.js';

/** Sorted list of an object's own keys (one nesting level deep is enough). */
function keySet(obj) {
  return Object.keys(obj || {}).sort();
}

// The carousel key set must be identical in the three locales.
// A missing/extra translation under templates.carousel.* in any locale would
// surface as a raw key at runtime, so we assert the three key sets match.
describe('templates.carousel.* i18n parity (en/de/fr)', () => {
  it('has a non-empty carousel block in every locale', () => {
    expect(en.templates?.carousel).toBeTruthy();
    expect(de.templates?.carousel).toBeTruthy();
    expect(fr.templates?.carousel).toBeTruthy();
  });

  it('en/de/fr carousel key sets are identical', () => {
    const enKeys = keySet(en.templates.carousel);
    expect(enKeys.length).toBeGreaterThan(0);
    expect(keySet(de.templates.carousel)).toEqual(enKeys);
    expect(keySet(fr.templates.carousel)).toEqual(enKeys);
  });

  it('includes the sub-step 6 "templateChanged" key in every locale', () => {
    for (const locale of [en, de, fr]) {
      expect(typeof locale.templates.carousel.templateChanged).toBe('string');
      expect(locale.templates.carousel.templateChanged.length).toBeGreaterThan(0);
    }
  });

  // The required templates.carousel.* keys.
  const REQUIRED = [
    'title', 'loading', 'error', 'retry', 'empty', 'disabledLocale', 'selected',
    'sidebarLeft', 'sidebarRight', 'oneColumn', 'twoColumns', 'mine', 'theme',
    'themeDefault', 'country', 'countryNone', 'countryNote', 'downloadSample',
    'templateChanged',
  ];

  it('includes every sub-step 7 required key (non-empty) in each locale', () => {
    for (const [name, locale] of [['en', en], ['de', de], ['fr', fr]]) {
      for (const key of REQUIRED) {
        expect(typeof locale.templates.carousel[key], `${name}.${key}`).toBe('string');
        expect(locale.templates.carousel[key].length, `${name}.${key}`).toBeGreaterThan(0);
      }
    }
  });
});
