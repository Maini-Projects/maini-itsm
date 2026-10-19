-- ============================================================================
-- Migration 003 - incidents no longer need approval
--
-- Before: P1/P2 incidents went Resolved -> Pending Approval -> Closed (manager or admin approval).
-- Now:    every incident closes directly from Resolved (P1 to P4 alike), like P3/P4 did before.
-- Problems never had an approval. Changes and releases keep theirs (admin approves).
--
-- What this does
--   1. Incidents waiting for approval go back to Resolved and their open approval is removed.
--   2. 'Pending Approval' stops being a valid incident status.
--   3. The database no longer creates an approval when an incident is resolved, and no longer refuses
--      Resolved -> Closed for P1/P2.
-- Old, already decided incident approvals stay in the approvals table as history.
-- Safe to run more than once. Run it in the Supabase SQL editor after 001 and 002.
-- ============================================================================

-- 1. Put incidents that are waiting for approval back to Resolved.
--    (the move needs a transition row, so add it for this clean-up and remove it again below)
insert into workflow_transitions values ('incident', 'Pending Approval', 'Resolved') on conflict do nothing;
update incidents set status = 'Resolved' where status = 'Pending Approval';
delete from approvals where record_type = 'incident' and status = 'pending';

-- 2. No more Pending Approval for incidents.
delete from workflow_transitions
 where record_type = 'incident' and (from_status = 'Pending Approval' or to_status = 'Pending Approval');

-- 3. No approval row is created when an incident is resolved.
drop trigger if exists incidents_approval on incidents;
drop function if exists incident_open_approval();

-- 4. incident_rules without the approval gate (otherwise identical to migration 002).
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
    if new.status = 'In Progress' and old.status = 'Resolved' then new.resolved_at := null; end if;
  end if;
  return new;
end $$;

-- Note: apply_approval_decision() still has an 'incident' branch. It can no longer run, because no
-- incident approvals are created, so it is left as it is.
