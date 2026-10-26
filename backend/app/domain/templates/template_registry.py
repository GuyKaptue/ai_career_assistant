from dataclasses import dataclass, field
from typing import Any, Iterable


@dataclass(frozen=True)
class TemplateDefinition:
    id: str
    name: str
    document_type: str
    description: str
    active: bool = True
    supported_locales: tuple[str, ...] = ("en",)
    metadata: dict[str, Any] = field(default_factory=dict)


class TemplateRegistry:
    """Registry for selecting document templates without hard-coding rendering logic."""

    def __init__(self, templates: Iterable[TemplateDefinition] | None = None) -> None:
        self._templates: dict[str, TemplateDefinition] = {}
        for template in templates or self._default_templates():
            self.register(template)

    @staticmethod
    def _default_templates() -> list[TemplateDefinition]:
        return [
            # --- CV templates (12) ---
            TemplateDefinition(
                id="professional",
                name="Professional",
                document_type="cv",
                description="Structured, ATS-friendly format for broad job applications.",
                supported_locales=("en", "fr", "de"),
                metadata={"color_scheme": "blue", "layout": "classic"},
            ),
            TemplateDefinition(
                id="modern",
                name="Modern",
                document_type="cv",
                description="Clean editorial layout for modern product and consulting roles.",
                supported_locales=("en", "es", "nl"),
                metadata={"color_scheme": "slate", "layout": "modern"},
            ),
            TemplateDefinition(
                id="executive",
                name="Executive",
                document_type="cv",
                description="High-clarity layout designed for senior leadership and strategic positions.",
                supported_locales=("en",),
                metadata={"color_scheme": "dark", "layout": "executive"},
            ),
            TemplateDefinition(
                id="minimal",
                name="Minimal",
                document_type="cv",
                description="Low-noise format prioritizing readability and content density.",
                supported_locales=("en",),
                metadata={"color_scheme": "neutral", "layout": "minimal"},
            ),
            TemplateDefinition(
                id="academic",
                name="Academic",
                document_type="cv",
                description="Publication- and research-focused layout for academic and R&D roles.",
                supported_locales=("en", "de", "fr"),
                metadata={"color_scheme": "maroon", "layout": "academic"},
            ),
            TemplateDefinition(
                id="technical",
                name="Technical",
                document_type="cv",
                description="Skills-first layout for engineering and data roles.",
                supported_locales=("en", "de"),
                metadata={"color_scheme": "teal", "layout": "technical"},
            ),
            TemplateDefinition(
                id="creative",
                name="Creative",
                document_type="cv",
                description="Visual layout for design, marketing, and media roles.",
                supported_locales=("en", "es", "fr"),
                metadata={"color_scheme": "coral", "layout": "creative"},
            ),
            TemplateDefinition(
                id="timeline",
                name="Timeline",
                document_type="cv",
                description="Chronological layout emphasizing career progression.",
                supported_locales=("en", "de", "nl"),
                metadata={"color_scheme": "indigo", "layout": "timeline"},
            ),
            TemplateDefinition(
                id="skills-based",
                name="Skills-Based",
                document_type="cv",
                description="Functional layout grouping skills over chronological history.",
                supported_locales=("en", "fr"),
                metadata={"color_scheme": "olive", "layout": "functional"},
            ),
            TemplateDefinition(
                id="international",
                name="International",
                document_type="cv",
                description="Neutral layout for cross-border and multilingual applications.",
                supported_locales=("en", "de", "fr", "es", "nl"),
                metadata={"color_scheme": "steel", "layout": "international"},
            ),
            TemplateDefinition(
                id="startup",
                name="Startup",
                document_type="cv",
                description="Compact, impact-focused layout for fast-moving teams.",
                supported_locales=("en",),
                metadata={"color_scheme": "orange", "layout": "startup"},
            ),
            TemplateDefinition(
                id="corporate",
                name="Corporate",
                document_type="cv",
                description="Formal layout for finance, legal, and enterprise roles.",
                supported_locales=("en", "de", "fr"),
                metadata={"color_scheme": "charcoal", "layout": "corporate"},
            ),
            # --- Two-column CV templates (18): sidebar left/right, selectable width and banner ---
            TemplateDefinition(
                id="sidebar-left-navy",
                name="Navy Sidebar (Left)",
                document_type="cv",
                description="Executive two-column CV with a navy left sidebar and gold accents.",
                supported_locales=("en", "de", "fr"),
                metadata={
                    "layout": "sidebar",
                    "color_scheme": "navy",
                    "columns": 2,
                    "sidebar": "left",
                    "sidebar_pct": 32,
                    "theme_id": "navy_exec",
                    "heading": "rule",
                    "top_band": False,
                },
            ),
            TemplateDefinition(
                id="sidebar-right-blue",
                name="Blue Sidebar (Right)",
                document_type="cv",
                description="Two-column CV with a bright blue right sidebar for skills and certificates.",
                supported_locales=("en", "de", "fr"),
                metadata={
                    "layout": "sidebar",
                    "color_scheme": "blue",
                    "columns": 2,
                    "sidebar": "right",
                    "sidebar_pct": 32,
                    "theme_id": "sky_light",
                    "heading": "rule",
                    "top_band": False,
                },
            ),
            TemplateDefinition(
                id="sidebar-left-forest",
                name="Forest Sidebar (Left)",
                document_type="cv",
                description="Calm green left sidebar with marker-style section headings.",
                supported_locales=("en", "de", "fr"),
                metadata={
                    "layout": "sidebar",
                    "color_scheme": "olive",
                    "columns": 2,
                    "sidebar": "left",
                    "sidebar_pct": 32,
                    "theme_id": "forest_green",
                    "heading": "bar",
                    "top_band": False,
                },
            ),
            TemplateDefinition(
                id="sidebar-right-burgundy",
                name="Burgundy Classic (Right)",
                document_type="cv",
                description="Serif two-column CV with a burgundy right sidebar.",
                supported_locales=("en", "de", "fr"),
                metadata={
                    "layout": "sidebar",
                    "color_scheme": "maroon",
                    "columns": 2,
                    "sidebar": "right",
                    "sidebar_pct": 32,
                    "theme_id": "burgundy_classic",
                    "heading": "rule",
                    "top_band": False,
                },
            ),
            TemplateDefinition(
                id="sidebar-left-charcoal",
                name="Charcoal Modern (Left)",
                document_type="cv",
                description="Dark charcoal sidebar with an orange accent.",
                supported_locales=("en", "de", "fr"),
                metadata={
                    "layout": "sidebar",
                    "color_scheme": "charcoal",
                    "columns": 2,
                    "sidebar": "left",
                    "sidebar_pct": 32,
                    "theme_id": "charcoal_modern",
                    "heading": "caps",
                    "top_band": False,
                },
            ),
            TemplateDefinition(
                id="sidebar-right-teal",
                name="Teal Executive (Right)",
                document_type="cv",
                description="Teal right sidebar for leadership and consulting profiles.",
                supported_locales=("en", "de", "fr"),
                metadata={
                    "layout": "sidebar",
                    "color_scheme": "teal",
                    "columns": 2,
                    "sidebar": "right",
                    "sidebar_pct": 32,
                    "theme_id": "teal_exec",
                    "heading": "bar",
                    "top_band": False,
                },
            ),
            TemplateDefinition(
                id="sidebar-left-narrow",
                name="Light Narrow Sidebar",
                document_type="cv",
                description="Slim light-grey sidebar that maximises space for experience.",
                supported_locales=("en", "de", "fr"),
                metadata={
                    "layout": "sidebar",
                    "color_scheme": "neutral",
                    "columns": 2,
                    "sidebar": "left",
                    "sidebar_pct": 25,
                    "theme_id": "minimal_white",
                    "heading": "rule",
                    "top_band": False,
                },
            ),
            TemplateDefinition(
                id="sidebar-right-wide",
                name="Plum Wide Sidebar (Right)",
                document_type="cv",
                description="Wide plum right sidebar for skill-heavy profiles.",
                supported_locales=("en", "de", "fr"),
                metadata={
                    "layout": "sidebar",
                    "color_scheme": "indigo",
                    "columns": 2,
                    "sidebar": "right",
                    "sidebar_pct": 38,
                    "theme_id": "plum_deep",
                    "heading": "bar",
                    "top_band": False,
                },
            ),
            TemplateDefinition(
                id="banner-left-ocean",
                name="Ocean Banner (Left)",
                document_type="cv",
                description="Full-width name banner with a left sidebar below.",
                supported_locales=("en", "de", "fr"),
                metadata={
                    "layout": "sidebar",
                    "color_scheme": "blue",
                    "columns": 2,
                    "sidebar": "left",
                    "sidebar_pct": 32,
                    "theme_id": "ocean_blue",
                    "heading": "rule",
                    "top_band": True,
                },
            ),
            TemplateDefinition(
                id="banner-right-coral",
                name="Coral Banner (Right)",
                document_type="cv",
                description="Full-width coral banner with a right sidebar below.",
                supported_locales=("en", "de", "fr"),
                metadata={
                    "layout": "sidebar",
                    "color_scheme": "coral",
                    "columns": 2,
                    "sidebar": "right",
                    "sidebar_pct": 32,
                    "theme_id": "coral_warm",
                    "heading": "bar",
                    "top_band": True,
                },
            ),
            TemplateDefinition(
                id="dark-left-graphite",
                name="Graphite Dark (Left)",
                document_type="cv",
                description="Dark-mode two-column CV for engineering and data roles.",
                supported_locales=("en", "de", "fr"),
                metadata={
                    "layout": "sidebar",
                    "color_scheme": "dark",
                    "columns": 2,
                    "sidebar": "left",
                    "sidebar_pct": 32,
                    "theme_id": "graphite_tech",
                    "heading": "caps",
                    "top_band": False,
                },
            ),
            TemplateDefinition(
                id="dark-right-midnight",
                name="Midnight Gold (Right)",
                document_type="cv",
                description="Black and gold right-sidebar CV for premium positioning.",
                supported_locales=("en", "de", "fr"),
                metadata={
                    "layout": "sidebar",
                    "color_scheme": "dark",
                    "columns": 2,
                    "sidebar": "right",
                    "sidebar_pct": 32,
                    "theme_id": "midnight_gold",
                    "heading": "rule",
                    "top_band": False,
                },
            ),
            TemplateDefinition(
                id="soft-left-lavender",
                name="Lavender Soft (Left)",
                document_type="cv",
                description="Soft violet left sidebar for design and product roles.",
                supported_locales=("en", "de", "fr"),
                metadata={
                    "layout": "sidebar",
                    "color_scheme": "violet",
                    "columns": 2,
                    "sidebar": "left",
                    "sidebar_pct": 32,
                    "theme_id": "lavender_soft",
                    "heading": "bar",
                    "top_band": False,
                },
            ),
            TemplateDefinition(
                id="sand-right-warm",
                name="Warm Sand (Right)",
                document_type="cv",
                description="Warm sand and brown right sidebar with an amber accent.",
                supported_locales=("en", "de", "fr"),
                metadata={
                    "layout": "sidebar",
                    "color_scheme": "amber",
                    "columns": 2,
                    "sidebar": "right",
                    "sidebar_pct": 32,
                    "theme_id": "soft_sand",
                    "heading": "rule",
                    "top_band": False,
                },
            ),
            TemplateDefinition(
                id="emerald-left",
                name="Emerald Sidebar (Left)",
                document_type="cv",
                description="Fresh emerald left sidebar for health and sustainability roles.",
                supported_locales=("en", "de", "fr"),
                metadata={
                    "layout": "sidebar",
                    "color_scheme": "teal",
                    "columns": 2,
                    "sidebar": "left",
                    "sidebar_pct": 30,
                    "theme_id": "emerald_glow",
                    "heading": "rule",
                    "top_band": False,
                },
            ),
            TemplateDefinition(
                id="rose-right",
                name="Rose Quartz (Right)",
                document_type="cv",
                description="Rose right sidebar for marketing and communications.",
                supported_locales=("en", "de", "fr"),
                metadata={
                    "layout": "sidebar",
                    "color_scheme": "coral",
                    "columns": 2,
                    "sidebar": "right",
                    "sidebar_pct": 32,
                    "theme_id": "rose_quartz",
                    "heading": "bar",
                    "top_band": False,
                },
            ),
            TemplateDefinition(
                id="olive-left-compact",
                name="Olive Compact (Left)",
                document_type="cv",
                description="Compact olive sidebar layout for dense, one-page CVs.",
                supported_locales=("en", "de", "fr"),
                metadata={
                    "layout": "sidebar",
                    "color_scheme": "olive",
                    "columns": 2,
                    "sidebar": "left",
                    "sidebar_pct": 28,
                    "theme_id": "olive_pro",
                    "heading": "plain",
                    "top_band": False,
                },
            ),
            TemplateDefinition(
                id="ivory-right-serif",
                name="Ivory Serif (Right)",
                document_type="cv",
                description="Quiet serif two-column CV on ivory with a stone sidebar.",
                supported_locales=("en", "de", "fr"),
                metadata={
                    "layout": "sidebar",
                    "color_scheme": "gray",
                    "columns": 2,
                    "sidebar": "right",
                    "sidebar_pct": 30,
                    "theme_id": "ivory_classic",
                    "heading": "rule",
                    "top_band": False,
                },
            ),
            # --- Cover letter templates (6) ---
            TemplateDefinition(
                id="formal-german-din5008",
                name="Formal German DIN 5008",
                document_type="cover_letter",
                description=(
                    "Structured formal German business letter "
                    "(sender, recipient, date, subject, salutation, "
                    "body, closing)."
                ),
                supported_locales=("de", "en", "fr"),
                metadata={"color_scheme": "navy", "layout": "din5008"},
            ),
            TemplateDefinition(
                id="classic-letter",
                name="Classic Letter",
                document_type="cover_letter",
                description="A refined, professional letter structure for formal applications.",
                supported_locales=("en", "fr", "de"),
                metadata={"color_scheme": "ivory", "layout": "formal"},
            ),
            TemplateDefinition(
                id="warm-letter",
                name="Warm Letter",
                document_type="cover_letter",
                description="A personable, enthusiastic tone for team-oriented cultures.",
                supported_locales=("en", "fr", "es"),
                metadata={"color_scheme": "amber", "layout": "warm"},
            ),
            TemplateDefinition(
                id="brief-letter",
                name="Brief Letter",
                document_type="cover_letter",
                description="A concise, three-paragraph letter for high-volume applications.",
                supported_locales=("en", "de"),
                metadata={"color_scheme": "gray", "layout": "brief"},
            ),
            TemplateDefinition(
                id="creative-letter",
                name="Creative Letter",
                document_type="cover_letter",
                description="A narrative-driven letter for creative and marketing roles.",
                supported_locales=("en", "es", "fr"),
                metadata={"color_scheme": "violet", "layout": "creative"},
            ),
            TemplateDefinition(
                id="technical-letter",
                name="Technical Letter",
                document_type="cover_letter",
                description="A structured letter emphasizing technical scope and impact.",
                supported_locales=("en", "de"),
                metadata={"color_scheme": "cyan", "layout": "technical"},
            ),
            # --- Additional cover letter designs (4) ---
            TemplateDefinition(
                id="letterhead-band",
                name="Letterhead Band",
                document_type="cover_letter",
                description="Letter with a coloured letterhead band carrying the sender name.",
                supported_locales=("en", "de", "fr"),
                metadata={"color_scheme": "navy", "layout": "letterhead"},
            ),
            TemplateDefinition(
                id="centered-serif-letter",
                name="Centered Serif Letter",
                document_type="cover_letter",
                description="Centered serif letterhead with a rule, traditional and formal.",
                supported_locales=("en", "de", "fr"),
                metadata={"color_scheme": "maroon", "layout": "centered"},
            ),
            TemplateDefinition(
                id="modern-letter",
                name="Modern Letter",
                document_type="cover_letter",
                description="Clean sans-serif letter with an accent-coloured name.",
                supported_locales=("en", "de", "fr"),
                metadata={"color_scheme": "teal", "layout": "modern-letter"},
            ),
            TemplateDefinition(
                id="executive-letter",
                name="Executive Letter",
                document_type="cover_letter",
                description="Dark executive banner with a serif body for senior roles.",
                supported_locales=("en", "de", "fr"),
                metadata={"color_scheme": "charcoal", "layout": "executive-letter"},
            ),
            # --- Resignation templates (1) ---
            TemplateDefinition(
                id="formal-resignation",
                name="Formal Resignation",
                document_type="resignation",
                description="A concise, respectful letter for formal notice and transition.",
                supported_locales=("en", "fr", "de"),
                metadata={"color_scheme": "neutral", "layout": "formal"},
            ),
        ]

    def register(self, template: TemplateDefinition) -> TemplateDefinition:
        self._templates[template.id] = template
        return template

    def get(self, template_id: str, document_type: str | None = None) -> TemplateDefinition | None:
        template = self._templates.get(template_id)
        if template is None:
            return None
        if document_type and template.document_type != document_type:
            return None
        return template

    def list_templates(self, document_type: str | None = None) -> list[TemplateDefinition]:
        templates = list(self._templates.values())
        if document_type is not None:
            templates = [template for template in templates if template.document_type == document_type]
        return sorted(templates, key=lambda item: item.name)

    def supports(self, template_id: str, document_type: str) -> bool:
        template = self.get(template_id, document_type)
        return template is not None and template.active

    def validate(self, template_id: str, document_type: str) -> bool:
        return self.supports(template_id, document_type)
