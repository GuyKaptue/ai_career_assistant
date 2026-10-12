"""Unit tests for jobs service hardening (BE-04)."""

from __future__ import annotations

import time

import pytest

from app.domain.jobs.service import (
    _audit_to_dict,
    _cache_key,
    _get_cached,
    _is_rate_limit_error,
    _prune_cache,
    _search_with_retry,
    _set_cache,
    clear_job_cache,
    search_jobs,
)


class FakeProvider:
    name = "fake-provider"

    def __init__(self, jobs=None, error=None, rate_limit=False):
        self.jobs = jobs or []
        self.error = error
        self.rate_limit = rate_limit
        self.call_count = 0

    def search(self, query, location=None, limit=5):
        self.call_count += 1
        if self.rate_limit and self.call_count < 3:
            raise RuntimeError("429 rate limit exceeded")
        if self.error:
            raise self.error
        return self.jobs


class TestCacheKey:
    def test_deterministic(self):
        key1 = _cache_key("python", "remote", 1, 5)
        key2 = _cache_key("python", "remote", 1, 5)
        assert key1 == key2

    def test_different_params(self):
        key1 = _cache_key("python", "remote", 1, 5)
        key2 = _cache_key("python", "remote", 2, 5)
        assert key1 != key2


class TestCache:
    def setup_method(self):
        clear_job_cache()

    def test_set_and_get(self):
        jobs = [{"title": "Test"}]
        _set_cache("python", "remote", 1, 5, jobs)
        cached = _get_cached("python", "remote", 1, 5)
        assert cached == jobs

    def test_get_missing(self):
        assert _get_cached("nonexistent", None, 1, 5) is None

    def test_expiry(self):
        jobs = [{"title": "Test"}]
        _set_cache("python", "remote", 1, 5, jobs)
        # Manually expire the entry
        from app.domain.jobs.service import _cache

        key = _cache_key("python", "remote", 1, 5)
        _cache[key].expires_at = time.monotonic() - 1
        assert _get_cached("python", "remote", 1, 5) is None

    def test_prune_removes_expired(self):
        jobs = [{"title": "Test"}]
        _set_cache("python", "remote", 1, 5, jobs)
        from app.domain.jobs.service import _cache

        key = _cache_key("python", "remote", 1, 5)
        _cache[key].expires_at = time.monotonic() - 1
        _prune_cache()
        assert key not in _cache


class TestRateLimitDetection:
    def test_429(self):
        assert _is_rate_limit_error(RuntimeError("429 Too Many Requests"))

    def test_rate_limit_text(self):
        assert _is_rate_limit_error(RuntimeError("rate limit exceeded"))

    def test_too_many_requests(self):
        assert _is_rate_limit_error(RuntimeError("too many requests"))

    def test_other_error(self):
        assert not _is_rate_limit_error(RuntimeError("connection refused"))


class TestSearchWithRetry:
    def test_success_first_try(self):
        provider = FakeProvider(jobs=[{"title": "Test"}])
        result = _search_with_retry(provider, "python", None, 5)
        assert result == [{"title": "Test"}]
        assert provider.call_count == 1

    def test_retries_on_rate_limit(self):
        provider = FakeProvider(jobs=[{"title": "Test"}], rate_limit=True)
        result = _search_with_retry(provider, "python", None, 5)
        assert result == [{"title": "Test"}]
        assert provider.call_count == 3

    def test_fails_fast_on_non_transient(self):
        provider = FakeProvider(error=ValueError("bad request"))
        with pytest.raises(ValueError, match="bad request"):
            _search_with_retry(provider, "python", None, 5)
        assert provider.call_count == 1


class TestProviderSelection:
    """The provider set is opt-in; only complete Adzuna credentials add one."""

    def test_no_provider_configured_selects_nothing(self, monkeypatch):
        from app.domain.jobs.providers import _provider_names

        monkeypatch.delenv("JOB_PROVIDER", raising=False)
        monkeypatch.delenv("JOB_PROVIDERS", raising=False)
        assert _provider_names() == []

    def test_explicit_provider_list_is_used(self, monkeypatch):
        from app.domain.jobs.providers import _provider_names

        monkeypatch.setenv("JOB_PROVIDER", "arbeitnow, arbeitsagentur,arbeitnow")
        assert _provider_names() == ["arbeitnow", "arbeitsagentur"]

    def test_unknown_provider_is_a_configuration_error(self, monkeypatch):
        from app.domain.jobs.providers import _provider_names
        from app.infrastructure.job_providers.base import JobProviderError

        monkeypatch.setenv("JOB_PROVIDER", "linkedin")
        with pytest.raises(JobProviderError) as excinfo:
            _provider_names()
        assert excinfo.value.category == "unknown_provider"

    def test_adzuna_is_implicit_only_with_both_credentials(self, monkeypatch):
        from app.domain.jobs.providers import _provider_names

        monkeypatch.delenv("JOB_PROVIDER", raising=False)
        monkeypatch.delenv("JOB_PROVIDERS", raising=False)
        monkeypatch.setenv("ADZUNA_APP_ID", "id-only")
        monkeypatch.delenv("ADZUNA_APP_KEY", raising=False)
        assert _provider_names() == []

        monkeypatch.setenv("ADZUNA_APP_KEY", "key")
        assert _provider_names() == ["adzuna"]


class TestSearchJobs:
    def setup_method(self):
        clear_job_cache()

    def test_requires_query(self):
        with pytest.raises(ValueError, match="search query is required"):
            search_jobs("")

    def test_requires_provider(self, monkeypatch):
        monkeypatch.setattr("app.domain.jobs.service._build_providers", lambda: [])
        with pytest.raises(RuntimeError, match="No job provider"):
            search_jobs("python")

    def test_returns_results_with_audit(self, monkeypatch):
        provider = FakeProvider(
            jobs=[
                {
                    "title": "Data Analyst",
                    "company": "Test Corp",
                    "location": "Remote",
                    "description": "Analyze data.",
                    "url": "https://example.com/1",
                    "source": "fake",
                    "provider_id": "1",
                }
            ]
        )
        monkeypatch.setattr("app.domain.jobs.service._build_providers", lambda: [provider])

        result = search_jobs("data analyst", location="Remote", limit=5)

        assert result["count"] == 1
        assert result["results"][0]["title"] == "Data Analyst"
        assert result["page"] == 1
        assert result["limit"] == 5
        assert result["total"] == 1
        assert result["audit"]["providers_succeeded"] == 1
        assert result["audit"]["cached"] is False

    def test_caches_first_page(self, monkeypatch):
        provider = FakeProvider(
            jobs=[
                {
                    "title": "Data Analyst",
                    "company": "Test Corp",
                    "location": "Remote",
                    "description": "Analyze data.",
                    "url": "https://example.com/1",
                    "source": "fake",
                    "provider_id": "1",
                }
            ]
        )
        monkeypatch.setattr("app.domain.jobs.service._build_providers", lambda: [provider])

        result1 = search_jobs("data analyst", limit=5)
        assert result1["audit"]["cached"] is False
        assert provider.call_count == 1

        result2 = search_jobs("data analyst", limit=5)
        assert result2["audit"]["cached"] is True
        assert provider.call_count == 1  # No additional call

    def test_pagination(self, monkeypatch):
        jobs = []
        for i in range(10):
            jobs.append(
                {
                    "title": f"Job {i}",
                    "company": "Test Corp",
                    "location": "Remote",
                    "description": "Work.",
                    "url": f"https://example.com/{i}",
                    "source": "fake",
                    "provider_id": str(i),
                }
            )
        provider = FakeProvider(jobs=jobs)
        monkeypatch.setattr("app.domain.jobs.service._build_providers", lambda: [provider])

        page1 = search_jobs("job", limit=3, page=1)
        assert page1["count"] == 3
        assert page1["results"][0]["title"] == "Job 0"

        page2 = search_jobs("job", limit=3, page=2)
        assert page2["count"] == 3
        assert page2["results"][0]["title"] == "Job 3"

        page4 = search_jobs("job", limit=3, page=4)
        assert page4["count"] == 1  # Only 10 jobs total

    def test_provider_failure_isolation(self, monkeypatch):
        good_provider = FakeProvider(
            jobs=[
                {
                    "title": "Good Job",
                    "company": "Test Corp",
                    "location": "Remote",
                    "description": "Work.",
                    "url": "https://example.com/good",
                    "source": "good",
                    "provider_id": "good",
                }
            ]
        )
        bad_provider = FakeProvider(error=RuntimeError("provider down"))
        monkeypatch.setattr(
            "app.domain.jobs.service._build_providers",
            lambda: [good_provider, bad_provider],
        )

        result = search_jobs("job", limit=5)
        assert result["count"] == 1
        assert result["results"][0]["title"] == "Good Job"
        assert result["audit"]["providers_succeeded"] == 1
        assert result["audit"]["providers_failed"] == 1
        assert len(result["audit"]["errors"]) == 1


class TestAuditToDict:
    def test_serializable(self):
        from app.domain.jobs.service import SearchAudit

        audit = SearchAudit(
            query="python",
            location="remote",
            page=1,
            limit=5,
            providers_attempted=1,
            providers_succeeded=1,
            providers_failed=0,
            total_results=1,
            cached=False,
            duration_ms=10,
            errors=[],
        )
        data = _audit_to_dict(audit)
        assert data["query"] == "python"
        assert data["cached"] is False
        assert data["errors"] == []
