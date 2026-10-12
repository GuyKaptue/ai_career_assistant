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
