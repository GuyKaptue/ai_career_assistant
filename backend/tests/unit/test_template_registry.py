from app.application.services.document_generation import generate_document_content
from app.domain.templates.template_registry import TemplateRegistry


def test_template_registry_has_supported_templates():
    registry = TemplateRegistry()
    templates = registry.list_templates("cv")

    assert templates
    assert {template.id for template in templates} >= {"professional", "modern"}
    assert all(template.document_type == "cv" for template in templates)


def test_template_registry_has_12_plus_cv_templates():
    registry = TemplateRegistry()
    cv_templates = registry.list_templates("cv")
    assert len(cv_templates) >= 12


def test_template_registry_has_multiple_cover_letter_templates():
    registry = TemplateRegistry()
    letter_templates = registry.list_templates("cover_letter")
    assert len(letter_templates) >= 6


def test_template_registry_has_resignation_template():
    registry = TemplateRegistry()
    resignation_templates = registry.list_templates("resignation")
    assert len(resignation_templates) >= 1


def test_template_registry_total_count():
    registry = TemplateRegistry()
    all_templates = registry.list_templates()
    assert len(all_templates) >= 19


def test_template_registry_unique_ids():
    registry = TemplateRegistry()
    all_templates = registry.list_templates()
    ids = [template.id for template in all_templates]
    assert len(ids) == len(set(ids))


def test_template_registry_all_have_locales():
    registry = TemplateRegistry()
    all_templates = registry.list_templates()
    for template in all_templates:
        assert template.supported_locales
        assert "en" in template.supported_locales


def test_template_registry_get_by_type():
    registry = TemplateRegistry()
    template = registry.get("professional", "cv")
    assert template is not None
    assert template.id == "professional"

    # Wrong type returns None
    assert registry.get("professional", "cover_letter") is None


def test_template_registry_validate():
    registry = TemplateRegistry()
    assert registry.validate("professional", "cv")
    assert not registry.validate("nonexistent", "cv")
    assert not registry.validate("professional", "resignation")


def test_document_generation_uses_selected_template():
    payload = {
        "name": "John Doe",
        "target_role": "Data Analyst",
        "summary": "Analyst with experience in analytics and reporting.",
        "experience": [{"role": "Analyst", "company": "Northwind", "highlights": ["Built dashboards"]}],
        "education": [{"school": "University of London", "degree": "BSc Computer Science"}],
        "skills": ["Python", "SQL"],
    }

    result = generate_document_content(payload, template_id="professional")

    assert result["template_id"] == "professional"
    assert result["document_type"] == "cv"
    assert "John Doe" in result["content"]
    assert "Data Analyst" in result["content"]
