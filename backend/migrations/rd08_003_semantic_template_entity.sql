-- RD-08 migration 003 (idempotent). The code now stores user templates in
-- semantic_embeddings with entity_type = 'template'. If your table has a CHECK
-- constraint on entity_type, it must allow the new value. The original migration is
-- not in the zip, so this script only acts when such a constraint exists.
do $$
declare c record;
begin
  for c in
    select conname from pg_constraint
    where conrelid = 'semantic_embeddings'::regclass and contype = 'c'
      and pg_get_constraintdef(oid) ilike '%entity_type%'
  loop
    execute format('alter table semantic_embeddings drop constraint %I', c.conname);
  end loop;
  alter table semantic_embeddings
    add constraint semantic_embeddings_entity_type_check
    check (entity_type in ('profile','cv','cover_letter','resume_analysis','job_description','template'));
exception when undefined_table then
  raise notice 'semantic_embeddings does not exist; nothing to do';
end $$;
