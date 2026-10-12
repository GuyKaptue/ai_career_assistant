from __future__ import annotations

from typing import Any, Callable

import httpx

from app.core.config import settings, validate_supabase_storage
from app.core.errors import ConfigurationError, DatabaseError


def build_supabase_client(base_url: str, api_key: str) -> httpx.Client:
    """Build an authenticated Supabase PostgREST client.

    Single source of truth for the client construction
    (base URL, JSON headers, ``return=representation``,
    service-role auth, 20s timeout) shared by every
    Supabase-backed store. Callers resolve their own
    settings and unconfigured-error type so per-module
    behavior is preserved.
    """
    return httpx.Client(
        base_url=base_url.rstrip("/"),
        headers={
            "Content-Type": "application/json",
            "Accept": "application/json",
            # PostgREST only returns the written row when asked.
            # Without this, POST/PATCH return 201 with an empty
            # body and response.json() fails even though the
            # write succeeded.
            "Prefer": "return=representation",
            "apikey": api_key,
            "Authorization": f"Bearer {api_key}",
        },
        timeout=20.0,
    )


class InMemoryRepository:
    def __init__(self) -> None:
        self._records: dict[str, Any] = {}

    def create(self, record: Any) -> Any:
        self._records[record.id if hasattr(record, "id") else record.application_id] = record
        return record

    def get(self, record_id: str) -> Any | None:
        return self._records.get(record_id)

    def list_for_user(self, user_id: str) -> list[Any]:
        return [record for record in self._records.values() if getattr(record, "user_id", None) == user_id]

    def update(self, record_id: str, payload: dict[str, Any]) -> Any:
        record = self._records[record_id]
        for field_name, value in payload.items():
            if hasattr(record, field_name):
                setattr(record, field_name, value)
        return record

    def delete(self, record_id: str) -> bool:
        if record_id in self._records:
            del self._records[record_id]
            return True
        return False


class SupabaseRepository:
    def __init__(self, table_name: str, model_factory: Callable[..., Any], key_field: str = "id") -> None:
        self.table_name = table_name
        self.model_factory = model_factory
        self.key_field = key_field
        self._memory: dict[str, dict[str, Any]] = {}
        if settings.supabase_url and settings.supabase_service_role_key:
            validate_supabase_storage()

    def _client(self) -> httpx.Client:
        if not settings.supabase_url or not settings.supabase_service_role_key:
            raise ConfigurationError(
                "Supabase persistence is not configured. Set SUPABASE_URL and SUPABASE_SERVICE_ROLE_KEY."
            )

        return build_supabase_client(settings.supabase_url, settings.supabase_service_role_key)

    def _parse_row(self, row: dict[str, Any] | None) -> Any:
        if row is None:
            raise ValueError("Cannot parse an empty row.")
        return self.model_factory(**self._scoped_fields(row))

    def _scoped_fields(self, row: dict[str, Any]) -> dict[str, Any]:
        """Keep only the fields the model constructor accepts.

        Rows carry more than the model does: ``to_dict()`` adds derived
        values such as ``message_count``, and Postgres may return columns the
        domain model does not declare. Passing those straight into the model
        factory raised ``TypeError`` — which crashed chat-session creation
        whenever Supabase was configured.
        """
        import dataclasses

        factory = self.model_factory
        if not dataclasses.is_dataclass(factory):
            return dict(row)
        allowed = {f.name for f in dataclasses.fields(factory)}
        return {key: value for key, value in row.items() if key in allowed}

    def _fallback_create(self, payload: dict[str, Any]) -> Any:
        key = payload.get(self.key_field)
        if key is None:
            key = payload.get("id") or payload.get("application_id") or f"local-{len(self._memory) + 1}"
        record = dict(payload)
        self._memory[str(key)] = record
        return self._parse_row(record)

    def _find_fallback_record(self, record_id: str) -> dict[str, Any] | None:
        if record_id in self._memory:
            return self._memory[record_id]

        for record in self._memory.values():
            if record.get(self.key_field) == record_id:
                return record
        return None

    def _fallback_delete(self, record_id: str) -> bool:
        if record_id in self._memory:
            del self._memory[record_id]
            return True
        for key, record in list(self._memory.items()):
            if record.get(self.key_field) == record_id:
                del self._memory[key]
                return True
        return False

    def _is_missing_table_error(self, detail: str | httpx.Response | Exception) -> bool:
        """True only when the *table itself* is absent.

        Supabase reports two different problems with broadly similar text, and
        conflating them caused silent data loss:

          PGRST205 "Could not find the table 'x' in the schema cache"
              → the table was never created. In-memory fallback is the
                intended graceful degradation for running without a database.
          PGRST204 "Could not find the 'col' column of 'x' in the schema cache"
              → the table exists but the schema is out of date. Writing here
                would be *silently discarded* into memory, so it must raise
                instead.

        Both messages contain "in the schema cache", so the code is used to
        tell them apart rather than the prose.
        """
        text = detail.text if isinstance(detail, httpx.Response) else str(detail)
        lowered = text.lower()
        if "pgrst204" in lowered:
            return False
        if "pgrst205" in lowered:
            return True
        if "'column of" in lowered or "could not find the" in lowered and "column" in lowered:
            return False
        return (
            "could not find the table" in lowered
            or "does not exist" in lowered
            or ("relation" in lowered and "does not exist" in lowered)
        )

    def create(self, payload: dict[str, Any]) -> Any:
        try:
            with self._client() as client:
                response = client.post(f"/rest/v1/{self.table_name}", json=payload)
                if response.status_code >= 400:
                    if self._is_missing_table_error(response):
                        return self._fallback_create(payload)
                    raise DatabaseError(
                        "The database rejected the write.",
                        internal=f"Supabase write failed for {self.table_name}: {response.text}",
                    )
                if not response.content:
                    # PostgREST can answer 201 with an empty body when the
                    # Prefer header is ignored. Merge the request payload with
                    # the key returned by the DB would be ideal, but without a
                    # body we fall back to local parsing so callers still get a
                    # typed record.
                    return self._parse_row(dict(payload))
                data = response.json()
                if isinstance(data, list):
                    if not data:
                        return self._parse_row(dict(payload))
                    return self._parse_row(data[0])
                return self._parse_row(data)
        except (httpx.HTTPError, RuntimeError) as exc:
            if self._is_missing_table_error(exc):
                return self._fallback_create(payload)
            if isinstance(exc, httpx.HTTPError):
                raise DatabaseError("The database could not be reached.", internal=str(exc)) from exc
            raise

    def get(self, record_id: str) -> Any | None:
        try:
            with self._client() as client:
                response = client.get(
                    f"/rest/v1/{self.table_name}",
                    params={self.key_field: f"eq.{record_id}"},
                )
                if response.status_code >= 400:
                    if self._is_missing_table_error(response):
                        row = self._find_fallback_record(record_id)
                        return self._parse_row(row) if row is not None else None
                    raise DatabaseError(
                        "The database read failed.",
                        internal=f"Supabase read failed for {self.table_name}: {response.text}",
                    )
                rows = response.json()
                if not rows:
                    return (
                        self._parse_row(self._find_fallback_record(record_id))
                        if self._find_fallback_record(record_id)
                        else None
                    )
                return self._parse_row(rows[0])
        except (httpx.HTTPError, RuntimeError) as exc:
            if self._is_missing_table_error(exc):
                row = self._find_fallback_record(record_id)
                return self._parse_row(row) if row is not None else None
            if isinstance(exc, httpx.HTTPError):
                raise DatabaseError("The database could not be reached.", internal=str(exc)) from exc
            raise

    def list_for_user(self, user_id: str) -> list[Any]:
        try:
            with self._client() as client:
                response = client.get(
                    f"/rest/v1/{self.table_name}",
                    params={"user_id": f"eq.{user_id}"},
                )
                if response.status_code >= 400:
                    if self._is_missing_table_error(response):
                        return [self._parse_row(row) for row in self._memory.values() if row.get("user_id") == user_id]
                    raise DatabaseError(
                        "The database read failed.",
                        internal=f"Supabase list failed for {self.table_name}: {response.text}",
                    )
                rows = response.json()
                return [self._parse_row(row) for row in rows]
        except (httpx.HTTPError, RuntimeError) as exc:
            if self._is_missing_table_error(exc):
                return [self._parse_row(row) for row in self._memory.values() if row.get("user_id") == user_id]
            if isinstance(exc, httpx.HTTPError):
                raise DatabaseError("The database could not be reached.", internal=str(exc)) from exc
            raise

    def update(self, record_id: str, payload: dict[str, Any]) -> Any:
        try:
            with self._client() as client:
                response = client.patch(
                    f"/rest/v1/{self.table_name}",
                    params={self.key_field: f"eq.{record_id}"},
                    json=payload,
                )
                if response.status_code >= 400:
                    if self._is_missing_table_error(response):
                        row = self._find_fallback_record(record_id)
                        if row is None:
                            raise KeyError(record_id)
                        row.update(payload)
                        return self._parse_row(row)
                    raise DatabaseError(
                        "The database rejected the update.",
                        internal=f"Supabase update failed for {self.table_name}: {response.text}",
                    )
                rows = response.json()
                if not rows:
                    raise KeyError(record_id)
                return self._parse_row(rows[0])
        except (httpx.HTTPError, RuntimeError) as exc:
            if self._is_missing_table_error(exc):
                row = self._find_fallback_record(record_id)
                if row is None:
                    raise KeyError(record_id)
                row.update(payload)
                return self._parse_row(row)
            if isinstance(exc, httpx.HTTPError):
                raise DatabaseError("The database could not be reached.", internal=str(exc)) from exc
            raise

    def delete(self, record_id: str) -> bool:
        """Delete one record by primary key. Returns True when a row existed."""
        try:
            with self._client() as client:
                response = client.delete(
                    f"/rest/v1/{self.table_name}",
                    params={self.key_field: f"eq.{record_id}"},
                )
                if response.status_code >= 400:
                    if self._is_missing_table_error(response):
                        return self._fallback_delete(record_id)
                    raise DatabaseError(
                        "The database rejected the delete.",
                        internal=f"Supabase delete failed for {self.table_name}: {response.text}",
                    )
                # PostgREST returns 204 (no body) on success.
                return True
        except (httpx.HTTPError, RuntimeError) as exc:
            if self._is_missing_table_error(exc):
                return self._fallback_delete(record_id)
            if isinstance(exc, httpx.HTTPError):
                raise DatabaseError("The database could not be reached.", internal=str(exc)) from exc
            raise
