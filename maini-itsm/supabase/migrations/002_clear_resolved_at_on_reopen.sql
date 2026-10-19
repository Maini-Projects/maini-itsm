-- ============================================================================
-- Migration 002 - clear "resolved at" when an incident is reopened or its approval is rejected
--
-- Bug fixed: when a P1/P2 approval was rejected the incident went back to In Progress but kept
-- its old resolved_at time, which would have distorted SLA reporting. Reopening from Resolved
-- already cleared it.
--
-- This file replaces three functions. Two of them (managers_only, apply_approval_decision) are
-- re-applied unchanged so that a database created from ANY earlier draft of 001 ends up identical.
-- Safe to run more than once.
-- ============================================================================

create or replace function incident_rules() returns trigger language plpgsql as $$
declare sla sla_policies%rowtype;
begin
  new.priority := priority_from(new.impact, new.urgency);

  if tg_op = 'INSERT' then
    new.team_id := (select team_id from profiles where id = new.requester_id);
    new.status  := 'New';
  end if;

  -- SLA clocks (re-computed from creation time if priority changes)
  if tg_op = 'INSERT' or new.priority is distinct from old.priority then
    select * into sla from sla_policies where priority = new.priority;
    new.response_due   := new.created_at + make_interval(mins => sla.response_minutes);
    new.resolution_due := new.created_at + make_interval(mins => sla.resolution_minutes);
  end if;

  if tg_op = 'UPDATE' and new.status is distinct from old.status then
    -- approval gate: P1/P2 must go through Pending Approval, P3/P4 must not
    if old.status = 'Resolved' and new.status = 'Closed' and new.priority in ('P1','P2') then
      raise exception 'approval_required: P1/P2 incidents need manager approval before closing' using errcode = 'P0001';
    end if;
    if old.status = 'Resolved' and new.status = 'Pending Approval' and new.priority in ('P3','P4') then
      raise exception 'approval_not_needed: P3/P4 incidents close directly' using errcode = 'P0001';
    end if;
    if new.status = 'Assigned' and new.assignee_id is null then
      raise exception 'assignee_required: assign someone before moving to Assigned' using errcode = 'P0001';
    end if;
    if new.status = 'In Progress' and new.responded_at is null then new.responded_at := now(); end if;
    if new.status = 'Resolved' then
      if coalesce(trim(new.resolution_notes), '') = '' then
        raise exception 'resolution_notes_required' using errcode = 'P0001';
      end if;
      new.resolved_at := now();
    end if;
    if new.status = 'Closed' then new.closed_at := now(); end if;
    if new.status = 'In Progress' and old.status in ('Resolved','Pending Approval') then new.resolved_at := null; end if;
  end if;
  return new;
end $$;

create or replace function managers_only() returns trigger language plpgsql as $$
declare who uuid := (to_jsonb(new) ->> tg_argv[0])::uuid; r user_role;
begin
  select role into r from profiles where id = who and status = 'active';
  if r is null or r = 'employee' then
    raise exception 'forbidden: only managers and admins can raise %', tg_table_name using errcode = 'P0001';
  end if;
  return new;
end $$;

create or replace function apply_approval_decision() returns trigger language plpgsql as $$
declare dr user_role; dt uuid;
begin
  if old.status = 'pending' and new.status in ('approved','rejected') then
    if new.decided_by is null then
      raise exception 'decider_required' using errcode = 'P0001';
    end if;
    -- only the right person may decide: admin approvals need an admin; incident
    -- approvals need an admin or the manager of the incident's own team
    select role, team_id into dr, dt from profiles where id = new.decided_by and status = 'active';
    if dr is null
       or (old.approver_role = 'admin'   and dr <> 'admin')
       or (old.approver_role = 'manager' and not (dr = 'admin' or (dr = 'manager' and dt = old.team_id))) then
      raise exception 'forbidden: this user cannot decide this approval' using errcode = 'P0001';
    end if;
    -- separation of duties for managers: a manager cannot decide their own request
    -- (admins have no restrictions, so an admin may decide their own)
    if new.decided_by = old.requested_by and dr <> 'admin' then
      raise exception 'self_approval: you cannot approve your own request' using errcode = 'P0001';
    end if;
    new.decided_at := now();

    if new.record_type = 'incident' then
      update incidents set status = case when new.status = 'approved' then 'Closed' else 'In Progress' end,
                           updated_by = new.decided_by where id = new.record_id;
    elsif new.record_type = 'change' then
      update changes   set status = case when new.status = 'approved' then 'Scheduled' else 'Draft' end,
                           updated_by = new.decided_by where id = new.record_id;
    elsif new.record_type = 'release' then
      update releases  set status = case when new.status = 'approved' then 'Approved' else 'Planned' end,
                           updated_by = new.decided_by where id = new.record_id;
    end if;
  end if;
  return new;
end $$;
