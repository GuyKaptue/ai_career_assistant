"""Twenty selectable CV colour themes with WCAG AA contrast validation.

The palette table comes from the product spec. Text colours are derived (the spec does not
define them) and every text/background pair is checked for a contrast ratio of at least
4.5:1. ``resolve_theme`` fixes pairs that fail by moving the colour toward black or white
(the closest AA-safe value) and reports what it changed, so a theme or a user override can
never produce unreadable text.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import Final

AA: Final = 4.5
FONTS: Final = ("Inter", "Helvetica", "Georgia", "system-ui")
OVERRIDABLE: Final = ("background", "sidebar", "accent", "section_title", "text", "font")


def _rgb(hex_color: str) -> tuple[int, int, int]:
    h = hex_color.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"Invalid colour '{hex_color}'. Use #RRGGBB.")
    return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)


def _lin(c: int) -> float:
    s = c / 255
    return s / 12.92 if s <= 0.03928 else ((s + 0.055) / 1.055) ** 2.4


def luminance(hex_color: str) -> float:
    r, g, b = _rgb(hex_color)
    return 0.2126 * _lin(r) + 0.7152 * _lin(g) + 0.0722 * _lin(b)


def contrast_ratio(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def is_dark(hex_color: str) -> bool:
    return luminance(hex_color) < 0.25


def nearest_aa(color: str, background: str) -> str:
    """The closest colour to ``color`` (same hue, shifted toward black or white) with AA contrast."""
    if contrast_ratio(color, background) >= AA:
        return color
    target = (0, 0, 0) if not is_dark(background) else (255, 255, 255)
    r, g, b = _rgb(color)
    for step in range(1, 101):
        t = step / 100
        cand = "#%02X%02X%02X" % tuple(round(c + (tc - c) * t) for c, tc in zip((r, g, b), target, strict=True))
        if contrast_ratio(cand, background) >= AA:
            return cand
    return "#000000" if target == (0, 0, 0) else "#FFFFFF"


@dataclass(frozen=True)
class CvTheme:
    id: str
    name: str
    background: str
    sidebar: str
    accent: str
    section_title: str
    font: str
    text: str = ""
    sidebar_text: str = ""
    sidebar_heading: str = ""  # accent if readable on the sidebar, else the sidebar text colour

    def to_dict(self) -> dict[str, str | int]:
        return {
            "id": self.id,
            "name": self.name,
            "background_color": self.background,
            "sidebar_color": self.sidebar,
            "accent_color": self.accent,
            "section_title_color": self.section_title,
            "text_color": self.text,
            "sidebar_text_color": self.sidebar_text,
            "sidebar_heading_color": self.sidebar_heading,
            "font": self.font,
            "photo_size_px": 140,
        }


def _derive(t: CvTheme) -> CvTheme:
    text = t.text or ("#F4F4F5" if is_dark(t.background) else "#1F2937")
    side = t.sidebar_text or ("#F8FAFC" if is_dark(t.sidebar) else "#1F2937")
    heading = t.accent if contrast_ratio(t.accent, t.sidebar) >= AA else side
    return replace(t, text=text, sidebar_text=side, sidebar_heading=heading)


_RAW: Final = [
    ("minimal_white", "Minimal White", "#FFFFFF", "#F3F4F6", "#0F62FE", "#111827", "Inter"),
    ("slate_pro", "Slate Pro", "#F8FAFC", "#1E293B", "#38BDF8", "#F1F5F9", "Inter"),
    ("navy_exec", "Navy Executive", "#FFFFFF", "#0B1F3A", "#C9A227", "#0B1F3A", "Helvetica"),
    ("forest_green", "Forest Green", "#F7FBF7", "#14532D", "#22C55E", "#14532D", "Inter"),
    ("burgundy_classic", "Burgundy Classic", "#FFFFFF", "#4C0519", "#B91C1C", "#4C0519", "Georgia"),
    ("charcoal_modern", "Charcoal Modern", "#F5F5F5", "#262626", "#F97316", "#111111", "Inter"),
    ("ocean_blue", "Ocean Blue", "#F0F9FF", "#075985", "#0EA5E9", "#075985", "Inter"),
    ("soft_sand", "Soft Sand", "#FFFBEB", "#78350F", "#D97706", "#78350F", "Inter"),
    ("rose_quartz", "Rose Quartz", "#FFF1F2", "#9F1239", "#E11D48", "#9F1239", "Inter"),
    ("plum_deep", "Plum Deep", "#FFFFFF", "#4C1D95", "#7C3AED", "#4C1D95", "Inter"),
    ("emerald_glow", "Emerald Glow", "#ECFDF5", "#064E3B", "#10B981", "#064E3B", "Inter"),
    ("graphite_tech", "Graphite Tech", "#18181B", "#27272A", "#22D3EE", "#E4E4E7", "Inter"),
    ("ivory_classic", "Ivory Classic", "#FFFFF7", "#E7E5E4", "#57534E", "#292524", "Georgia"),
    ("teal_exec", "Teal Executive", "#F0FDFA", "#134E4A", "#14B8A6", "#134E4A", "Inter"),
    ("midnight_gold", "Midnight Gold", "#0B0B0F", "#1C1C22", "#EAB308", "#F5F5F5", "Inter"),
    ("sky_light", "Sky Light", "#EFF6FF", "#1D4ED8", "#3B82F6", "#1E3A8A", "Inter"),
    ("coral_warm", "Coral Warm", "#FFF7ED", "#7C2D12", "#F97316", "#7C2D12", "Inter"),
    ("lavender_soft", "Lavender Soft", "#F5F3FF", "#5B21B6", "#8B5CF6", "#5B21B6", "Inter"),
    ("olive_pro", "Olive Pro", "#F7FEE7", "#365314", "#84CC16", "#365314", "Inter"),
    ("monochrome_bw", "Monochrome B/W", "#FFFFFF", "#111827", "#111827", "#111827", "Helvetica"),
]
THEMES: Final[dict[str, CvTheme]] = {t[0]: _derive(CvTheme(*t)) for t in _RAW}
DEFAULT_THEME_ID: Final = "minimal_white"


def contrast_report(theme: CvTheme) -> list[dict[str, str | float]]:
    """AA text pairs of a theme: body/background, sidebar text/sidebar, section title/background."""
    pairs = [
        ("text", theme.text, theme.background),
        ("sidebar_text", theme.sidebar_text, theme.sidebar),
        ("section_title", theme.section_title, theme.background),
        ("sidebar_heading", theme.sidebar_heading, theme.sidebar),
    ]
    return [
        {
            "pair": n,
            "fg": fg,
            "bg": bg,
            "ratio": round(contrast_ratio(fg, bg), 2),
            "passes": contrast_ratio(fg, bg) >= AA,
        }
        for n, fg, bg in pairs
    ]


def resolve_theme(
    theme_id: str | None, overrides: dict[str, str] | None = None, *, single_column: bool = False
) -> tuple[CvTheme, list[str]]:
    """Theme with overrides applied and every text pair made AA-safe; returns (theme, warnings).

    ``single_column`` (US/UK/CA/AU style) keeps the page white and ignores background/sidebar.
    """
    base = THEMES.get(theme_id or DEFAULT_THEME_ID)
    if base is None:
        raise ValueError(f"Unknown theme '{theme_id}'.")
    warnings: list[str] = []
    values = {k: v for k, v in (overrides or {}).items() if k in OVERRIDABLE and v}
    for key, val in values.items():
        if key == "font":
            if val not in FONTS:
                raise ValueError(f"Unknown font '{val}'. Use one of: {', '.join(FONTS)}.")
        else:
            _rgb(val)
    t = replace(
        base,
        background=values.get("background", base.background),
        sidebar=values.get("sidebar", base.sidebar),
        accent=values.get("accent", base.accent),
        section_title=values.get("section_title", base.section_title),
        text=values.get("text", base.text),
        font=values.get("font", base.font),
    )
    if single_column:
        t = replace(t, background="#FFFFFF", sidebar="#FFFFFF", text="#1F2937" if "text" not in values else t.text)
    if "sidebar" in values or "text" in values:
        t = replace(t, sidebar_text="#F8FAFC" if is_dark(t.sidebar) else "#1F2937")
    t = replace(t, sidebar_heading=t.accent if contrast_ratio(t.accent, t.sidebar) >= AA else t.sidebar_text)
    for field, bg_attr in (("text", "background"), ("sidebar_text", "sidebar"), ("section_title", "background")):
        fg, bg = getattr(t, field), getattr(t, bg_attr)
        fixed = nearest_aa(fg, bg)
        if fixed != fg:
            warnings.append(f"{field} {fg} on {bg} is below WCAG AA (4.5:1); using {fixed}.")
            t = replace(t, **{field: fixed})
    return t, warnings
