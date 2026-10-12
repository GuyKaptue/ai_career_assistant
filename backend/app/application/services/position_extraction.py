"""Extract a job position from URL, pasted text, PDF, DOCX, image or ZIP.

Design rules
------------
* **Never invent data.** Fields that cannot be found stay ``None`` and a
  warning is recorded.
* **Trust bytes, not names.** File types are detected from magic bytes; the
  client's file name / content type is only a hint.
* **Bounded work.** Every input is size-limited; archives are limited in entry
  count, member size, total size and compression ratio (zip-bomb guard);
  nothing is ever written to disk or executed.
* **SSRF-safe fetching.** Only public http(s) hosts; every resolved address
  must be a global IP; redirects are re-validated hop by hop; the connection is
  pinned to the validated IP (TLS still verifies the *original* host name via
  SNI), which closes the DNS-rebinding window.
* **No new Python dependencies.** HTML is parsed with the standard library; OCR
  uses the ``tesseract`` command-line tool when it is installed and otherwise
  reports a clear configuration error.
"""

from __future__ import annotations

import io
import ipaddress
import json
import re
import shutil
import socket
import subprocess  # nosec B404 - used only for the fixed `tesseract` OCR command below
import zipfile
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from html import unescape
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit

import httpx

from app.core.errors import ConfigurationError, ExternalServiceError, ValidationError
from app.domain.positions.models import Position

MAX_UPLOAD_BYTES = 5 * 1024 * 1024
MAX_FETCH_BYTES = 2 * 1024 * 1024
MAX_TEXT_CHARS = 60_000
MIN_TEXT_CHARS = 40
MAX_PDF_PAGES = 30
MAX_IMAGE_PIXELS = 25_000_000
MAX_ZIP_ENTRIES = 25
MAX_ZIP_MEMBER_BYTES = 5 * 1024 * 1024
MAX_ZIP_TOTAL_BYTES = 20 * 1024 * 1024
MAX_ZIP_RATIO = 100
MAX_REDIRECTS = 3
FETCH_TIMEOUT_SECONDS = 10.0
OCR_TIMEOUT_SECONDS = 30
USER_AGENT = "AICareerAssistant/1.0 (+job position import)"

Resolver = Callable[[str], list[str]]
OcrEngine = Callable[[bytes], str]


@dataclass
class ExtractionResult:
    positions: list[Position] = field(default_factory=list)
    skipped: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "positions": [position.to_dict() for position in self.positions],
            "skipped": self.skipped,
            "count": len(self.positions),
        }


# --------------------------------------------------------------------------- #
# Type detection
# --------------------------------------------------------------------------- #
def detect_kind(content: bytes) -> str:
    """Return pdf | docx | zip | png | jpeg | webp | html | text from the bytes."""
    head = content[:16]
    if head.startswith(b"%PDF"):
        return "pdf"
    if head.startswith(b"PK\x03\x04") or head.startswith(b"PK\x05\x06"):
        return "docx" if _zip_has(content, "word/document.xml") else "zip"
    if head.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if head.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if head[:4] == b"RIFF" and content[8:12] == b"WEBP":
        return "webp"
    sample = content[:2048].lstrip().lower()
    if sample.startswith((b"<!doctype html", b"<html", b"<head", b"<body", b"<?xml")) or b"<html" in sample:
        return "html"
    if head.startswith((b"\xff\xfe", b"\xfe\xff")):
        return "text"  # UTF-16 with BOM legitimately contains NUL bytes
    if b"\x00" in content[:4096]:
        raise ValidationError("Unsupported file type. Use PDF, DOCX, an image (PNG/JPEG/WEBP), ZIP, HTML or text.")
    return "text"


def _zip_has(content: bytes, name: str) -> bool:
    try:
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            return name in archive.namelist()
    except zipfile.BadZipFile:
        return False


# --------------------------------------------------------------------------- #
# Text extraction per format
# --------------------------------------------------------------------------- #
def _decode(content: bytes) -> str:
    """UTF-8 (with/without BOM), UTF-16 only when a BOM says so, else Windows-1252.

    Trying UTF-16 blindly would "succeed" on any even-length byte string and
    turn legacy-encoded German text into garbage.
    """
    if content.startswith((b"\xff\xfe", b"\xfe\xff")):
        try:
            return content.decode("utf-16")
        except UnicodeError:
            pass
    try:
        return content.decode("utf-8-sig")
    except UnicodeError:
        return content.decode("cp1252", errors="replace")


def _guard_zip_container(content: bytes) -> zipfile.ZipFile:
    """Open an OOXML/ZIP container after bounding its size and ratio."""
    try:
        archive = zipfile.ZipFile(io.BytesIO(content))
    except zipfile.BadZipFile as exc:
        raise ValidationError("The archive is corrupted or not a valid ZIP/DOCX file.") from exc
    infos = archive.infolist()
    if len(infos) > MAX_ZIP_ENTRIES * 40:
        raise ValidationError("The archive contains too many entries.")
    total = sum(info.file_size for info in infos)
    if total > MAX_ZIP_TOTAL_BYTES:
        raise ValidationError("The archive expands to more than the allowed size.")
    compressed = max(1, sum(info.compress_size for info in infos))
    if total / compressed > MAX_ZIP_RATIO and total > 1024 * 1024:
        raise ValidationError("The archive's compression ratio is suspicious (possible zip bomb).")
    return archive


def text_from_pdf(content: bytes) -> str:
    from pypdf import PdfReader
    from pypdf.errors import PyPdfError

    try:
        reader = PdfReader(io.BytesIO(content))
        if reader.is_encrypted:
            raise ValidationError("Encrypted PDFs are not supported.")
        pages = reader.pages[:MAX_PDF_PAGES]
        return "\n".join((page.extract_text() or "") for page in pages)
    except ValidationError:
        raise
    except (PyPdfError, ValueError, KeyError, OSError) as exc:
        raise ValidationError("The PDF could not be read.") from exc


def text_from_docx(content: bytes) -> str:
    from docx import Document

    _guard_zip_container(content).close()
    try:
        document = Document(io.BytesIO(content))
    except Exception as exc:  # python-docx raises several unrelated types for bad files
        raise ValidationError("The DOCX file could not be read.") from exc
    lines = [paragraph.text for paragraph in document.paragraphs]
    for table in document.tables:
        for row in table.rows:
            cells = [cell.text.strip() for cell in row.cells if cell.text.strip()]
            if cells:
                lines.append(" | ".join(cells))
    return "\n".join(lines)


def _tesseract_languages() -> str:
    """Best installed subset of English/German/French, never an unavailable pack."""
    binary = shutil.which("tesseract")
    if binary is None:
        raise ConfigurationError("Image import needs OCR: install the `tesseract` command-line tool.")
    try:
        listing = subprocess.run(  # nosec B603 - fixed argv, no shell, binary resolved via shutil.which
            [binary, "--list-langs"], capture_output=True, timeout=10, check=False
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ConfigurationError("The OCR engine could not be started.") from exc
    installed = set(listing.stdout.decode("utf-8", "replace").split())
    wanted = [code for code in ("deu", "eng", "fra") if code in installed]
    return "+".join(wanted) if wanted else "eng"


def tesseract_ocr(image_bytes: bytes) -> str:
    """Default OCR engine: the ``tesseract`` CLI reading the image from stdin."""
    binary = shutil.which("tesseract")
    if binary is None:
        raise ConfigurationError("Image import needs OCR: install the `tesseract` command-line tool.")
    languages = _tesseract_languages()
    try:
        completed = subprocess.run(  # nosec B603 - fixed argv, no shell, image passed via stdin only
            [binary, "stdin", "stdout", "-l", languages],
            input=image_bytes,
            capture_output=True,
            timeout=OCR_TIMEOUT_SECONDS,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ExternalServiceError("Reading the image took too long.", internal="tesseract timeout") from exc
    except (OSError, subprocess.SubprocessError) as exc:
        raise ConfigurationError("The OCR engine could not be started.") from exc
    if completed.returncode != 0:
        raise ValidationError("The image could not be read as text.")
    return completed.stdout.decode("utf-8", "replace")


def text_from_image(content: bytes, ocr: OcrEngine | None = None) -> str:
    from PIL import Image, UnidentifiedImageError

    try:
        with Image.open(io.BytesIO(content)) as image:
            width, height = image.size
            image.verify()
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError) as exc:
        raise ValidationError("The image file is corrupted or unsupported.") from exc
    if width * height > MAX_IMAGE_PIXELS:
        raise ValidationError("The image resolution is too large.")
    return (ocr or tesseract_ocr)(content)


# --------------------------------------------------------------------------- #
# HTML
# --------------------------------------------------------------------------- #
_SKIP_TAGS = {"script", "style", "noscript", "svg", "nav", "footer", "header", "aside", "form", "iframe", "template"}
_BLOCK_TAGS = {
    "p",
    "div",
    "br",
    "li",
    "ul",
    "ol",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "tr",
    "section",
    "article",
    "table",
}


class _HtmlText(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self._skip = 0
        self._in_title = False
        self.title = ""
        self.parts: list[str] = []
        self.json_ld: list[str] = []
        self.meta: dict[str, str] = {}
        self._capture_ld = False
        self._ld_buffer: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {key: (value or "") for key, value in attrs}
        if tag == "script" and values.get("type", "").lower() == "application/ld+json":
            self._capture_ld = True
            self._ld_buffer = []
            return
        if tag == "meta":
            key = (values.get("property") or values.get("name") or "").lower()
            if key and values.get("content"):
                self.meta.setdefault(key, values["content"])
        if tag == "title":
            self._in_title = True
        if tag in _SKIP_TAGS:
            self._skip += 1
        if tag in _BLOCK_TAGS and not self._skip:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self._capture_ld:
            self._capture_ld = False
            self.json_ld.append("".join(self._ld_buffer))
            return
        if tag == "title":
            self._in_title = False
        if tag in _SKIP_TAGS and self._skip:
            self._skip -= 1
        if tag in _BLOCK_TAGS and not self._skip:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._capture_ld:
            self._ld_buffer.append(data)
        elif self._in_title:
            self.title += data
        elif not self._skip:
            self.parts.append(data)


def _parse_html(html: str) -> tuple[str, _HtmlText]:
    """Visible text plus the parser state (title, meta tags, JSON-LD blocks)."""
    parser = _HtmlText()
    try:
        parser.feed(html)
        parser.close()
    except Exception as exc:  # html.parser can fail on pathological markup
        raise ValidationError("The page could not be parsed.") from exc
    return "".join(parser.parts), parser


def _html_to_text(html: str) -> str:
    return _parse_html(html)[0]


def _find_job_posting(node: Any) -> dict[str, Any] | None:
    if isinstance(node, list):
        for item in node:
            found = _find_job_posting(item)
            if found:
                return found
    elif isinstance(node, dict):
        node_type = node.get("@type")
        types = node_type if isinstance(node_type, list) else [node_type]
        if "JobPosting" in types:
            return node
        for key in ("@graph", "mainEntity", "itemListElement"):
            if key in node:
                found = _find_job_posting(node[key])
                if found:
                    return found
    return None


def _ld_location(posting: dict[str, Any]) -> str | None:
    locations = posting.get("jobLocation")
    items = locations if isinstance(locations, list) else [locations]
    names: list[str] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        address = item.get("address")
        if isinstance(address, dict):
            parts = [address.get("addressLocality"), address.get("addressRegion"), address.get("addressCountry")]
            text = ", ".join(str(p).strip() for p in parts if isinstance(p, str) and p.strip())
            if text:
                names.append(text)
        elif isinstance(address, str) and address.strip():
            names.append(address.strip())
    if posting.get("jobLocationType") == "TELECOMMUTE" and not names:
        names.append("Remote")
    return "; ".join(dict.fromkeys(names)) or None


def _from_html(html: str, url: str | None, source: str) -> Position:
    text, parser = _parse_html(html)
    posting: dict[str, Any] | None = None
    for raw in parser.json_ld:
        try:
            posting = _find_job_posting(json.loads(raw))
        except (ValueError, TypeError):
            continue
        if posting:
            break
    if posting:
        organization = posting.get("hiringOrganization")
        company = organization.get("name") if isinstance(organization, dict) else organization
        employment = posting.get("employmentType")
        description = _html_to_text(unescape(str(posting.get("description") or ""))) or text
        position = parse_position_text(
            description,
            url=url,
            source=source,
            title=str(posting.get("title") or "") or None,
            company=company if isinstance(company, str) else None,
            location=_ld_location(posting),
            published_at=str(posting.get("datePosted") or "") or None,
            employment_type=", ".join(employment) if isinstance(employment, list) else employment,
            extracted_with="json_ld",
        )
        return position
    title_hint = parser.meta.get("og:title") or parser.title.strip() or None
    return parse_position_text(
        text,
        url=url,
        source=source,
        title=title_hint if title_hint and len(title_hint) <= 160 else None,
        company=parser.meta.get("og:site_name"),
    )


# --------------------------------------------------------------------------- #
# Heuristic parsing of plain job-ad text
# --------------------------------------------------------------------------- #
_LABELS = {
    "title": r"job\s*title|position|stelle|stellenbezeichnung|stellentitel|rolle|titel|role",
    "company": r"company|unternehmen|firma|arbeitgeber|employer|organisation|organization",
    "location": r"location|standort|arbeitsort|einsatzort|ort|place of work",
}
_LABEL_RE = {
    name: re.compile(rf"^\s*(?:{pattern})\s*[:\-–]\s*(.+?)\s*$", re.IGNORECASE) for name, pattern in _LABELS.items()
}
_TITLE_AT_RE = re.compile(r"^(?P<title>.{3,120}?)\s+(?:at|bei|@)\s+(?P<company>[^|()\n]{2,80})$", re.IGNORECASE)
_WORD_RE = re.compile(r"[^\W\d_][\w+#.\-]{2,}", re.UNICODE)
_STOPWORDS = frozenset(
    """
    and the for with you your our are will have has this that from not but all can any more their they who what when
    work working team experience years year role job position company about into able also well such other including
    und der die das den dem des ein eine einer eines einem einen mit für von bei auf aus nach wir sie ihr ihre ihren
    sind ist wird werden haben hat oder als auch sich zu zum zur im in an am dass nicht sowie über unter durch bis
    deine dein dich uns unser unsere mehr gute guter gutes jahre jahren arbeit stelle bewerbung
    """.split()
)


def extract_keywords(text: str, limit: int = 20) -> tuple[str, ...]:
    """Most frequent meaningful terms (stop-word filtered, deterministic order)."""
    counts: Counter[str] = Counter()
    for match in _WORD_RE.finditer(text):
        word = match.group(0).strip(".-").casefold()
        if len(word) >= 3 and word not in _STOPWORDS:
            counts[word] += 1
    ranked = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return tuple(word for word, _count in ranked[:limit])


def _clip(value: str | None, limit: int = 200) -> str | None:
    if value is None:
        return None
    text = " ".join(value.split())
    return text[:limit] or None


def parse_position_text(
    text: str,
    *,
    url: str | None = None,
    source: str = "text",
    title: str | None = None,
    company: str | None = None,
    location: str | None = None,
    published_at: str | None = None,
    employment_type: str | None = None,
    extracted_with: str = "heuristic",
) -> Position:
    """Turn raw job-ad text into a :class:`Position` (explicit hints win)."""
    cleaned = "\n".join(line.rstrip() for line in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"))
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned).strip()[:MAX_TEXT_CHARS]
    if len(cleaned) < MIN_TEXT_CHARS:
        raise ValidationError("The text is too short to be a job posting.")

    lines = [line.strip() for line in cleaned.split("\n") if line.strip()]
    found: dict[str, str] = {}
    for line in lines[:40]:
        for name, pattern in _LABEL_RE.items():
            match = pattern.match(line)
            if match and name not in found:
                found[name] = match.group(1)

    resolved_title = _clip(title) or _clip(found.get("title"))
    resolved_company = _clip(company) or _clip(found.get("company"))
    resolved_location = _clip(location) or _clip(found.get("location"))

    if resolved_title is None and lines:
        first = lines[0]
        at_match = _TITLE_AT_RE.match(first)
        if at_match:
            resolved_title = _clip(at_match.group("title"))
            resolved_company = resolved_company or _clip(at_match.group("company"))
        elif len(first) <= 120 and not any(pattern.match(first) for pattern in _LABEL_RE.values()):
            resolved_title = _clip(first)

    warnings = tuple(
        f"{name} could not be determined"
        for name, value in (("title", resolved_title), ("company", resolved_company), ("location", resolved_location))
        if value is None
    )
    return Position(
        title=resolved_title,
        company=resolved_company,
        location=resolved_location,
        description=cleaned,
        url=url,
        source=source,
        published_at=_clip(published_at, 40),
        employment_type=_clip(employment_type, 80),
        keywords=extract_keywords(cleaned),
        extracted_with=extracted_with,
        warnings=warnings,
    )


# --------------------------------------------------------------------------- #
# SSRF-safe URL fetching
# --------------------------------------------------------------------------- #
def _default_resolver(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, None, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise ValidationError("The URL's host name could not be resolved.") from exc
    return list(dict.fromkeys(info[4][0] for info in infos))


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address.split("%")[0])
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return ip.is_global and not ip.is_multicast


def validate_public_url(url: str, resolver: Resolver | None = None) -> tuple[str, str, int, str]:
    """Validate ``url`` and return ``(scheme, host, port, pinned_ip)``.

    Rejects non-http(s) schemes, embedded credentials, non-standard ports and
    any host that resolves to a non-public address (loopback, private,
    link-local, metadata, CGNAT, multicast, reserved…).
    """
    parts = urlsplit(url.strip())
    if parts.scheme not in {"http", "https"}:
        raise ValidationError("Only http and https URLs are supported.")
    if parts.username or parts.password:
        raise ValidationError("URLs with embedded credentials are not allowed.")
    host = parts.hostname
    if not host:
        raise ValidationError("The URL has no host name.")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise ValidationError("The URL has an invalid port.") from exc
    if port not in {80, 443}:
        raise ValidationError("Only standard web ports (80, 443) are allowed.")
    try:
        addresses = [str(ipaddress.ip_address(host))]
    except ValueError:
        addresses = (resolver or _default_resolver)(host)
    if not addresses:
        raise ValidationError("The URL's host name could not be resolved.")
    if not all(_is_public(address) for address in addresses):
        raise ValidationError("The URL points to a non-public address and cannot be fetched.")
    return parts.scheme, host, port, addresses[0]


def fetch_url(
    url: str,
    *,
    resolver: Resolver | None = None,
    transport: httpx.BaseTransport | None = None,
) -> tuple[bytes, str, str]:
    """Download ``url`` safely; returns ``(content, content_type, final_url)``."""
    current = url.strip()
    with httpx.Client(timeout=FETCH_TIMEOUT_SECONDS, follow_redirects=False, transport=transport) as client:
        for _hop in range(MAX_REDIRECTS + 1):
            scheme, host, port, pinned = validate_public_url(current, resolver)
            parts = urlsplit(current)
            netloc_host = f"[{pinned}]" if ":" in pinned else pinned
            default_port = 443 if scheme == "https" else 80
            netloc = netloc_host if port == default_port else f"{netloc_host}:{port}"
            target = f"{scheme}://{netloc}{parts.path or '/'}" + (f"?{parts.query}" if parts.query else "")
            extensions: dict[str, Any] = {"sni_hostname": host} if scheme == "https" else {}
            try:
                with client.stream(
                    "GET",
                    target,
                    headers={
                        "Host": host if port == default_port else f"{host}:{port}",
                        "User-Agent": USER_AGENT,
                        "Accept": "text/html,application/xhtml+xml,text/plain,application/pdf;q=0.9,*/*;q=0.1",
                    },
                    extensions=extensions,
                ) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        location = response.headers.get("location")
                        if not location:
                            raise ExternalServiceError("The page redirected without a target.", internal="no location")
                        current = urljoin(current, location)
                        continue
                    if response.status_code >= 400:
                        raise ExternalServiceError(
                            f"The page could not be loaded (HTTP {response.status_code}).",
                            internal=f"fetch status {response.status_code}",
                        )
                    declared = response.headers.get("content-length")
                    if declared and declared.isdigit() and int(declared) > MAX_FETCH_BYTES:
                        raise ValidationError("The page is too large to import.")
                    chunks: list[bytes] = []
                    size = 0
                    for chunk in response.iter_bytes():
                        size += len(chunk)
                        if size > MAX_FETCH_BYTES:
                            raise ValidationError("The page is too large to import.")
                        chunks.append(chunk)
                    return b"".join(chunks), response.headers.get("content-type", ""), current
            except httpx.TimeoutException as exc:
                raise ExternalServiceError("The page took too long to respond.", internal=type(exc).__name__) from exc
            except httpx.HTTPError as exc:
                raise ExternalServiceError("The page could not be loaded.", internal=type(exc).__name__) from exc
    raise ValidationError("The URL redirected too many times.")


# --------------------------------------------------------------------------- #
# ZIP archives
# --------------------------------------------------------------------------- #
_ZIP_SUPPORTED = (".pdf", ".docx", ".txt", ".md", ".html", ".htm", ".png", ".jpg", ".jpeg", ".webp")


def _from_zip(content: bytes, ocr: OcrEngine | None) -> ExtractionResult:
    archive = _guard_zip_container(content)
    result = ExtractionResult()
    consumed = 0
    with archive:
        members = [info for info in archive.infolist() if not info.is_dir()]
        if len(members) > MAX_ZIP_ENTRIES:
            raise ValidationError(f"The archive has more than {MAX_ZIP_ENTRIES} files.")
        for info in members:
            name = info.filename
            base = name.rsplit("/", 1)[-1]
            if name.startswith("__MACOSX/") or base.startswith(".") or base.startswith("~$"):
                continue
            if name.startswith(("/", "\\")) or ".." in name.replace("\\", "/").split("/"):
                result.skipped.append({"name": name, "reason": "unsafe path"})
                continue
            if not base.lower().endswith(_ZIP_SUPPORTED):
                result.skipped.append({"name": name, "reason": "unsupported file type"})
                continue
            if info.file_size > MAX_ZIP_MEMBER_BYTES:
                result.skipped.append({"name": name, "reason": "file too large"})
                continue
            consumed += info.file_size
            if consumed > MAX_ZIP_TOTAL_BYTES:
                raise ValidationError("The archive expands to more than the allowed size.")
            with archive.open(info) as handle:
                data = handle.read(MAX_ZIP_MEMBER_BYTES + 1)
            if len(data) > MAX_ZIP_MEMBER_BYTES:
                result.skipped.append({"name": name, "reason": "file too large"})
                continue
            try:
                kind = detect_kind(data)
                if kind == "zip":
                    result.skipped.append({"name": name, "reason": "nested archives are not opened"})
                    continue
                result.positions.append(_extract_single(data, kind, source=f"zip:{base}", ocr=ocr))
            except (ValidationError, ConfigurationError) as exc:
                result.skipped.append({"name": name, "reason": exc.message})
    if not result.positions and not result.skipped:
        raise ValidationError("The archive contains no files.")
    return result


# --------------------------------------------------------------------------- #
# Public entry points
# --------------------------------------------------------------------------- #
def _default_source(kind: str, url: str | None) -> str:
    if kind in {"png", "jpeg", "webp"}:
        return "image"
    if kind in {"html", "text"}:
        return "url" if url else ("html" if kind == "html" else "text")
    return kind  # pdf | docx


def _extract_single(
    content: bytes,
    kind: str,
    *,
    source: str | None = None,
    url: str | None = None,
    ocr: OcrEngine | None = None,
) -> Position:
    origin = source or _default_source(kind, url)
    if kind == "pdf":
        return parse_position_text(text_from_pdf(content), url=url, source=origin)
    if kind == "docx":
        return parse_position_text(text_from_docx(content), url=url, source=origin)
    if kind in {"png", "jpeg", "webp"}:
        return parse_position_text(text_from_image(content, ocr), url=url, source=origin)
    if kind == "html":
        return _from_html(_decode(content), url, origin)
    return parse_position_text(_decode(content), url=url, source=origin)


def extract_from_text(text: str, *, url: str | None = None) -> ExtractionResult:
    """Pasted text (plain or HTML)."""
    if not text or not text.strip():
        raise ValidationError("Provide the job posting text.")
    if len(text) > MAX_TEXT_CHARS * 4:
        raise ValidationError("The text is too long.")
    kind = "html" if re.search(r"<\s*(html|body|div|p|h1|ul)\b", text[:4096], re.IGNORECASE) else "text"
    position = _extract_single(text.encode("utf-8"), kind, source="text", url=url)
    return ExtractionResult(positions=[position])


def extract_from_url(
    url: str,
    *,
    resolver: Resolver | None = None,
    transport: httpx.BaseTransport | None = None,
    ocr: OcrEngine | None = None,
) -> ExtractionResult:
    """Fetch a public job-ad URL and extract the position."""
    content, _content_type, final_url = fetch_url(url, resolver=resolver, transport=transport)
    if not content:
        raise ValidationError("The page is empty.")
    kind = detect_kind(content)
    if kind == "zip":
        raise ValidationError("The URL does not point to a job posting page.")
    position = _extract_single(content, kind, source="url", url=final_url, ocr=ocr)
    return ExtractionResult(positions=[position])


def extract_from_file(content: bytes, *, filename: str | None = None, ocr: OcrEngine | None = None) -> ExtractionResult:
    """Uploaded file: PDF, DOCX, image, ZIP, HTML or text (type detected from bytes)."""
    if not content:
        raise ValidationError("The uploaded file is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise ValidationError(f"The file is larger than {MAX_UPLOAD_BYTES // (1024 * 1024)} MB.")
    kind = detect_kind(content)
    if kind == "zip":
        return _from_zip(content, ocr)
    return ExtractionResult(positions=[_extract_single(content, kind, ocr=ocr)])
