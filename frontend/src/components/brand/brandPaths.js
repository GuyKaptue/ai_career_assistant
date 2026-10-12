// Geometry for the AI Career Assistant brand mark (64 x 64 grid).
// An "A" built from two rising strokes and a crossbar, with a four-point
// spark at the upper right. It is an original mark made for this project.

export const BRAND_VIEWBOX = '0 0 64 64';
export const BRAND_RADIUS = 15;

// Default colours. They match the Claude-style design tokens used in the
// project docs (--accent, --accent-ink). Override them with CSS variables.
export const BRAND_COLORS = {
  bg: '#0f6b5c',
  fg: '#f4fbf9',
  spark: '#f3cf6f',
};

export const BRAND_A = 'M16.5 48L30 16l13.5 32';
export const BRAND_CROSSBAR = 'M23.5 38h13';
export const BRAND_SPARK =
  'M47 10c.6 4.4 2.6 6.4 7 7-4.4.6-6.4 2.6-7 7-.6-4.4-2.6-6.4-7-7 4.4-.6 6.4-2.6 7-7z';
export const BRAND_STROKE = 5;
