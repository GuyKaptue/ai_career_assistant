"""Bundesagentur für Arbeit Jobsuche API adapter."""

from __future__ import annotations

import base64
from typing import Any
from urllib.parse import quote

from app.domain.jobs.models import Job
from app.infrastructure.job_providers.base import (
    JobProviderError,
    JobSearchOptions,
    ProviderSearchResult,
    company_name,
    first_present,
    optional_int,
    optional_text,
    response_rows,
    valid_job_url,
)
from app.infrastructure.job_providers.http import get_json

WORK_TIME_CODES = {"vz", "tz", "snw", "ho", "mj"}
CONTRACT_CODES = {"1", "2"}


def _location(item: dict[str, Any]) -> str | None:
    raw = item.get("arbeitsort") or item.get("place") or item.get("location")
    if not raw and isinstance(item.get("stellenlokationen"), list):
        raw = next((place for place in item["stellenlokationen"] if isinstance(place, dict)), None)
    if isinstance(raw, dict):
        city = optional_text(first_present(raw, "ort", "city", "display_name"))
        region = optional_text(raw.get("region"))
        if city and region and region.casefold() not in city.casefold():
            return f"{city}, {region}"
        return city or region
    return optional_text(raw)


def _published_at(item: dict[str, Any]) -> str | None:
    return optional_text(
        first_present(
            item,
            "aktuelleVeroeffentlichungsdatum",
            "datumErsteVeroeffentlichung",
            "publishedAt",
            "date",
            "createdAt",
        )
    )


def _salary(item: dict[str, Any]) -> str | None:
    direct = optional_text(first_present(item, "verguetung", "verguetungsangabe", "salary"))
    if direct:
        return direct
    minimum = optional_text(item.get("gehaltsspanneVon"))
    maximum = optional_text(item.get("gehaltsspanneBis"))
    if minimum and maximum:
        return f"{minimum}–{maximum}"
    return minimum or maximum


def _boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value
    return None


def _validate_filter(name: str, value: str | None, allowed: set[str]) -> str | None:
    if value is None or not value.strip():
        return None
    values = [part.strip().lower() for part in value.split(";") if part.strip()]
    if not values or any(part not in allowed for part in values):
        raise ValueError(f"{name} must use documented values: {', '.join(sorted(allowed))}.")
    return ";".join(values)


class ArbeitsagenturProvider:
    name = "arbeitsagentur"
    API_KEY = "jobboerse-jobsuche"

    def __init__(
        self,
        base_url: str | None = None,
        details_base_url: str | None = None,
        api_key: str | None = None,
        radius_km: int = 50,
    ) -> None:
        self.base_url = base_url or "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v6/jobs"
        self.details_base_url = (
            details_base_url or "https://rest.arbeitsagentur.de/jobboerse/jobsuche-service/pc/v4/jobdetails"
        )
        self.api_key = api_key or self.API_KEY
        self.radius_km = radius_km

    def search(
        self,
        query: str,
        location: str | None = None,
        limit: int = 5,
        page: int = 1,
        options: JobSearchOptions | None = None,
    ) -> ProviderSearchResult:
        if not query.strip():
            raise ValueError("A search query is required.")
        options = options or JobSearchOptions()
        page = max(1, page)
        limit = min(max(1, limit), 100)
        radius = options.radius_km if options.radius_km is not None else self.radius_km
        if radius < 0 or radius > 200:
            raise ValueError("radius_km must be between 0 and 200.")
        if options.published_since_days is not None and not 0 <= options.published_since_days <= 100:
            raise ValueError("published_since_days must be between 0 and 100.")

        work_time = _validate_filter("work_time", options.work_time, WORK_TIME_CODES)
        contract_type = _validate_filter("contract_type", options.contract_type, CONTRACT_CODES)
        params: dict[str, str | int] = {"was": query.strip(), "size": limit, "page": page}
        if location and location.strip():
            params["wo"] = location.strip()
            params["umkreis"] = radius
        if options.published_since_days is not None:
            params["veroeffentlichtseit"] = options.published_since_days
        if work_time:
            params["arbeitszeit"] = work_time
        if contract_type:
            params["befristung"] = contract_type

        payload = get_json(self.name, self.base_url, params=params, headers={"X-API-Key": self.api_key})
        if not isinstance(payload, dict):
            raise JobProviderError(self.name, "invalid_response")
        rows = response_rows(payload, "ergebnisliste", "stellenangebote", "jobs", provider=self.name)
        jobs = [
            Job(
                title=optional_text(first_present(item, "stellenangebotsTitel", "titel", "title", "beruf")),
                company=company_name(first_present(item, "firma", "arbeitgeber", "company", "companyName")),
                location=_location(item),
                description=optional_text(
                    first_present(item, "stellenangebotsBeschreibung", "stellenbeschreibung", "description")
                ),
                url=valid_job_url(first_present(item, "externeUrl", "externalUrl", "url", "jobUrl")),
                source=self.name,
                provider_id=optional_text(first_present(item, "referenznummer", "refnr", "hashId", "id")),
                published_at=_published_at(item),
                salary=_salary(item),
                remote=_boolean(first_present(item, "homeofficemoeglich", "homeOfficePossible", "remote")),
            )
            for item in rows
        ]
        total = optional_int(first_present(payload, "maxErgebnisse", "total", "count"))
        has_more = page * limit < total if total is not None else (len(rows) == limit)
        return ProviderSearchResult(jobs=jobs, total=total, has_more=has_more)

    def get_details(self, refnr: str) -> dict[str, Any]:
        raw_refnr = str(refnr).strip()
        if not raw_refnr:
            raise ValueError("A job refnr is required to fetch details.")
        encoded = base64.b64encode(raw_refnr.encode("utf-8")).decode("ascii")
        payload = get_json(
            self.name,
            f"{self.details_base_url}/{quote(encoded, safe='')}",
            headers={"X-API-Key": self.api_key},
        )
        if not isinstance(payload, dict):
            raise JobProviderError(self.name, "invalid_response")
        return payload
