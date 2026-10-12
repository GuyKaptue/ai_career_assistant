"""Job identity keys, default recency filter and applied-job exclusion."""

from datetime import datetime, timedelta, timezone

import pytest

from app.application.services.application_tracking import ApplicationTracker
from app.domain.jobs.keys import job_key, loose_key, normalize_url
from app.domain.jobs.models import Job
from app.domain.jobs.providers import ProviderSearchResult
from app.domain.jobs.service import clear_job_cache, default_recency_days, search_jobs
from app.infrastructure.job_providers.base import JobSearchOptions


def _days_ago(days: int) -> str:
    return (datetime.now(timezone.utc) - timedelta(days=days)).date().isoformat()


def _job(title, company="Acme", location="Berlin", days=None, url=None, source="fake"):
    return Job(
        title, company, location, "desc", url or f"https://jobs.example/{title}", source, title,
        _days_ago(days) if days is not None else None,
    )  # fmt: skip


class RecordingProvider:
    def __init__(self, jobs, name="fake"):
        self.name = name
        self.jobs = jobs
        self.options_seen: list[JobSearchOptions | None] = []

    def search(self, query, location=None, limit=5, page=1, options=None):
        self.options_seen.append(options)
        return ProviderSearchResult(self.jobs, has_more=False)


@pytest.fixture(autouse=True)
def _fresh_cache():
    clear_job_cache()
    yield
    clear_job_cache()


def _use(monkeypatch, provider):
    monkeypatch.setattr("app.domain.jobs.service._build_providers", lambda: [provider])


class TestKeys:
    def test_job_key_ignores_case_punctuation_and_spacing(self):
        assert job_key("ACME GmbH", "Python  Developer (m/w/d)", "Berlin") == job_key(
            "acme gmbh", "python developer m w d", " berlin "
        )

    def test_job_key_differs_by_location(self):
        assert job_key("Acme", "Dev", "Berlin") != job_key("Acme", "Dev", "München")

    def test_unicode_is_preserved(self):
        assert job_key("Müller & Söhne", "Entwickler", "Köln") != job_key("Muller Sohne", "Entwickler", "Koln")

    def test_loose_key_ignores_location_and_differs_from_strict(self):
        assert loose_key("Acme", "Dev") == loose_key("acme", " DEV ")
        assert loose_key("Acme", "Dev") != job_key("Acme", "Dev", "")

    @pytest.mark.parametrize(
        ("left", "right"),
        [
            ("https://www.jobs.example/a/1/?utm_source=x&id=7", "http://jobs.example/a/1?id=7"),
            ("https://jobs.example/a/1#section", "https://jobs.example/a/1"),
        ],
    )
    def test_urls_that_differ_only_by_tracking_are_equal(self, left, right):
        assert normalize_url(left) == normalize_url(right)

    def test_meaningful_query_params_are_kept(self):
        assert normalize_url("https://jobs.example/view?id=1") != normalize_url("https://jobs.example/view?id=2")

    @pytest.mark.parametrize("value", [None, "", "   ", "not a url"])
    def test_unusable_urls_return_none(self, value):
        assert normalize_url(value) is None

    def test_job_dict_exposes_the_key(self):
        job = _job("Dev")
        assert job.to_dict()["job_key"] == job_key("Acme", "Dev", "Berlin")


class TestRecencyDefault:
    def test_default_is_thirty_days(self, monkeypatch):
        monkeypatch.delenv("JOB_DEFAULT_RECENCY_DAYS", raising=False)
        assert default_recency_days() == 30

    @pytest.mark.parametrize(("raw", "expected"), [("10", 10), ("0", None), ("-3", None), ("abc", 30), ("500", 100)])
    def test_env_override(self, monkeypatch, raw, expected):
        monkeypatch.setenv("JOB_DEFAULT_RECENCY_DAYS", raw)
        assert default_recency_days() == expected

    def test_old_jobs_are_dropped_for_every_provider(self, monkeypatch):
        provider = RecordingProvider([_job("Fresh", days=5), _job("Stale", days=45), _job("Undated")])
        _use(monkeypatch, provider)
        result = search_jobs("dev", limit=10)
        titles = [job["title"] for job in result["results"]]
        assert titles == ["Fresh", "Undated"]  # newest first, undated last, stale gone
        assert result["audit"]["recency_days"] == 30
        assert result["audit"]["filtered_old"] == 1
        assert result["audit"]["undated_kept"] == 1

    def test_effective_window_is_passed_to_providers_that_can_filter(self, monkeypatch):
        provider = RecordingProvider([_job("Fresh", days=1)])
        _use(monkeypatch, provider)
        search_jobs("dev")
        assert provider.options_seen[0].published_since_days == 30

    def test_explicit_window_wins_over_default(self, monkeypatch):
        provider = RecordingProvider([_job("Fresh", days=5), _job("Mid", days=45)])
        _use(monkeypatch, provider)
        titles = [
            job["title"] for job in search_jobs("dev", options=JobSearchOptions(published_since_days=60))["results"]
        ]
        assert titles == ["Fresh", "Mid"]

    def test_include_old_disables_the_filter(self, monkeypatch):
        provider = RecordingProvider([_job("Fresh", days=5), _job("Stale", days=400)])
        _use(monkeypatch, provider)
        result = search_jobs("dev", include_old=True)
        assert [job["title"] for job in result["results"]] == ["Fresh", "Stale"]
        assert result["audit"]["recency_days"] is None
        assert provider.options_seen[0].published_since_days is None

    def test_filter_does_not_leak_between_cached_variants(self, monkeypatch):
        provider = RecordingProvider([_job("Fresh", days=5), _job("Stale", days=400)])
        _use(monkeypatch, provider)
        assert len(search_jobs("dev")["results"]) == 1
        assert len(search_jobs("dev", include_old=True)["results"]) == 2
        assert len(search_jobs("dev")["results"]) == 1


class TestAppliedExclusion:
    def test_excluded_jobs_never_reach_the_page(self, monkeypatch):
        provider = RecordingProvider([_job("Applied", days=1), _job("Open", days=2)])
        _use(monkeypatch, provider)
        result = search_jobs("dev", exclude=lambda job: job.title == "Applied", exclude_token="t1")
        assert [job["title"] for job in result["results"]] == ["Open"]
        assert result["audit"]["excluded_applied"] == 1
        assert result["total"] == 1  # pagination counts only what is shown

    def test_cache_is_partitioned_by_exclusion_token(self, monkeypatch):
        provider = RecordingProvider([_job("Applied", days=1), _job("Open", days=2)])
        _use(monkeypatch, provider)
        hidden = search_jobs("dev", exclude=lambda job: job.title == "Applied", exclude_token="user-a")
        shown = search_jobs("dev")
        again = search_jobs("dev", exclude=lambda job: job.title == "Applied", exclude_token="user-a")
        assert [j["title"] for j in hidden["results"]] == ["Open"]
        assert [j["title"] for j in shown["results"]] == ["Applied", "Open"]
        assert again["audit"]["cached"] is True


class TestTrackerMatching:
    def _tracker(self):
        return ApplicationTracker()

    def test_strict_key_matches_only_the_same_location(self):
        tracker = self._tracker()
        tracker.create(
            {"user_id": "u", "company": "Acme", "position": "Dev", "job_key": job_key("Acme", "Dev", "Berlin")}
        )
        tracked, _ = tracker.job_match_filter("u")
        assert tracked(_job("Dev", "Acme", "Berlin"))
        assert not tracked(_job("Dev", "Acme", "München")), "same title elsewhere is a different posting"

    def test_url_match_ignores_tracking_parameters(self):
        tracker = self._tracker()
        tracker.create(
            {"user_id": "u", "company": "X", "position": "Y", "job_url": "https://www.jobs.example/a?utm_source=m"}
        )
        tracked, _ = tracker.job_match_filter("u")
        assert tracked(_job("Whatever", "Other", "Hamburg", url="https://jobs.example/a"))

    def test_manual_entry_without_key_or_url_matches_loosely(self):
        tracker = self._tracker()
        tracker.create({"user_id": "u", "company": "Acme", "position": "Dev"})
        tracked, _ = tracker.job_match_filter("u")
        assert tracked(_job("dev", "ACME", "Anywhere"))
        assert not tracked(_job("Designer", "Acme", "Berlin"))

    def test_other_users_applications_are_ignored(self):
        tracker = self._tracker()
        tracker.create({"user_id": "alice", "company": "Acme", "position": "Dev"})
        tracked, _ = tracker.job_match_filter("bob")
        assert not tracked(_job("Dev", "Acme", "Berlin"))

    def test_token_changes_when_the_tracked_set_changes(self):
        tracker = self._tracker()
        _, before = tracker.job_match_filter("u")
        tracker.create({"user_id": "u", "company": "Acme", "position": "Dev"})
        _, after = tracker.job_match_filter("u")
        assert before != after

    def test_status_lookup_reports_the_tracked_status(self):
        tracker = self._tracker()
        created = tracker.create({"user_id": "u", "company": "Acme", "position": "Dev", "status": "interview"})
        lookup = tracker.status_by_job("u")
        assert lookup(_job("Dev", "Acme", "Berlin").to_dict()) == "interview"
        assert lookup(_job("Other", "Zed", "Berlin").to_dict()) is None
        assert created.status == "interview"


class TestTrackerUpdate:
    def test_updates_notes_follow_up_and_url(self):
        tracker = ApplicationTracker()
        app = tracker.create({"user_id": "u", "company": "Acme", "position": "Dev"})
        updated = tracker.update(
            app.application_id,
            {"notes": "Spoke with HR", "follow_up_date": "2026-11-01", "job_url": "https://jobs.example/1"},
        )
        assert (updated.notes, updated.follow_up_date, updated.job_url) == (
            "Spoke with HR",
            "2026-11-01",
            "https://jobs.example/1",
        )
        assert updated.updated_at >= app.created_at

    def test_null_clears_optional_fields(self):
        tracker = ApplicationTracker()
        app = tracker.create(
            {"user_id": "u", "company": "A", "position": "B", "notes": "x", "follow_up_date": "2026-11-01"}
        )
        cleared = tracker.update(app.application_id, {"notes": None, "follow_up_date": None})
        assert cleared.notes == ""
        assert cleared.follow_up_date is None

    @pytest.mark.parametrize("bad", ["tomorrow", "2026-13-40", "", 5])
    def test_rejects_invalid_follow_up(self, bad):
        tracker = ApplicationTracker()
        app = tracker.create({"user_id": "u", "company": "A", "position": "B"})
        with pytest.raises(ValueError, match="follow_up_date"):
            tracker.update(app.application_id, {"follow_up_date": bad})

    def test_accepts_iso_datetime(self):
        tracker = ApplicationTracker()
        app = tracker.create({"user_id": "u", "company": "A", "position": "B"})
        assert tracker.update(app.application_id, {"follow_up_date": "2026-11-01T09:30:00Z"}).follow_up_date

    def test_protected_fields_cannot_be_changed(self):
        tracker = ApplicationTracker()
        app = tracker.create({"user_id": "u", "company": "A", "position": "B"})
        with pytest.raises(ValueError, match="No editable fields"):
            tracker.update(app.application_id, {"user_id": "attacker", "job_key": "x"})
        assert tracker.get(app.application_id).user_id == "u"

    @pytest.mark.parametrize("field", ["company", "position"])
    def test_required_fields_cannot_be_emptied(self, field):
        tracker = ApplicationTracker()
        app = tracker.create({"user_id": "u", "company": "A", "position": "B"})
        with pytest.raises(ValueError, match="must not be empty"):
            tracker.update(app.application_id, {field: "  "})

    def test_unknown_status_is_rejected(self):
        tracker = ApplicationTracker()
        app = tracker.create({"user_id": "u", "company": "A", "position": "B"})
        with pytest.raises(ValueError, match="Unsupported status"):
            tracker.update(app.application_id, {"status": "ghosted"})
