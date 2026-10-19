-- ============================================================================
-- Migration 004 - defects
--
-- A "Defect" is a bug found in a service (for example in UAT or Production). It is handled like an
-- incident: anyone can raise one, a manager or admin assigns and works it, and it moves
-- New -> Assigned -> In Progress (or Pending) -> Resolved -> Closed (Resolved can be reopened).
-- No approval step and no SLA clock.
--
-- Adds: defects, defect_comments, defect_transitions, the defect rules and the audit trail for defects.
-- Safe to run more than once. Run it in the Supabase SQL editor after 001, 002 and 003.
-- ============================================================================

do $$ begin
  create type defect_severity as enum ('Critical', 'High', 'Medium', 'Low');
exception when duplicate_object then null; end $$;

create sequence if not exists defect_seq start 1;

create table if not exists defects (
  id                  uuid primary key default gen_random_uuid(),
  number              text not null unique default 'DEF-' || lpad(nextval('defect_seq')::text, 4, '0'),
  title               text not null,
  description         text,
  steps_to_reproduce  text,
  expected_result     text,
  actual_result       text,
  raised_by           uuid not null references profiles(id),
  team_id             uuid references teams(id),          -- the reporter's team, set by trigger
  service_id          uuid references services(id),
  severity            defect_severity not null default 'Medium',
  environment         environment not null default 'Production',
  status              text not null default 'New',
  assignee_id         uuid references profiles(id),
  resolution_notes    text,
  resolved_at         timestamptz,
  closed_at           timestamptz,
  created_at          timestamptz not null default now(),
  updated_at          timestamptz not null default now(),
  updated_by          uuid references profiles(id)
);
create index if not exists defects_raised_by_idx on defects(raised_by);
create index if not exists defects_team_status_idx on defects(team_id, status);
create index if not exists defects_assignee_idx on defects(assignee_id);

create table if not exists defect_comments (
  id          uuid primary key default gen_random_uuid(),
  defect_id   uuid not null references defects(id) on delete cascade,
  author_id   uuid not null references profiles(id),
  body        text not null,
  internal    boolean not null default false,   -- internal notes hidden from the reporter
  created_at  timestamptz not null default now()
);
create index if not exists defect_comments_defect_idx on defect_comments(defect_id);

-- allowed status moves (its own table: a new value cannot be added to record_type and used in one script)
create table if not exists defect_transitions (
  from_status  text not null,
  to_status    text not null,
  primary key (from_status, to_status)
);
insert into defect_transitions values
  ('New', 'Assigned'),
  ('Assigned', 'In Progress'),
  ('In Progress', 'Pending'),
  ('Pending', 'In Progress'),
  ('In Progress', 'Resolved'),
  ('Resolved', 'Closed'),
  ('Resolved', 'In Progress')       -- reopen
on conflict do nothing;

-- ---- rules -----------------------------------------------------------------
create or replace function defect_rules() returns trigger language plpgsql as $$
begin
  if tg_op = 'INSERT' then
    new.team_id := (select team_id from profiles where id = new.raised_by);
    new.status  := 'New';
  end if;

  if tg_op = 'UPDATE' and new.status is distinct from old.status then
    if not exists (select 1 from defect_transitions where from_status = old.status and to_status = new.status) then
      raise exception 'invalid_transition: defect cannot move from "%" to "%"', old.status, new.status
        using errcode = 'P0001';
    end if;
    if new.status = 'Assigned' and new.assignee_id is null then
      raise exception 'assignee_required: assign someone before moving to Assigned' using errcode = 'P0001';
    end if;
    if new.status = 'Resolved' then
      if coalesce(trim(new.resolution_notes), '') = '' then
        raise exception 'resolution_notes_required' using errcode = 'P0001';
      end if;
      new.resolved_at := now();
    end if;
    if new.status = 'Closed' then new.closed_at := now(); end if;
    if new.status = 'In Progress' and old.status = 'Resolved' then new.resolved_at := null; end if;
  end if;
  return new;
end $$;

drop trigger if exists defects_rules on defects;
create trigger defects_rules before insert or update on defects for each row execute function defect_rules();
drop trigger if exists defects_touch on defects;
create trigger defects_touch before update on defects for each row execute function touch_updated_at();

-- audit trail (the actor is taken from updated_by / raised_by by audit_row)
drop trigger if exists audit_defects on defects;
create trigger audit_defects after insert or update or delete on defects for each row execute function audit_row();

-- ---- security: same posture as every other table ----------------------------
alter table defects            enable row level security;
alter table defect_comments    enable row level security;
alter table defect_transitions enable row level security;

revoke all on defects, defect_comments, defect_transitions from anon, authenticated;
revoke all on sequence defect_seq from anon, authenticated;
revoke all on function defect_rules() from public, anon, authenticated;

grant all on defects, defect_comments, defect_transitions to service_role;
grant all on sequence defect_seq to service_role;
grant execute on function defect_rules() to service_role;
