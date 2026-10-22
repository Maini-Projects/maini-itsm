-- 010: every customer gets its own schema. Shared data (users, teams, projects, applications, SLA targets, workflow
-- rules) stays in public; a customer's incidents, problems, defects, changes, releases, approvals, attachments and
-- audit history live in that customer's schema (created by the back end when a project is added).
-- The tables themselves come from backend/app/tenant_sql/*.sql. Safe to run more than once.

alter table projects add column if not exists schema_name text;
create unique index if not exists projects_schema_name_key on projects(schema_name) where schema_name is not null;

-- Audit trigger for customer tables: writes to the audit_log of whichever customer schema is first on the search path.
-- (public.audit_row keeps writing to public.audit_log for users and SLA changes.)
create or replace function tenant_audit_row() returns trigger language plpgsql as $$
declare actor uuid; rid uuid;
begin
  if tg_op = 'DELETE' then
    rid := (to_jsonb(old) ->> 'id')::uuid;
    insert into audit_log(actor_id, action, table_name, record_id, old_values)
    values (null, tg_op, tg_table_name, rid, to_jsonb(old));
    return old;
  end if;
  rid   := (to_jsonb(new) ->> 'id')::uuid;
  actor := coalesce((to_jsonb(new) ->> 'updated_by')::uuid, (to_jsonb(new) ->> 'requester_id')::uuid,
                    (to_jsonb(new) ->> 'raised_by')::uuid, (to_jsonb(new) ->> 'decided_by')::uuid);
  insert into audit_log(actor_id, action, table_name, record_id, old_values, new_values)
  values (actor, tg_op, tg_table_name, rid,
          case when tg_op = 'UPDATE' then to_jsonb(old) end, to_jsonb(new));
  return new;
end $$;
grant execute on function tenant_audit_row() to service_role;
