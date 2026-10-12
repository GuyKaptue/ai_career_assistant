/**
 * Legacy Tailwind JS config.
 *
 * Tailwind v4 (via @tailwindcss/vite) does not load this file - all theme
 * configuration lives in the `@theme` block of src/styles.css, which is the
 * single source of truth for colors, fonts, radii and shadows. We keep this
 * file only so tooling that expects it (e.g. the shadcn CLI) finds one; do
 * not add design tokens here, they will never be compiled.
 */
export default { content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'] };
