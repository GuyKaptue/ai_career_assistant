import React from 'react';

/**
 * Custom line-icon set for the AI Career Assistant.
 *
 * These are NOT off-the-shelf glyphs. Every domain icon (chat, CV, cover
 * letter, jobs, tracker, projects) is an original shape drawn for this product
 * so the iconography itself tells the story: career growth + AI + documents.
 *
 * All glyphs share one design language so the UI stays cohesive:
 *   · 24×24 grid, `stroke: currentColor` (theme-aware, light + dark)
 *   · round caps/joins, ~1.7–2 stroke weight, generous rounding
 * Universal affordances (plus, ×, check, chevrons…) stay instantly readable;
 * the brand marks (BrandMark / SparkIcon) are bespoke.
 */
const base = {
  viewBox: '0 0 24 24',
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 2,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
  'aria-hidden': 'true',
  focusable: 'false',
};

/** Brand mark — the eight-point spark used next to the wordmark. */
export function SparkIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} strokeWidth={2.2} {...props}>
      <path d="M12 3v18M3 12h18M5.6 5.6l12.8 12.8M18.4 5.6L5.6 18.4" />
    </svg>
  );
}

export function PlusIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} strokeWidth={2.2} {...props}>
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

export function ArrowUpIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} strokeWidth={2.4} {...props}>
      <path d="M12 19V5M5 12l7-7 7 7" />
    </svg>
  );
}

export function MenuIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} {...props}>
      <path d="M4 7h16M4 12h16M4 17h16" />
    </svg>
  );
}

export function XIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} {...props}>
      <path d="M18 6 6 18M6 6l12 12" />
    </svg>
  );
}

export function PaperclipIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} strokeWidth={1.8} {...props}>
      <path d="M21.44 11.05 12.25 20.24a6 6 0 0 1-8.49-8.49l9.19-9.19a4 4 0 0 1 5.66 5.66l-9.2 9.19a2 2 0 0 1-2.83-2.83l8.49-8.48" />
    </svg>
  );
}

export function CopyIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} strokeWidth={1.8} {...props}>
      <rect x="9" y="9" width="12" height="12" rx="2" />
      <path d="M5 15H4a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2h9a2 2 0 0 1 2 2v1" />
    </svg>
  );
}

export function CheckIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} strokeWidth={2.4} {...props}>
      <path d="M20 6 9 17l-5-5" />
    </svg>
  );
}

export function RetryIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} strokeWidth={1.8} {...props}>
      <path d="M3 12a9 9 0 1 0 2.6-6.3L3 8" />
      <path d="M3 3v5h5" />
    </svg>
  );
}

export function GearIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} strokeWidth={1.8} {...props}>
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 1 1-4 0v-.09a1.65 1.65 0 0 0-1-1.51 1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 1 1 0-4h.09a1.65 1.65 0 0 0 1.51-1 1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33h0a1.65 1.65 0 0 0 1-1.51V3a2 2 0 1 1 4 0v.09a1.65 1.65 0 0 0 1 1.51h0a1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82v0a1.65 1.65 0 0 0 1.51 1H21a2 2 0 1 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  );
}

export function SearchIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} strokeWidth={1.8} {...props}>
      <circle cx="11" cy="11" r="7" />
      <path d="m21 21-4.3-4.3" />
    </svg>
  );
}

export function MoonIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} strokeWidth={1.8} {...props}>
      <path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z" />
    </svg>
  );
}

export function SunIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} strokeWidth={1.8} {...props}>
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}

export function MonitorIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} strokeWidth={1.8} {...props}>
      <rect x="2" y="3" width="20" height="14" rx="2" />
      <path d="M8 21h8M12 17v4" />
    </svg>
  );
}

export function UserIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} strokeWidth={1.8} {...props}>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21a8 8 0 0 1 16 0" />
    </svg>
  );
}

/* --- Icons added for the Claude-style shell (same 24px / round-cap grid) --- */

/** Sidebar-panel glyph used by the collapse / open toggle. */
export function PanelLeftIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} strokeWidth={1.8} {...props}>
      <rect x="3" y="4" width="18" height="16" rx="3" />
      <path d="M9 4v16" />
    </svg>
  );
}

export function ChevronDownIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} {...props}>
      <path d="m6 9 6 6 6-6" />
    </svg>
  );
}

export function ChevronUpDownIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} {...props}>
      <path d="m7 15 5 5 5-5M7 9l5-5 5 5" />
    </svg>
  );
}

export function MessageIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} strokeWidth={1.8} {...props}>
      <path d="M21 12a8 8 0 0 1-11.6 7.1L4 20l1-4.6A8 8 0 1 1 21 12Z" />
    </svg>
  );
}

export function FileTextIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} strokeWidth={1.8} {...props}>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8l-5-5Z" />
      <path d="M14 3v5h5M9 13h6M9 17h6" />
    </svg>
  );
}

export function ClipboardCheckIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} strokeWidth={1.8} {...props}>
      <rect x="5" y="4" width="14" height="17" rx="2" />
      <path d="M9 4h6v3H9zM9 14l2 2 4-4" />
    </svg>
  );
}

export function BriefcaseIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} strokeWidth={1.8} {...props}>
      <rect x="3" y="7" width="18" height="13" rx="2" />
      <path d="M9 7V5a1 1 0 0 1 1-1h4a1 1 0 0 1 1 1v2M3 13h18" />
    </svg>
  );
}

export function KanbanIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} strokeWidth={1.8} {...props}>
      <rect x="3" y="4" width="18" height="16" rx="2" />
      <path d="M9 8v8M15 8v4" />
    </svg>
  );
}

export function FolderIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} strokeWidth={1.8} {...props}>
      <path d="M3 7a2 2 0 0 1 2-2h4l2 2h8a2 2 0 0 1 2 2v8a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V7Z" />
    </svg>
  );
}

export function GlobeIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} strokeWidth={1.8} {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18M12 3c2.5 2.7 3.8 5.7 3.8 9s-1.3 6.3-3.8 9c-2.5-2.7-3.8-5.7-3.8-9S9.5 5.7 12 3Z" />
    </svg>
  );
}

export function LogOutIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} strokeWidth={1.8} {...props}>
      <path d="M9 21H6a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h3M16 17l5-5-5-5M21 12H9" />
    </svg>
  );
}

export function LogInIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} strokeWidth={1.8} {...props}>
      <path d="M15 3h3a2 2 0 0 1 2 2v14a2 2 0 0 1-2 2h-3M10 17l5-5-5-5M15 12H3" />
    </svg>
  );
}

export function SlidersIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} strokeWidth={1.8} {...props}>
      <path d="M4 7h10M18 7h2M4 17h2M10 17h10" />
      <circle cx="16" cy="7" r="2" />
      <circle cx="8" cy="17" r="2" />
    </svg>
  );
}

export function CpuIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} strokeWidth={1.8} {...props}>
      <rect x="6" y="6" width="12" height="12" rx="2" />
      <path d="M9 2v3M15 2v3M9 19v3M15 19v3M2 9h3M2 15h3M19 9h3M19 15h3" />
    </svg>
  );
}

/* --- Status / utility icons (same 24px / round-cap grid, currentColor) --- */

/**
 * Loading / busy indicator. Intentionally a static arc; callers that need a
 * spin add it via a Tailwind `animate-spin` on the className so this stays a
 * pure, theme-aware glyph (same as the rest of the set).
 */
export function LoaderIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} strokeWidth={1.8} {...props}>
      <path d="M12 3a9 9 0 1 0 9 9" />
    </svg>
  );
}

/** Informational status glyph (circle + i). */
export function InfoIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} strokeWidth={1.8} {...props}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 11v5M12 8h.01" />
    </svg>
  );
}

/** Error / warning status glyph (triangle + bang). */
export function AlertIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} strokeWidth={1.8} {...props}>
      <path d="M10.3 4.3 2.9 17a2 2 0 0 0 1.7 3h14.8a2 2 0 0 0 1.7-3L13.7 4.3a2 2 0 0 0-3.4 0Z" />
      <path d="M12 9v4M12 17h.01" />
    </svg>
  );
}

/** "More options" affordance — three horizontal dots. */
export function EllipsisIcon({ className = '', ...props }) {
  return (
    <svg className={className} {...base} strokeWidth={2} {...props}>
      <circle cx="5" cy="12" r="1" />
      <circle cx="12" cy="12" r="1" />
      <circle cx="19" cy="12" r="1" />
    </svg>
  );
}
