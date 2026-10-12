# i18n

## Purpose

Internationalization (FE-04). Context provider
with dictionary lookup and `{variable}`
interpolation.

## Locales

- `en` — English (default)
- `de` — German
- `fr` — French

## Behavior

- The selected locale persists in
  `localStorage` (`aca-locale`).
- Missing keys fall back to the key itself, so
  partial translations never crash the UI.
- `t(key, vars)` interpolates `{name}` placeholders.

## Key Exports

- `I18nProvider`, `useI18n()` → `{ locale, availableLocales, t, setLocale }`

## Testing

- `i18n/index.test.jsx` — defaults, interpolation,
  fallback, locale switching
