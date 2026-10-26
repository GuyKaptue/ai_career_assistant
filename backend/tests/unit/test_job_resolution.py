"""Sub-step 3: chat-path job resolution (mock transports only, sockets blocked)."""

from __future__ import annotations

import io
import socket

import httpx
import pytest
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

from app.application.services import job_resolution as jr
from app.application.services import position_extraction as px

AD = """Senior Python Developer (m/w/d)
Company: Acme GmbH
Location: Berlin

Responsibilities:
- Design and build FastAPI services used by thousands of customers
- Review pull requests and mentor junior engineers on the team
- Operate services in production with Docker and Kubernetes
- Document the APIs and keep them observable with metrics

Requirements:
- Five or more years of Python in a production environment
- Strong FastAPI and PostgreSQL knowledge, REST and messaging
- Comfortable with CI/CD pipelines, Git and code review
- Excellent written and spoken English

We are looking for an experienced Python developer to build FastAPI services.
We offer a full-time position with an attractive salary, flexible hours
and a modern stack. Apply now with your CV and a short introduction.
"""

PUBLIC = lambda host: ["93.184.216.34"]  # noqa: E731 - test-only resolver to a public IP


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """No test in this feature may reach the network: block sockets outright."""

    def _blocked(*args, **kwargs):
        raise AssertionError("network access is blocked in tests")

    monkeypatch.setattr(socket, "create_connection", _blocked)
    monkeypatch.setattr(socket, "getaddrinfo", _blocked)


def _blank_pdf() -> bytes:
    buffer = io.BytesIO()
    pdf = canvas.Canvas(buffer, pagesize=A4)
    pdf.drawString(50, 800, " ")
    pdf.save()
    return buffer.getvalue()


def _transport(handler) -> httpx.MockTransport:
    return httpx.MockTransport(handler)


def test_ok_html_url():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "text/html"}, text=f"<html><body><p>{AD}</p></body></html>")

    out = jr.resolve_job_from_url("https://jobs.example/posting/1", transport=_transport(handler), resolver=PUBLIC)
    assert out.status == "ok"
    assert out.position is not None and out.position.company == "Acme GmbH"
    assert out.final_url == "https://jobs.example/posting/1"


def test_login_wall_url():
    body = AD + "\nPlease sign in to view the full description."
    out = jr.resolve_job_from_url(
        "https://jobs.example/walled",
        transport=_transport(lambda r: httpx.Response(200, text=body)),
        resolver=PUBLIC,
    )
    assert out.status == "login_wall"


def test_not_a_job_posting_text():
    out = jr.resolve_job_from_text("hello there, this is far too short")
    assert out.status == "not_a_job_posting"


def test_invalid_url_maps_to_invalid_url():
    out = jr.resolve_job_from_url(
        "http://127.0.0.1/admin",
        transport=_transport(lambda r: httpx.Response(200, text=AD)),
        resolver=PUBLIC,
    )
    assert out.status == "invalid_url"


def test_fetch_failed_on_404():
    out = jr.resolve_job_from_url(
        "https://jobs.example/gone",
        transport=_transport(lambda r: httpx.Response(404)),
        resolver=PUBLIC,
    )
    assert out.status == "fetch_failed"


def test_image_url_is_unsupported_without_ocr():
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 100
    out = jr.resolve_job_from_url(
        "https://jobs.example/logo.png",
        transport=_transport(lambda r: httpx.Response(200, content=png)),
        resolver=PUBLIC,
    )
    assert out.status == "unsupported_type"


def test_too_large_url():
    big = b"x" * (px.MAX_FETCH_BYTES + 10)
    out = jr.resolve_job_from_url(
        "https://jobs.example/big",
        transport=_transport(lambda r: httpx.Response(200, content=big)),
        resolver=PUBLIC,
    )
    assert out.status == "too_large"


def test_ok_pasted_text():
    out = jr.resolve_job_from_text(AD)
    assert out.status == "ok"
    assert out.position is not None and out.position.title is not None


def test_scanned_pdf_never_calls_tesseract(monkeypatch):
    def _boom(content: bytes) -> str:
        raise AssertionError("tesseract must never run on the chat path")

    monkeypatch.setattr(px, "tesseract_ocr", _boom)
    out = jr.resolve_job_from_url(
        "https://jobs.example/scanned.pdf",
        transport=_transport(lambda r: httpx.Response(200, content=_blank_pdf())),
        resolver=PUBLIC,
    )
    assert out.status in {"unsupported_type", "not_a_job_posting"}


BLOG = """My thoughts on remote work this year

I have been writing about focus, async standups and good coffee for months now.
This post is about habits that helped me ship side projects on weekends.
Remote teams need clear writing, shared calendars and kind code reviews.
I track my reading list, my running routes and my favourite recipes.
Thanks for reading and subscribing to the newsletter for more essays.
"""

PORTFOLIO = """Jane Roe — designer portfolio

Selected work: brand systems, landing pages and motion studies for startups.
Tools I enjoy: Figma, illustration and prototyping with small teams.
Recent clients include bakeries, bookshops and a bike repair collective.
Contact me for freelance projects, talks and workshops this spring.
"""

CV_LIKE = """John Smith
Python Developer

Summary
Backend developer with six years of experience designing, building and
operating reliable web services for product teams.

Experience
- Built internal tools at Acme Corp using Python and FastAPI
- Maintained CI pipelines, releases and automated deployments
- Wrote API documentation and mentored junior developers
- Improved query performance across several PostgreSQL databases

Education
Bachelor of Science in Computer Science, Technical University, 2018.

Skills
Python, FastAPI, PostgreSQL, Docker, Git, communication and mentoring.
"""


def test_blog_url_is_not_a_job_posting():
    out = jr.resolve_job_from_url(
        "https://blog.example/remote-work-habits",
        transport=_transport(lambda r: httpx.Response(200, text=BLOG)),
        resolver=PUBLIC,
    )
    assert out.status == "not_a_job_posting"


def test_portfolio_page_is_not_a_job_posting():
    out = jr.resolve_job_from_url(
        "https://jane.example/work",
        transport=_transport(lambda r: httpx.Response(200, text=PORTFOLIO)),
        resolver=PUBLIC,
    )
    assert out.status == "not_a_job_posting"


def test_cv_like_page_is_not_a_job_posting():
    out = jr.resolve_job_from_url(
        "https://cv.example/jane-doe",
        transport=_transport(lambda r: httpx.Response(200, text=CV_LIKE)),
        resolver=PUBLIC,
    )
    assert out.status == "not_a_job_posting"


def test_pasted_text_is_not_rejected_by_signals_only_by_length():
    """Explicitly pasted text is trusted: only too short / too long rejects it."""
    out = jr.resolve_job_from_text(CV_LIKE)
    assert out.status == "ok"
    short = jr.resolve_job_from_text("too short")
    assert short.status == "not_a_job_posting"


# --- realistic postings (A2) -------------------------------------------------

EN_POSTING = """Data Platform Engineer

What you'll do
- Build and operate our Python data platform
- Own the ingestion pipelines end to end

What we're looking for
- Five or more years of Python
- Experience with PostgreSQL and Kafka

Benefits
- Flexible hours and remote work
"""

DE_POSTING = """Data Platform Engineer

Deine Aufgaben
- Du baust und betreibst unsere Python-Datenplattform
- Du verantwortest die Ingestion-Pipelines

Dein Profil
- Mindestens fuenf Jahre Python
- Erfahrung mit PostgreSQL und Kafka

Das bieten wir
- Flexible Arbeitszeiten und Homeoffice
"""

FR_POSTING = """Data Platform Engineer

Vos missions
- Construire et exploiter notre plateforme de donnees en Python
- Responsable des pipelines d'ingestion

Ce que nous offrons
- Horaires flexibles et teletravail
- Formation continue
"""


@pytest.mark.parametrize(
    ("body", "label"),
    [(EN_POSTING, "en"), (DE_POSTING, "de"), (FR_POSTING, "fr")],
)
def test_realistic_posting_is_accepted(body: str, label: str):
    out = jr.resolve_job_from_url(
        f"https://jobs.example/{label}/platform",
        transport=_transport(lambda r: httpx.Response(200, text=body)),
        resolver=PUBLIC,
    )
    assert out.status == "ok", out.detail


def test_short_page_is_not_a_job_posting():
    out = jr.resolve_job_from_url(
        "https://jobs.example/short",
        transport=_transport(lambda r: httpx.Response(200, text="Apply now!")),
        resolver=PUBLIC,
    )
    assert out.status == "not_a_job_posting"


def test_json_ld_page_is_trusted():
    """A page with JSON-LD job markup is a job posting, whatever the prose says.

    The prose carries no job signal at all (no bullets, no section heading, no
    employment term), so only the JSON-LD markup can make this a posting.
    """
    body = (
        "<html><body>"
        '<script type="application/ld+json">'
        '{"@type":"JobPosting","title":"Data Platform Engineer",'
        '"description":"Acme GmbH is hiring a data platform engineer for our Berlin office."}'
        "</script>"
        "<p>Acme GmbH is hiring a data platform engineer for our Berlin office.</p>"
        "</body></html>"
    )
    out = jr.resolve_job_from_url(
        "https://jobs.example/ld",
        transport=_transport(lambda r: httpx.Response(200, text=body)),
        resolver=PUBLIC,
    )
    assert out.status == "ok", out.detail


def test_no_logging_of_url_content(caplog):
    with caplog.at_level("INFO", logger="app.application.services.job_resolution"):
        jr.resolve_job_from_text(AD)
        jr.resolve_job_from_url(
            "https://jobs.example/secret-path?q=token123",
            transport=_transport(lambda r: httpx.Response(200, text=AD)),
            resolver=PUBLIC,
        )
    for record in caplog.records:
        assert "secret-path" not in record.getMessage()
        assert "token123" not in record.getMessage()
        assert "Acme" not in record.getMessage()
