"""Hermetic contract tests for job providers and their aggregator."""

from __future__ import annotations

import base64
import threading
from urllib.parse import unquote

import httpx
import pytest

from app.domain.jobs.models import Job
from app.domain.jobs.providers import (
    AdzunaProvider,
    ArbeitnowProvider,
    ArbeitsagenturProvider,
    JobProviderError,
    JobSearchOptions,
    ProviderSearchResult,
    RemotiveProvider,
    _deduplicate_jobs,
)
from app.domain.jobs.service import (
    CACHE_TTL_SECONDS,
    JobSearchFailed,
    _cache_key,
    _is_retryable_error,
    _parse_posted_at,
    _sort_by_posted_date,
    clear_job_cache,
    search_jobs,
)
from app.infrastructure.job_providers.http import parse_retry_after


def _install_mock_transport(monkeypatch: pytest.MonkeyPatch, handler):
    captured: list[httpx.Request] = []

    def dispatch(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return handler(request)

    client = httpx.Client(transport=httpx.MockTransport(dispatch))
    monkeypatch.setattr(
        "app.infrastructure.job_providers.http.httpx.get",
        lambda url, **kwargs: client.get(url, **kwargs),
    )
    return captured


class TestAdzunaProvider:
    def test_germany_endpoint_and_credentials_are_query_parameters(self, monkeypatch):
        monkeypatch.setenv("ADZUNA_APP_ID", "unit-id")
        monkeypatch.setenv("ADZUNA_APP_KEY", "unit-key")
        captured = _install_mock_transport(monkeypatch, lambda request: httpx.Response(200, json={"results": []}))

        AdzunaProvider().search("python", location="Berlin", limit=5)

        request = captured[0]
        assert request.url.path.endswith("/v1/api/jobs/de/search/1")
        assert request.url.params["app_id"] == "unit-id"
        assert request.url.params["app_key"] == "unit-key"
        assert request.url.params["what"] == "python"
        assert request.url.params["where"] == "Berlin"

    def test_missing_credentials_fail_explicitly(self, monkeypatch):
        monkeypatch.delenv("ADZUNA_APP_ID", raising=False)
        monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)
        with pytest.raises(JobProviderError) as error:
            AdzunaProvider().search("python")
        assert error.value.category == "not_configured"
        assert not error.value.retryable

    def test_maps_optional_data_and_salary_without_invention(self, monkeypatch):
        monkeypatch.setenv("ADZUNA_APP_ID", "unit-id")
        monkeypatch.setenv("ADZUNA_APP_KEY", "unit-key")
        payload = {
            "count": 1,
            "results": [
                {
                    "id": 12345,
                    "title": "Data Scientist",
                    "company": {"display_name": "Acme GmbH"},
                    "location": {"display_name": "Berlin"},
                    "description": "Build models.",
                    "redirect_url": "https://jobs.example.test/1",
                    "created": "2026-10-01T10:00:00Z",
                    "salary_min": 60000,
                    "salary_max": 80000,
                },
                {"id": "missing-fields", "title": "Sparse", "redirect_url": "https://jobs.example.test/2"},
            ],
        }
        _install_mock_transport(monkeypatch, lambda request: httpx.Response(200, json=payload))

        result = AdzunaProvider().search("data scientist", limit=5)

        assert isinstance(result, ProviderSearchResult)
        first, sparse = result.jobs
        assert (first.title, first.company, first.location) == ("Data Scientist", "Acme GmbH", "Berlin")
        assert first.salary == "60000–80000"
        assert first.published_at == "2026-10-01T10:00:00Z"
        assert first.source == "adzuna" and first.provider_id == "12345"
        assert sparse.company is None and sparse.location is None and sparse.salary is None
        assert sparse.remote is None

    def test_client_error_is_not_retryable_and_key_not_logged(self, monkeypatch, caplog):
        secret_marker = "adzuna-secret-marker"
        monkeypatch.setenv("ADZUNA_APP_ID", "unit-id")
        monkeypatch.setenv("ADZUNA_APP_KEY", secret_marker)
        _install_mock_transport(monkeypatch, lambda request: httpx.Response(401, json={"error": "invalid"}))

        with pytest.raises(JobProviderError) as error:
            AdzunaProvider().search("python")
        assert not error.value.retryable
        assert secret_marker not in caplog.text
        assert secret_marker not in str(error.value)

    def test_rate_limit_preserves_bounded_retry_after_without_response_body(self, monkeypatch):
        _install_mock_transport(
            monkeypatch,
            lambda request: httpx.Response(429, headers={"Retry-After": "3"}, text="sensitive upstream body"),
        )
        with pytest.raises(JobProviderError) as error:
            AdzunaProvider(app_id="id", app_key="key").search("python")
        assert error.value.retryable is True
        assert error.value.retry_after == 3
        assert "sensitive upstream body" not in str(error.value)


class TestArbeitsagenturProvider:
    def test_header_params_and_documented_filter_values(self, monkeypatch):
        captured = _install_mock_transport(
            monkeypatch,
            lambda request: httpx.Response(200, json={"ergebnisliste": [], "maxErgebnisse": "0"}),
        )
        options = JobSearchOptions(
            radius_km=50,
            published_since_days=30,
            work_time="vz;tz",
            contract_type="1;2",
        )
        ArbeitsagenturProvider().search("softwareentwickler", "Berlin", 5, page=2, options=options)

        request = captured[0]
        assert request.headers["X-API-Key"] == "jobboerse-jobsuche"
        assert request.url.params["was"] == "softwareentwickler"
        assert request.url.params["wo"] == "Berlin"
        assert request.url.params["umkreis"] == "50"
        assert request.url.params["page"] == "2"
        assert request.url.params["veroeffentlichtseit"] == "30"
        assert request.url.params["arbeitszeit"] == "vz;tz"
        assert request.url.params["befristung"] == "1;2"

    def test_parses_live_ergebnisliste_shape_and_optional_fields(self, monkeypatch):
        payload = {
            "ergebnisliste": [
                {
                    "referenznummer": "10001-123456789-S",
                    "stellenangebotsTitel": "Softwareentwickler (m/w/d)",
                    "firma": "Firma GmbH",
                    "stellenlokationen": [{"ort": "Berlin", "region": "Berlin"}],
                    "datumErsteVeroeffentlichung": "2026-10-01",
                    "externeUrl": "https://jobs.example.test/1",
                    "verguetungsangabe": "60.000–80.000 EUR",
                    "homeofficemoeglich": True,
                },
                {
                    "referenznummer": "10001-987654321-S",
                    "stellenangebotsTitel": "Data Analyst",
                    "firma": "Daten AG",
                    "stellenlokationen": [{"ort": "Hamburg"}],
                    "externeUrl": None,
                },
            ],
            "maxErgebnisse": "2",
            "page": "1",
            "size": "5",
        }
        _install_mock_transport(monkeypatch, lambda request: httpx.Response(200, json=payload))

        result = ArbeitsagenturProvider().search("softwareentwickler", limit=5)

        assert result.total == 2 and result.has_more is False
        assert len(result.jobs) == 2
        first, second = result.jobs
        assert first.title == "Softwareentwickler (m/w/d)"
        assert first.company == "Firma GmbH" and first.location == "Berlin"
        assert first.provider_id == "10001-123456789-S"
        assert first.salary == "60.000–80.000 EUR" and first.remote is True
        assert second.title == "Data Analyst" and second.url is None
        assert second.salary is None and second.remote is None

    def test_accepts_openapi_stellenangebote_alias(self, monkeypatch):
        payload = {
            "stellenangebote": [
                {
                    "refnr": "ref-1",
                    "beruf": "Data Engineer",
                    "arbeitgeber": "Example AG",
                    "arbeitsort": {"ort": "Köln"},
                    "aktuelleVeroeffentlichungsdatum": "2026-10-02",
                    "externeUrl": "https://jobs.example.test/ref-1",
                }
            ]
        }
        _install_mock_transport(monkeypatch, lambda request: httpx.Response(200, json=payload))

        job = ArbeitsagenturProvider().search("data", limit=1).jobs[0]
        assert job.title == "Data Engineer"
        assert job.company == "Example AG"
        assert job.location == "Köln"
        assert job.published_at == "2026-10-02"

    @pytest.mark.parametrize(
        ("options", "field"),
        [
            (JobSearchOptions(work_time="full-time"), "work_time"),
            (JobSearchOptions(contract_type="unbefristet"), "contract_type"),
            (JobSearchOptions(published_since_days=101), "published_since_days"),
            (JobSearchOptions(radius_km=201), "radius_km"),
        ],
    )
    def test_rejects_undocumented_filter_values(self, options, field):
        with pytest.raises(ValueError, match=field):
            ArbeitsagenturProvider().search("python", options=options)

    def test_rejects_missing_response_array(self, monkeypatch):
        _install_mock_transport(monkeypatch, lambda request: httpx.Response(200, json={"unexpected": []}))
        with pytest.raises(JobProviderError) as error:
            ArbeitsagenturProvider().search("python")
        assert error.value.category == "invalid_response"

    def test_job_details_uses_base64_reference(self, monkeypatch):
        captured = _install_mock_transport(monkeypatch, lambda request: httpx.Response(200, json={"refnr": "ref"}))
        result = ArbeitsagenturProvider().get_details("10001-123456789-S")
        encoded_path = unquote(captured[0].url.path.rsplit("/", 1)[-1])
        assert base64.b64decode(encoded_path).decode() == "10001-123456789-S"
        assert captured[0].headers["X-API-Key"] == "jobboerse-jobsuche"
        assert result["refnr"] == "ref"

    def test_job_details_requires_reference(self):
        with pytest.raises(ValueError, match="refnr"):
            ArbeitsagenturProvider().get_details(" ")


class TestArbeitnowProvider:
    def test_uses_real_feed_page_parameter_and_response_metadata(self, monkeypatch):
        captured = _install_mock_transport(
            monkeypatch,
            lambda request: httpx.Response(
                200,
                json={"data": [], "links": {"next": "https://feed.example.test/?page=2"}, "meta": {"current_page": 1}},
            ),
        )
        result = ArbeitnowProvider().search("python", page=1)
        assert captured[0].url.params["page"] == "1"
        assert "search" not in captured[0].url.params
        assert result.has_more is True
        assert result.jobs == []

    def test_parses_feed_data_and_locally_filters_query_and_location(self, monkeypatch):
        payload = {
            "data": [
                {
                    "slug": "backend-python-1",
                    "title": "Backend Python Engineer",
                    "company_name": "Startup GmbH",
                    "location": "Berlin",
                    "description": "Build APIs.",
                    "url": "https://jobs.example.test/1",
                    "created_at": "2026-10-02T08:00:00Z",
                    "remote": True,
                    "tags": ["python", "backend"],
                },
                {
                    "slug": "frontend-2",
                    "title": "Frontend Engineer",
                    "company_name": "Agency GmbH",
                    "location": "Hamburg",
                    "description": "Build UIs.",
                    "url": "https://jobs.example.test/2",
                    "created_at": "2026-10-01T08:00:00Z",
                    "remote": False,
                    "tags": ["javascript"],
                },
            ],
            "links": {"next": None},
            "meta": {"current_page": 1, "per_page": 325},
        }
        _install_mock_transport(monkeypatch, lambda request: httpx.Response(200, json=payload))

        result = ArbeitnowProvider().search("backend python", location="Berlin", limit=1)

        assert len(result.jobs) == 1
        job = result.jobs[0]
        assert job.title == "Backend Python Engineer"
        assert job.company == "Startup GmbH" and job.location == "Berlin"
        assert job.remote is True and job.tags == ("python", "backend")
        assert job.salary is None
        assert result.has_more is False

    def test_missing_optional_fields_remain_unknown(self, monkeypatch):
        payload = {
            "data": [{"slug": "sparse", "title": "Engineer", "url": "https://jobs.example.test/1"}],
            "links": {},
            "meta": {},
        }
        _install_mock_transport(monkeypatch, lambda request: httpx.Response(200, json=payload))
        job = ArbeitnowProvider().search("engineer").jobs[0]
        assert job.company is None and job.location is None and job.salary is None
        assert job.published_at is None and job.remote is None

    def test_follows_feed_page_when_local_query_has_no_current_page_match(self, monkeypatch):
        requests: list[httpx.Request] = []

        def response(request: httpx.Request) -> httpx.Response:
            requests.append(request)
            page = request.url.params["page"]
            if page == "1":
                return httpx.Response(
                    200,
                    json={"data": [{"title": "Unrelated role"}], "links": {"next": "?page=2"}, "meta": {}},
                )
            return httpx.Response(
                200,
                json={
                    "data": [
                        {
                            "slug": "python-2",
                            "title": "Python Engineer",
                            "company_name": "Example GmbH",
                            "location": "Berlin",
                            "url": "https://jobs.example.test/python-2",
                        }
                    ],
                    "links": {"next": None},
                    "meta": {"current_page": 2},
                },
            )

        _install_mock_transport(monkeypatch, response)
        result = ArbeitnowProvider().search("python", location="Berlin", limit=1)

        assert [request.url.params["page"] for request in requests] == ["1", "2"]
        assert [job.title for job in result.jobs] == ["Python Engineer"]

    def test_feed_page_following_is_bounded(self, monkeypatch):
        """An unbounded `links.next` must not turn one search into endless traffic."""

        captured = _install_mock_transport(
            monkeypatch,
            lambda request: httpx.Response(
                200,
                json={"data": [{"title": "Unrelated role"}], "links": {"next": "?page=next"}, "meta": {}},
            ),
        )
        provider = ArbeitnowProvider(max_feed_pages=3)
        result = provider.search("python", limit=1)

        assert [request.url.params["page"] for request in captured] == ["1", "2", "3"]
        assert result.jobs == []
        assert result.has_more is True

    def test_rejects_non_http_urls(self, monkeypatch):
        payload = {
            "data": [{"slug": "bad", "title": "Engineer", "url": "javascript:alert(1)"}],
            "links": {},
            "meta": {},
        }
        _install_mock_transport(monkeypatch, lambda request: httpx.Response(200, json=payload))
        assert ArbeitnowProvider().search("engineer").jobs[0].url is None


class TestRemotiveProvider:
    def test_remote_status_is_derived_only_when_source_says_remote(self, monkeypatch):
        payload = {
            "jobs": [
                {
                    "id": 7,
                    "title": "Remote Dev",
                    "company_name": "Remote Co",
                    "candidate_required_location": "Remote",
                    "description": "Work from anywhere.",
                    "url": "https://jobs.example.test/1",
                    "published_at": "2026-10-01",
                },
                {"id": 8, "title": "Unclear", "url": "https://jobs.example.test/2"},
            ]
        }
        _install_mock_transport(monkeypatch, lambda request: httpx.Response(200, json=payload))
        jobs = RemotiveProvider().search("dev").jobs
        assert jobs[0].remote is True
        assert jobs[1].remote is None


class TestDeduplication:
    def test_normalizes_identity_and_fills_missing_metadata(self):
        jobs = [
            Job("Data Scientist", "ACME GmbH", "Berlin", None, "https://a.example.test/1", "adzuna", "a-1"),
            Job(" data   scientist ", "acme gmbh", "Berlin", "Role description", None, "arbeitnow", "b-1"),
        ]
        result = _deduplicate_jobs(jobs)
        assert len(result) == 1
        assert result[0].source == "adzuna"
        assert result[0].location == "Berlin"
        assert result[0].description == "Role description"

    def test_incomplete_unidentified_jobs_are_not_collapsed(self):
        jobs = [
            Job(None, None, None, None, None, "provider-a", None),
            Job(None, None, None, None, None, "provider-b", None),
        ]
        assert len(_deduplicate_jobs(jobs)) == 2

    def test_does_not_collapse_distinct_positions(self):
        jobs = [
            Job("Data Scientist", "Acme GmbH", "Berlin", None, "https://a.example/1", "a", "1"),
            Job("Data Engineer", "Acme GmbH", "Berlin", None, "https://a.example/2", "a", "2"),
        ]
        assert len(_deduplicate_jobs(jobs)) == 2


class FakeProvider:
    def __init__(self, name="fake", jobs=None, error=None, retry_count=0):
        self.name = name
        self.jobs = jobs or []
        self.error = error
        self.retry_count = retry_count
        self.calls: list[tuple[int, int]] = []

    def search(self, query, location=None, limit=5, page=1, options=None):
        self.calls.append((page, limit))
        if len(self.calls) <= self.retry_count:
            raise self.error or RuntimeError("503 Service Unavailable")
        if self.error and not self.retry_count:
            raise self.error
        return ProviderSearchResult(self.jobs, has_more=False)


class TestAggregator:
    def setup_method(self):
        clear_job_cache()

    def test_queries_providers_in_parallel(self, monkeypatch):
        first_started = threading.Event()
        second_started = threading.Event()

        class ProbeProvider(FakeProvider):
            def __init__(self, name):
                super().__init__(name=name)

            def search(self, query, location=None, limit=5, page=1, options=None):
                first_started.set() if self.name == "first" else second_started.set()
                assert first_started.wait(2) and second_started.wait(2)
                return ProviderSearchResult([])

        monkeypatch.setattr(
            "app.domain.jobs.service._build_providers",
            lambda: [ProbeProvider("first"), ProbeProvider("second")],
        )
        result = search_jobs("python", limit=5)
        assert result["count"] == 0
        assert result["audit"]["providers_succeeded"] == 2

    def test_merges_partial_success_and_reports_safe_provider_status(self, monkeypatch):
        good = FakeProvider(
            name="good",
            jobs=[Job("Analyst", "Acme", "Berlin", None, "https://jobs.example/1", "good", "1")],
        )
        bad = FakeProvider(name="bad", error=JobProviderError("bad", "rate_limited", retryable=False))
        monkeypatch.setattr("app.domain.jobs.service._build_providers", lambda: [good, bad])
        result = search_jobs("analyst", limit=5)
        assert result["count"] == 1 and result["partial"] is True
        assert result["provider_status"] == [
            {"provider": "good", "status": "succeeded", "count": 1},
            {"provider": "bad", "status": "failed", "count": 0},
        ]
        assert result["audit"]["errors"] == [{"provider": "bad", "category": "rate_limited"}]

    def test_all_provider_failures_are_not_successful_empty_results(self, monkeypatch):
        providers = [
            FakeProvider("a", error=RuntimeError("private request URL")),
            FakeProvider("b", error=ValueError()),
        ]
        monkeypatch.setattr("app.domain.jobs.service._build_providers", lambda: providers)
        with pytest.raises(JobSearchFailed) as error:
            search_jobs("analyst")
        assert "private request URL" not in str(error.value)
        assert {item["provider"] for item in error.value.provider_errors} == {"a", "b"}

    def test_successful_empty_search_is_valid(self, monkeypatch):
        monkeypatch.setattr("app.domain.jobs.service._build_providers", lambda: [FakeProvider("empty")])
        result = search_jobs("nothing matches")
        assert result["results"] == []
        assert result["partial"] is False

    def test_global_pagination_and_newest_first_sort(self, monkeypatch):
        jobs = [
            Job("Old", "A", "Berlin", None, "https://jobs.example/old", "fake", "old", "2026-09-01"),
            Job("New", "B", "Berlin", None, "https://jobs.example/new", "fake", "new", "2026-10-05"),
            Job("Undated", "C", "Berlin", None, "https://jobs.example/none", "fake", "none"),
        ]
        provider = FakeProvider("fake", jobs=jobs)
        monkeypatch.setattr("app.domain.jobs.service._build_providers", lambda: [provider])
        # Fixed historical dates: keep this test independent of today's date by
        # disabling the (default 30-day) recency filter explicitly.
        first = search_jobs("job", limit=2, page=1, include_old=True)
        second = search_jobs("job", limit=2, page=2, include_old=True)
        assert [job["title"] for job in first["results"]] == ["New", "Old"]
        assert [job["title"] for job in second["results"]] == ["Undated"]
        assert second["total"] == 3

    def test_transient_errors_retry_boundedly_without_logging_raw_error(self, monkeypatch, caplog):
        monkeypatch.setattr("app.domain.jobs.service.time.sleep", lambda delay: None)
        monkeypatch.setattr("app.domain.jobs.service.random.uniform", lambda low, high: low)
        provider = FakeProvider(
            "transient",
            jobs=[Job("Recovered", "A", "Berlin", None, "https://jobs.example/1", "transient", "1")],
            retry_count=2,
        )
        # This test uses the provider patched below and proves the retry result.
        monkeypatch.setattr("app.domain.jobs.service._build_providers", lambda: [provider])
        clear_job_cache()
        result = search_jobs("job", limit=5)
        assert result["count"] == 1
        assert len(provider.calls) == 3
        assert "503 Service Unavailable" not in caplog.text

    def test_retry_classifier_rejects_permanent_errors(self):
        assert _is_retryable_error(JobProviderError("x", "rate_limited", retryable=True))
        assert _is_retryable_error(RuntimeError("503 Service Unavailable"))
        assert not _is_retryable_error(JobProviderError("x", "unauthorized", retryable=False))
        assert not _is_retryable_error(RuntimeError("connection refused"))

    def test_cache_key_normalizes_query_and_includes_provider_set(self):
        assert _cache_key(" Python  Dev ", " Berlin ", 1, 5, ("arbeitnow",)) == _cache_key(
            "python dev", "berlin", 1, 5, ("arbeitnow",)
        )
        assert _cache_key("python", None, 1, 5, ("adzuna",)) != _cache_key("python", None, 1, 5, ("arbeitnow",))

    def test_cache_ttl_is_one_hour_by_default(self):
        assert CACHE_TTL_SECONDS == 3600.0

    def test_requires_nonempty_query(self):
        with pytest.raises(ValueError, match="search query is required"):
            search_jobs("  ")

    def test_cache_does_not_store_partial_responses(self, monkeypatch):
        good = FakeProvider("good", jobs=[])
        bad = FakeProvider("bad", error=ValueError("offline"))
        monkeypatch.setattr("app.domain.jobs.service._build_providers", lambda: [good, bad])
        first = search_jobs("partial")
        second = search_jobs("partial")
        assert first["audit"]["cached"] is False
        assert second["audit"]["cached"] is False
        assert len(good.calls) >= 2


def test_date_parser_supports_iso_european_and_invalid_values():
    assert _parse_posted_at("2026-10-01T10:00:00Z") is not None
    assert _parse_posted_at("01.10.2026") is not None
    assert _parse_posted_at("invalid") is None
    assert _parse_posted_at(None) is None


def test_retry_after_http_date_is_parsed_or_ignored_safely():
    assert parse_retry_after("3") == 3
    assert parse_retry_after("not-a-date") is None


def test_undated_job_sorts_last_stably():
    dated = Job("Dated", "A", "Berlin", None, "https://jobs.example/1", "test", "1", "2026-10-01")
    undated = Job("Undated", "B", "Berlin", None, "https://jobs.example/2", "test", "2")
    assert [job.title for job in _sort_by_posted_date([undated, dated])] == ["Dated", "Undated"]


def test_all_jobs_without_urls_are_retained_but_not_linkable():
    job = Job("Role", "Company", "Berlin", None, None, "arbeitsagentur", "reference")
    result = _deduplicate_jobs([job])
    assert len(result) == 1
    assert result[0].url is None
