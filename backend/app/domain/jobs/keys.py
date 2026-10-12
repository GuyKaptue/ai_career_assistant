"""Stable identity keys for jobs and applications.

The tracker, the job search and the apply flow must agree on "is this the same
job?". Provider ids are not enough (the same posting appears on several
boards), so identity is derived from normalised content:

* :func:`job_key`   — ``company | title | location`` (the aggregator's own
  de-duplication identity), hashed to a short, URL-safe key.
* :func:`loose_key` — ``company | title`` only; used to recognise *manually*
  tracked applications that never recorded a location or URL.
* :func:`normalize_url` — scheme/``www``/tracking-parameter-insensitive URL.
"""

from __future__ import annotations

import hashlib
import re
from urllib.parse import parse_qsl, urlsplit

_NON_WORD = re.compile(r"[\W_]+", re.UNICODE)
_TRACKING_PARAMS = frozenset({"gclid", "fbclid", "ref", "source", "referrer", "trk", "mc_cid", "mc_eid"})


def _normalise(value: str | None) -> str:
    """Case-fold, strip punctuation and collapse whitespace (Unicode-aware)."""
    return _NON_WORD.sub(" ", (value or "").casefold()).strip()


def _digest(*parts: str) -> str:
    return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:20]


def job_key(company: str | None, title: str | None, location: str | None) -> str:
    """Identity of a posting: same company, title and location ⇒ same key."""
    return _digest(_normalise(company), _normalise(title), _normalise(location))


def loose_key(company: str | None, title: str | None) -> str:
    """Identity without location, for entries that only know company + role."""
    return _digest("loose", _normalise(company), _normalise(title))


def normalize_url(url: str | None) -> str | None:
    """Comparable form of a job URL, or ``None`` when it is not a usable URL."""
    if not url or not url.strip():
        return None
    parts = urlsplit(url.strip())
    host = (parts.hostname or "").casefold()
    if not host:
        return None
    if host.startswith("www."):
        host = host[4:]
    kept = sorted(
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=False)
        if not key.casefold().startswith("utm_") and key.casefold() not in _TRACKING_PARAMS
    )
    query = "&".join(f"{key}={value}" for key, value in kept)
    path = parts.path.rstrip("/")
    return f"{host}{path}" + (f"?{query}" if query else "")
