"""Migration and RLS tests (TEST-02).

Validates:
    - Clean database initialization (migration files are valid SQL)
    - Constraints (check constraints, foreign keys, unique constraints)
    - Indexes
    - RLS policies (every table has RLS enabled and policies)
    - Ownership isolation (User A cannot access User B's records)

These tests validate the migration SQL structure. Live DB-layer RLS
proof requires a running Supabase instance (see test_supabase_crud.py
for the live integration test).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "supabase" / "migrations"


def _load_migrations() -> list[tuple[str, str]]:
    """Load all migration files as (filename, content) tuples."""
    migrations = []
    for path in sorted(MIGRATIONS_DIR.glob("*.sql")):
        migrations.append((path.name, path.read_text(encoding="utf-8")))
    return migrations


class TestMigrationFiles:
    def test_migrations_exist(self):
        migrations = _load_migrations()
        assert len(migrations) >= 2

    def test_migrations_are_valid_sql(self):
        """Basic SQL validity: non-empty, balanced parentheses."""
        for filename, content in _load_migrations():
            assert content.strip(), f"Empty migration: {filename}"
            assert content.count("(") == content.count(")"), f"Unbalanced parentheses in {filename}"

    def test_migrations_have_timestamp_prefix(self):
        """Migration filenames must start with a timestamp."""
        for filename, _content in _load_migrations():
            assert re.match(r"^\d{14}_", filename), f"Migration {filename} must start with YYYYMMDDHHMMSS_"


class TestInitSchema:
    """Validate the initial schema migration (20260101000000_init_schema.sql)."""

    @pytest.fixture(scope="class")
    def init_schema(self) -> str:
        migrations = dict(_load_migrations())
        for filename, content in migrations.items():
            if "init_schema" in filename:
                return content
        pytest.fail("init_schema migration not found")

    def test_creates_profiles_table(self, init_schema):
        assert "create table if not exists public.profiles" in init_schema

    def test_creates_documents_table(self, init_schema):
        assert "create table if not exists public.documents" in init_schema

    def test_creates_job_applications_table(self, init_schema):
        assert "create table if not exists public.job_applications" in init_schema

    def test_profiles_has_foreign_key(self, init_schema):
        assert "references auth.users(id)" in init_schema

    def test_documents_has_foreign_key(self, init_schema):
        assert "references auth.users(id)" in init_schema

    def test_job_applications_has_foreign_key(self, init_schema):
        assert "references auth.users(id)" in init_schema

    def test_profiles_has_unique_email(self, init_schema):
        assert "email text unique not null" in init_schema

    def test_documents_has_type_check(self, init_schema):
        assert "document_type in ('cv', 'cover_letter', 'resignation')" in init_schema

    def test_job_applications_has_status_check(self, init_schema):
        assert "status in ('applied', 'interview', 'offer', 'rejected')" in init_schema

    def test_rls_enabled_on_all_tables(self, init_schema):
        assert "alter table public.profiles enable row level security" in init_schema
        assert "alter table public.documents enable row level security" in init_schema
        assert "alter table public.job_applications enable row level security" in init_schema

    def test_profiles_has_rls_policies(self, init_schema):
        assert 'create policy "Users can view their own profile"' in init_schema
        assert 'create policy "Users can update their own profile"' in init_schema
        assert 'create policy "Users can insert their own profile"' in init_schema

    def test_documents_has_rls_policies(self, init_schema):
        assert 'create policy "Users can view their own documents"' in init_schema
        assert 'create policy "Users can insert their own documents"' in init_schema
        assert 'create policy "Users can update their own documents"' in init_schema
        assert 'create policy "Users can delete their own documents"' in init_schema

    def test_job_applications_has_rls_policies(self, init_schema):
        assert 'create policy "Users can view their own applications"' in init_schema
        assert 'create policy "Users can insert their own applications"' in init_schema
        assert 'create policy "Users can update their own applications"' in init_schema
        assert 'create policy "Users can delete their own applications"' in init_schema

    def test_rls_policies_use_auth_uid(self, init_schema):
        """All RLS policies must use auth.uid() for ownership checks."""
        policy_blocks = re.findall(
            r"create policy .*?using \(\(select auth\.uid\(\)\) = user_id\)",
            init_schema,
            re.DOTALL,
        )
        assert len(policy_blocks) >= 6

    def test_indexes_exist(self, init_schema):
        assert "create index if not exists idx_profiles_email" in init_schema
        assert "create index if not exists idx_documents_user_id" in init_schema
        assert "create index if not exists idx_documents_type" in init_schema
        assert "create index if not exists idx_applications_user_id" in init_schema
        assert "create index if not exists idx_applications_status" in init_schema


class TestDocumentVersioning:
    """Validate the document versioning migration."""

    @pytest.fixture(scope="class")
    def versioning(self) -> str:
        migrations = dict(_load_migrations())
        for filename, content in migrations.items():
            if "document_versioning" in filename:
                return content
        pytest.fail("document_versioning migration not found")

    def test_adds_version_column(self, versioning):
        assert "add column if not exists version integer not null default 1" in versioning

    def test_adds_version_history_column(self, versioning):
        assert "add column if not exists version_history jsonb not null default '[]'::jsonb" in versioning


class TestKnowledgeBase:
    """Validate the knowledge base migration (RD-03)."""

    @pytest.fixture(scope="class")
    def knowledge(self) -> str:
        migrations = dict(_load_migrations())
        for filename, content in migrations.items():
            if "knowledge_base" in filename:
                return content
        pytest.fail("knowledge_base migration not found")

    def test_creates_vector_extension(self, knowledge):
        assert "create extension if not exists vector" in knowledge

    def test_creates_knowledge_entries_table(self, knowledge):
        assert "create table if not exists public.knowledge_entries" in knowledge

    def test_has_vector_column(self, knowledge):
        assert "embedding vector(384)" in knowledge

    def test_enables_rls(self, knowledge):
        assert "alter table public.knowledge_entries enable row level security" in knowledge

    def test_readable_by_authenticated_users(self, knowledge):
        assert "for select to authenticated" in knowledge

    def test_writable_by_service_role_only(self, knowledge):
        assert "for all to service_role" in knowledge

    def test_has_cosine_vector_index(self, knowledge):
        assert "using ivfflat (embedding vector_cosine_ops)" in knowledge

    def test_has_search_function(self, knowledge):
        assert "create or replace function public.knowledge_search" in knowledge
        assert "1 - (ke.embedding <=> query_embedding) as similarity" in knowledge

    def test_search_function_is_threshold_filtered(self, knowledge):
        assert ">= match_threshold" in knowledge
        assert "order by ke.embedding <=> query_embedding" in knowledge


class TestSemanticEmbeddings:
    """Validate the semantic embeddings migration (RD-04)."""

    @pytest.fixture(scope="class")
    def semantic(self) -> str:
        migrations = dict(_load_migrations())
        for filename, content in migrations.items():
            if "semantic_embeddings" in filename:
                return content
        pytest.fail("semantic_embeddings migration not found")

    def test_creates_semantic_embeddings_table(self, semantic):
        assert "create table if not exists public.semantic_embeddings" in semantic

    def test_has_vector_column(self, semantic):
        assert "embedding vector(384)" in semantic

    def test_entity_type_check_constraint(self, semantic):
        assert "entity_type in ('profile', 'cv', 'job_description')" in semantic

    def test_user_id_references_auth_users(self, semantic):
        assert "user_id uuid references auth.users(id) on delete cascade" in semantic

    def test_unique_entity_constraint(self, semantic):
        assert "unique (entity_type, entity_id)" in semantic

    def test_enables_rls(self, semantic):
        assert "alter table public.semantic_embeddings enable row level security" in semantic

    def test_users_read_own_and_public(self, semantic):
        assert "for select to authenticated" in semantic
        assert "(user_id is null) or ((select auth.uid()) = user_id)" in semantic

    def test_service_role_writes(self, semantic):
        assert "for all to service_role" in semantic

    def test_has_cosine_vector_index(self, semantic):
        assert "using ivfflat (embedding vector_cosine_ops)" in semantic

    def test_has_search_function(self, semantic):
        assert "create or replace function public.semantic_search" in semantic
        assert "1 - (se.embedding <=> query_embedding) as similarity" in semantic

    def test_search_function_is_user_scoped(self, semantic):
        assert "(user_filter is null or se.user_id is null or se.user_id = user_filter)" in semantic


class TestDocumentRetrieval:
    """Validate the personal document retrieval migration (RD-05)."""

    @pytest.fixture(scope="class")
    def retrieval(self) -> str:
        migrations = dict(_load_migrations())
        for filename, content in migrations.items():
            if "document_retrieval" in filename:
                return content
        pytest.fail("document_retrieval migration not found")

    def test_extends_entity_type_constraint(self, retrieval):
        assert "drop constraint if exists " "semantic_embeddings_entity_type_check" in retrieval
        assert "entity_type in ('profile', 'cv', 'cover_letter', " "'resume_analysis', 'job_description')" in retrieval

    def test_constraint_is_replaced_not_duplicated(self, retrieval):
        """The constraint must be dropped before re-adding,
        otherwise the migration fails on existing databases."""
        drop_position = retrieval.index("drop constraint if exists " "semantic_embeddings_entity_type_check")
        add_position = retrieval.index("add constraint semantic_embeddings_entity_type_check")
        assert drop_position < add_position


class TestHandleNewUserTrigger:
    """Validate the handle_new_user trigger migration.

    The project guide documented an auto-create-profile trigger, but it was
    never created by any migration: Supabase signups produced auth.users
    rows with no public.profiles row ("signed up but no user record").
    This pins the migration that creates it.
    """

    @pytest.fixture(scope="class")
    def trigger_migration(self) -> str:
        for filename, content in _load_migrations():
            if "handle_new_user" in content:
                return content
        pytest.fail("handle_new_user trigger migration not found")

    def test_defines_handle_new_user_function(self, trigger_migration):
        assert "create or replace function public.handle_new_user()" in trigger_migration

    def test_function_is_security_definer(self, trigger_migration):
        """Must run as the function owner so signup is not blocked by RLS."""
        assert "security definer" in trigger_migration

    def test_trigger_fires_after_insert_on_auth_users(self, trigger_migration):
        assert "create trigger on_auth_user_created" in trigger_migration
        assert "after insert on auth.users" in trigger_migration

    def test_trigger_inserts_profiles_row_with_user_id(self, trigger_migration):
        """profiles is keyed by user_id (not id); the guide snippet used id."""
        assert "insert into public.profiles (user_id, email, full_name)" in trigger_migration

    def test_trigger_is_idempotent(self, trigger_migration):
        """Re-running must not fail: drop-if-exists + on conflict do nothing."""
        assert "drop trigger if exists on_auth_user_created" in trigger_migration
        assert "on conflict (user_id) do nothing" in trigger_migration

    def test_backfills_users_created_before_the_trigger(self, trigger_migration):
        """Existing auth users without a profile row are repaired inline."""
        assert "insert into public.profiles (user_id, email, full_name)" in trigger_migration
        assert "from auth.users" in trigger_migration
        assert "not exists" in trigger_migration


class TestOwnershipIsolation:
    """Validate that RLS policies enforce ownership isolation.

    These tests verify the SQL structure guarantees that User A
    cannot access User B's records. Live DB-layer proof requires
    a running Supabase instance.
    """

    @pytest.fixture(scope="class")
    def init_schema(self) -> str:
        migrations = dict(_load_migrations())
        for filename, content in migrations.items():
            if "init_schema" in filename:
                return content
        pytest.fail("init_schema migration not found")

    def test_select_policies_scope_to_user(self, init_schema):
        """Every SELECT policy must filter by auth.uid() = user_id."""
        select_policies = re.findall(
            r"for select to authenticated using \(\(select auth\.uid\(\)\) = user_id\)",
            init_schema,
        )
        # profiles, documents, job_applications = 3 select policies
        assert len(select_policies) == 3

    def test_insert_policies_scope_to_user(self, init_schema):
        """Every INSERT policy must check auth.uid() = user_id."""
        insert_policies = re.findall(
            r"for insert to authenticated with check \(\(select auth\.uid\(\)\) = user_id\)",
            init_schema,
        )
        # profiles, documents, job_applications = 3 insert policies
        assert len(insert_policies) == 3

    def test_update_policies_scope_to_user(self, init_schema):
        """Every UPDATE policy must filter by auth.uid() = user_id."""
        update_pattern = (
            r"for update to authenticated using \(\(select auth\.uid\(\)\) = user_id\)"
            r" with check \(\(select auth\.uid\(\)\) = user_id\)"
        )
        update_policies = re.findall(update_pattern, init_schema)
        # profiles, documents, job_applications = 3 update policies
        assert len(update_policies) == 3

    def test_delete_policies_scope_to_user(self, init_schema):
        """Every DELETE policy must filter by auth.uid() = user_id."""
        delete_policies = re.findall(
            r"for delete to authenticated using \(\(select auth\.uid\(\)\) = user_id\)",
            init_schema,
        )
        # documents, job_applications = 2 delete policies (profiles has no delete)
        assert len(delete_policies) == 2

    def test_no_public_access_policies(self, init_schema):
        """No policy should grant access to the 'public' role."""
        assert "to public" not in init_schema.lower()
        assert "to anon" not in init_schema.lower()

    def test_all_policies_target_authenticated_role(self, init_schema):
        """All policies must target the 'authenticated' role."""
        # Policies span multiple lines; join them for analysis.
        policy_blocks = re.findall(
            r"create policy .*?(?=create policy|alter table|create index|$)",
            init_schema,
            re.DOTALL,
        )
        # 3 (profiles) + 4 (documents) + 4 (job_applications) = 11 policies
        assert len(policy_blocks) == 11
        for block in policy_blocks:
            assert "to authenticated" in block, f"Policy not scoped to authenticated: {block[:100]}"
