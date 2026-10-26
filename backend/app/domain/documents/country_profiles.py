"""Country-specific CV and cover-letter conventions, resolved in code.

The format is decided here, never by the language model: layout, photo policy, section
order and cover-letter shape come from a table keyed by the employer's country. Where
the original brief and current German practice differ (photo, date of birth and signature
are customary but not required under the AGG), the table uses ``optional`` and keeps
those fields off by default; each is one value to change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final, Literal

Layout = Literal["two_column", "hybrid", "single_column"]
Policy = Literal["required", "recommended", "optional", "forbidden"]


@dataclass(frozen=True)
class CountryProfile:
    id: str
    countries: tuple[str, ...]
    layout: Layout
    photo: Policy
    date_of_birth: Policy
    signature: Policy
    cover_letter: Policy
    cover_paragraphs: str
    paper: str
    pages: str
    sections: tuple[str, ...]  # canonical keys, localised at render time
    language: str
    notes: str

    def to_dict(self, country: str | None = None) -> dict:
        return {
            "profile_id": self.id,
            "target_country": country,
            "cv_layout": self.layout,
            "photo_policy": self.photo,
            "date_of_birth_policy": self.date_of_birth,
            "signature_policy": self.signature,
            "cover_letter": self.cover_letter,
            "cover_letter_length": self.cover_paragraphs,
            "paper_size": self.paper,
            "page_count_recommended": self.pages,
            "section_order": list(self.sections),
            "language": self.language,
            "format_notes": self.notes,
        }


_EU = ("summary", "projects", "experience", "education", "certifications", "languages")
PROFILES: Final[tuple[CountryProfile, ...]] = (
    CountryProfile(
        "DACH",
        ("DE", "AT", "CH"),
        "two_column",
        "optional",
        "optional",
        "optional",
        "required",
        "5 paragraphs, 300-400 words",
        "A4",
        "2",
        _EU,
        "de",
        "Tabular CV; photo, date of birth and signature are customary but optional (AGG). Formal 'Sie' cover letter.",
    ),
    CountryProfile(
        "FR",
        ("FR", "LU", "MC"),
        "two_column",
        "recommended",
        "optional",
        "forbidden",
        "required",
        "4 paragraphs",
        "A4",
        "1",
        ("summary", "experience", "education", "skills", "languages"),
        "fr",
        "Lettre de motivation required; 'Objet : Candidature au poste de ...'.",
    ),
    CountryProfile(
        "SOUTH_EU",
        ("ES", "IT", "PT", "GR"),
        "two_column",
        "recommended",
        "optional",
        "forbidden",
        "required",
        "4 paragraphs",
        "A4",
        "1-2",
        ("summary", "experience", "education", "skills", "languages"),
        "match",
        "Two-column CV, formal cover letter.",
    ),
    CountryProfile(
        "NORDIC",
        ("SE", "NO", "DK", "FI", "IS"),
        "hybrid",
        "optional",
        "forbidden",
        "forbidden",
        "optional",
        "3 short paragraphs",
        "A4",
        "1-2",
        ("summary", "experience", "education", "skills", "languages"),
        "match",
        "Single column with optional narrow skills column.",
    ),
    CountryProfile(
        "NL_BE",
        ("NL",),
        "hybrid",
        "optional",
        "forbidden",
        "forbidden",
        "required",
        "3 paragraphs, direct tone",
        "A4",
        "1-2",
        ("summary", "experience", "education", "skills", "languages"),
        "match",
        "Hybrid layout, direct tone.",
    ),
    CountryProfile(
        "UK_IE",
        ("GB", "UK", "IE"),
        "single_column",
        "forbidden",
        "forbidden",
        "forbidden",
        "required",
        "3 paragraphs, 200-300 words",
        "A4",
        "1-2",
        ("summary", "experience", "education", "skills", "certifications"),
        "en",
        "Single column, British spelling, no photo, no personal data.",
    ),
    CountryProfile(
        "US_CA_AU",
        ("US", "CA", "AU", "NZ"),
        "single_column",
        "forbidden",
        "forbidden",
        "forbidden",
        "optional",
        "3 paragraphs, 200-300 words",
        "Letter",
        "1",
        ("summary", "experience", "education", "skills", "certifications"),
        "en",
        "Single column; photo and personal data removed (anti-discrimination practice).",
    ),
)
DEFAULT_PROFILE: Final = CountryProfile(
    "DEFAULT",
    (),
    "single_column",
    "forbidden",
    "forbidden",
    "forbidden",
    "optional",
    "3 paragraphs",
    "A4",
    "1-2",
    ("summary", "experience", "education", "skills", "languages"),
    "match",
    "Neutral single-column format.",
)
_NO_LETTER_PAPER: Final = {"AU": "A4", "NZ": "A4"}
# BE and CH are bilingual: the employer's language decides, so the caller passes ``language``.
_BE_BY_LANGUAGE: Final = {"nl": "NL_BE", "fr": "FR"}

SECTION_LABELS: Final[dict[str, dict[str, str]]] = {
    "summary": {"en": "Summary", "de": "Zusammenfassung", "fr": "Profil"},
    "projects": {"en": "Projects", "de": "Projekte", "fr": "Projets"},
    "experience": {"en": "Experience", "de": "Berufserfahrung", "fr": "Expérience"},
    "education": {"en": "Education", "de": "Bildung", "fr": "Formation"},
    "skills": {"en": "Skills", "de": "Kenntnisse", "fr": "Compétences"},
    "certifications": {"en": "Certifications", "de": "Zertifikate", "fr": "Certifications"},
    "languages": {"en": "Languages", "de": "Sprachen", "fr": "Langues"},
}


def profile_for_country(country: str | None, language: str | None = None) -> CountryProfile:
    code = (country or "").strip().upper()
    if code == "BE":
        return next(p for p in PROFILES if p.id == _BE_BY_LANGUAGE.get((language or "nl").lower(), "NL_BE"))
    for profile in PROFILES:
        if code in profile.countries:
            return profile
    return DEFAULT_PROFILE


def paper_for(country: str | None, profile: CountryProfile) -> str:
    return _NO_LETTER_PAPER.get((country or "").upper(), profile.paper)


def section_labels(profile: CountryProfile, locale: str) -> list[str]:
    return [SECTION_LABELS[k].get(locale, SECTION_LABELS[k]["en"]) for k in profile.sections]


def apply_photo_policy(profile: CountryProfile, has_photo: bool) -> tuple[bool, list[str]]:
    """Whether a photo may be shown, plus a caveat when one is removed."""
    if profile.photo == "forbidden":
        caveat = ["A photo was removed: it is not used on CVs for this country (anti-discrimination practice)."]
        return False, caveat if has_photo else []
    return has_photo, []
