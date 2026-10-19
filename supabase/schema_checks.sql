-- Business-rule checks for 001_foundation_schema.sql.
-- Run against a database where the schema is applied and the test users do not exist yet.
-- Everything runs in one transaction that is rolled back, so it leaves no data behind.
\set ON_ERROR_STOP on
begin;

create schema t;
create table t.results(name text, ok boolean, detail text);
create function t.check(n text, cond boolean, d text default '') returns void language sql as
$$ insert into t.results values (n, coalesce(cond, false), d) $$;
create function t.fails(n text, q text, expect text) returns void language plpgsql as $$
begin
  execute q;
  insert into t.results values (n, false, 'no error raised');
exception when others then
  insert into t.results values (n, position(expect in sqlerrm) > 0, sqlerrm);
end $$;

-- ---- people: admin, one manager + one employee per team -------------------
insert into auth.users(id, email) values
  ('00000000-0000-0000-0000-0000000000a1','admin@x'),
  ('00000000-0000-0000-0000-0000000000b1','devmgr@x'),
  ('00000000-0000-0000-0000-0000000000c1','devemp@x'),
  ('00000000-0000-0000-0000-0000000000b2','supmgr@x'),
  ('00000000-0000-0000-0000-0000000000c2','supemp@x'),
  ('00000000-0000-0000-0000-0000000000d1','second-dev-mgr@x'),
  ('00000000-0000-0000-0000-0000000000d2','no-team@x');

insert into profiles(id, email, full_name, role, team_id) values
  ('00000000-0000-0000-0000-0000000000a1','admin@x',  'Alice Admin',  'admin',    null),
  ('00000000-0000-0000-0000-0000000000b1','devmgr@x', 'Dev Manager',  'manager',  (select id from teams where name='Development')),
  ('00000000-0000-0000-0000-0000000000c1','devemp@x', 'Dev Employee', 'employee', (select id from teams where name='Development')),
  ('00000000-0000-0000-0000-0000000000b2','supmgr@x', 'Sup Manager',  'manager',  (select id from teams where name='Support')),
  ('00000000-0000-0000-0000-0000000000c2','supemp@x', 'Sup Employee', 'employee', (select id from teams where name='Support'));

select t.fails('second manager in one team is rejected',
  $$insert into profiles(id,email,full_name,role,team_id) values ('00000000-0000-0000-0000-0000000000d1','second-dev-mgr@x','X','manager',(select id from teams where name='Development'))$$,
  'one_manager_per_team');
select t.fails('employee without a team is rejected',
  $$insert into profiles(id,email,full_name,role,team_id) values ('00000000-0000-0000-0000-0000000000d2','no-team@x','X','employee',null)$$,
  'team_required');

-- ---- priority matrix ------------------------------------------------------
select t.check('matrix High/High = P1',     priority_from('High','High')     = 'P1');
select t.check('matrix High/Medium = P2',   priority_from('High','Medium')   = 'P2');
select t.check('matrix Medium/High = P2',   priority_from('Medium','High')   = 'P2');
select t.check('matrix Medium/Medium = P3', priority_from('Medium','Medium') = 'P3');
select t.check('matrix High/Low = P3',      priority_from('High','Low')      = 'P3');
select t.check('matrix Low/High = P3',      priority_from('Low','High')      = 'P3');
select t.check('matrix Low/Low = P4',       priority_from('Low','Low')       = 'P4');

-- ---- incident creation: priority, team, SLA clocks ------------------------
insert into incidents(id, short_description, requester_id, impact, urgency) values
  ('10000000-0000-0000-0000-000000000001','P1 incident A','00000000-0000-0000-0000-0000000000c1','High','High'),
  ('10000000-0000-0000-0000-000000000002','P1 incident B','00000000-0000-0000-0000-0000000000c1','High','High'),
  ('10000000-0000-0000-0000-000000000003','P1 incident C','00000000-0000-0000-0000-0000000000c1','High','High'),
  ('10000000-0000-0000-0000-000000000004','P3 incident D','00000000-0000-0000-0000-0000000000c2','Medium','Medium'),
  ('10000000-0000-0000-0000-000000000005','P4 incident E','00000000-0000-0000-0000-0000000000c2','Low','Low'),
  ('10000000-0000-0000-0000-000000000006','P1 incident F','00000000-0000-0000-0000-0000000000c1','High','High');

select t.check('incident priority computed (P1)',
  (select priority from incidents where id='10000000-0000-0000-0000-000000000001') = 'P1');
select t.check('incident team copied from requester',
  (select team_id from incidents where id='10000000-0000-0000-0000-000000000001') = (select id from teams where name='Development')
  and (select team_id from incidents where id='10000000-0000-0000-0000-000000000004') = (select id from teams where name='Support'));
select t.check('incident starts as New with an INC- number',
  (select status = 'New' and number like 'INC-1%' from incidents where id='10000000-0000-0000-0000-000000000001'));
select t.check('P1 SLA: respond 15 min, resolve 4 h',
  (select response_due - created_at = interval '15 minutes' and resolution_due - created_at = interval '4 hours'
     from incidents where id='10000000-0000-0000-0000-000000000001'));
select t.check('P3 SLA: respond 4 h, resolve 3 days',
  (select response_due - created_at = interval '4 hours' and resolution_due - created_at = interval '3 days'
     from incidents where id='10000000-0000-0000-0000-000000000004'));
select t.check('P4 SLA: respond 1 day, resolve 5 days',
  (select response_due - created_at = interval '1 day' and resolution_due - created_at = interval '5 days'
     from incidents where id='10000000-0000-0000-0000-000000000005'));

-- priority change recomputes the clocks
update incidents set impact='Low', urgency='Low' where id='10000000-0000-0000-0000-000000000006';
select t.check('priority change recomputes SLA clocks',
  (select priority = 'P4' and resolution_due - created_at = interval '5 days'
     from incidents where id='10000000-0000-0000-0000-000000000006'));

-- ---- P1 incident A: manager works it, admin approves ----------------------
select t.fails('cannot skip New -> Closed',
  $$update incidents set status='Closed' where id='10000000-0000-0000-0000-000000000001'$$, 'invalid_transition');
select t.fails('Assigned needs an assignee',
  $$update incidents set status='Assigned' where id='10000000-0000-0000-0000-000000000001'$$, 'assignee_required');
update incidents set status='Assigned', assignee_id='00000000-0000-0000-0000-0000000000b1', updated_by='00000000-0000-0000-0000-0000000000b1'
  where id='10000000-0000-0000-0000-000000000001';
update incidents set status='In Progress', updated_by='00000000-0000-0000-0000-0000000000b1'
  where id='10000000-0000-0000-0000-000000000001';
select t.check('first move to In Progress stamps responded_at',
  (select responded_at is not null from incidents where id='10000000-0000-0000-0000-000000000001'));
update incidents set status='Pending' where id='10000000-0000-0000-0000-000000000001';
update incidents set status='In Progress' where id='10000000-0000-0000-0000-000000000001';
select t.fails('Resolved needs resolution notes',
  $$update incidents set status='Resolved' where id='10000000-0000-0000-0000-000000000001'$$, 'resolution_notes_required');
update incidents set status='Resolved', resolution_notes='Restarted the posting workers.', updated_by='00000000-0000-0000-0000-0000000000b1'
  where id='10000000-0000-0000-0000-000000000001';
select t.check('Resolved stamps resolved_at',
  (select resolved_at is not null from incidents where id='10000000-0000-0000-0000-000000000001'));
select t.fails('P1 cannot close without approval',
  $$update incidents set status='Closed' where id='10000000-0000-0000-0000-000000000001'$$, 'approval_required');
update incidents set status='Pending Approval', updated_by='00000000-0000-0000-0000-0000000000b1'
  where id='10000000-0000-0000-0000-000000000001';
select t.check('P1 resolution opens a manager approval for the right team',
  (select count(*) = 1 from approvals a join incidents i on i.id = a.record_id
    where a.record_id='10000000-0000-0000-0000-000000000001' and a.status='pending'
      and a.approver_role='manager' and a.team_id = i.team_id
      and a.requested_by='00000000-0000-0000-0000-0000000000b1'));
select t.fails('requester cannot approve own request',
  $$update approvals set status='approved', decided_by='00000000-0000-0000-0000-0000000000b1' where record_id='10000000-0000-0000-0000-000000000001'$$, 'self_approval');
select t.fails('manager of the other team cannot approve',
  $$update approvals set status='approved', decided_by='00000000-0000-0000-0000-0000000000b2' where record_id='10000000-0000-0000-0000-000000000001'$$, 'forbidden');
select t.fails('employee cannot approve',
  $$update approvals set status='approved', decided_by='00000000-0000-0000-0000-0000000000c1' where record_id='10000000-0000-0000-0000-000000000001'$$, 'forbidden');
update approvals set status='approved', decided_by='00000000-0000-0000-0000-0000000000a1', comment='ok'
  where record_id='10000000-0000-0000-0000-000000000001';
select t.check('approval closes the incident',
  (select status = 'Closed' and closed_at is not null from incidents where id='10000000-0000-0000-0000-000000000001'));
select t.check('approval records who and when',
  (select status = 'approved' and decided_at is not null and decided_by='00000000-0000-0000-0000-0000000000a1'
     from approvals where record_id='10000000-0000-0000-0000-000000000001'));

-- ---- P1 incident B: admin works it, own-team manager approves -------------
update incidents set status='Assigned', assignee_id='00000000-0000-0000-0000-0000000000a1', updated_by='00000000-0000-0000-0000-0000000000a1' where id='10000000-0000-0000-0000-000000000002';
update incidents set status='In Progress' where id='10000000-0000-0000-0000-000000000002';
update incidents set status='Resolved', resolution_notes='Patched.' where id='10000000-0000-0000-0000-000000000002';
update incidents set status='Pending Approval', updated_by='00000000-0000-0000-0000-0000000000a1' where id='10000000-0000-0000-0000-000000000002';
select t.fails('other team manager cannot approve incident B',
  $$update approvals set status='approved', decided_by='00000000-0000-0000-0000-0000000000b2' where record_id='10000000-0000-0000-0000-000000000002'$$, 'forbidden');
update approvals set status='approved', decided_by='00000000-0000-0000-0000-0000000000b1' where record_id='10000000-0000-0000-0000-000000000002';
select t.check('own-team manager can approve (incident B closed)',
  (select status = 'Closed' from incidents where id='10000000-0000-0000-0000-000000000002'));

-- ---- P1 incident C: rejection sends it back to In Progress ----------------
update incidents set status='Assigned', assignee_id='00000000-0000-0000-0000-0000000000b1', updated_by='00000000-0000-0000-0000-0000000000b1' where id='10000000-0000-0000-0000-000000000003';
update incidents set status='In Progress' where id='10000000-0000-0000-0000-000000000003';
update incidents set status='Resolved', resolution_notes='Maybe fixed.' where id='10000000-0000-0000-0000-000000000003';
update incidents set status='Pending Approval', updated_by='00000000-0000-0000-0000-0000000000b1' where id='10000000-0000-0000-0000-000000000003';
update approvals set status='rejected', decided_by='00000000-0000-0000-0000-0000000000a1', comment='Not verified' where record_id='10000000-0000-0000-0000-000000000003';
select t.check('rejection returns the incident to In Progress and clears resolved_at (migration 002)',
  (select status = 'In Progress' and resolved_at is null from incidents where id='10000000-0000-0000-0000-000000000003'));
select t.check('a decided approval does not block a new one',
  (select count(*) from approvals where record_id='10000000-0000-0000-0000-000000000003' and status='pending') = 0);

-- ---- P3 incident D: no approval needed ------------------------------------
update incidents set status='Assigned', assignee_id='00000000-0000-0000-0000-0000000000b2' where id='10000000-0000-0000-0000-000000000004';
update incidents set status='In Progress' where id='10000000-0000-0000-0000-000000000004';
update incidents set status='Resolved', resolution_notes='Reset password.' where id='10000000-0000-0000-0000-000000000004';
select t.fails('P3 cannot go to Pending Approval',
  $$update incidents set status='Pending Approval' where id='10000000-0000-0000-0000-000000000004'$$, 'approval_not_needed');
update incidents set status='Closed' where id='10000000-0000-0000-0000-000000000004';
select t.check('P3 closes directly with no approval row',
  (select status = 'Closed' from incidents where id='10000000-0000-0000-0000-000000000004')
  and (select count(*) = 0 from approvals where record_id='10000000-0000-0000-0000-000000000004'));

-- ---- P4 incident E: reopen clears resolved_at -----------------------------
update incidents set status='Assigned', assignee_id='00000000-0000-0000-0000-0000000000b2' where id='10000000-0000-0000-0000-000000000005';
update incidents set status='In Progress' where id='10000000-0000-0000-0000-000000000005';
update incidents set status='Resolved', resolution_notes='Done.' where id='10000000-0000-0000-0000-000000000005';
update incidents set status='In Progress' where id='10000000-0000-0000-0000-000000000005';
select t.check('reopening clears resolved_at',
  (select resolved_at is null and status = 'In Progress' from incidents where id='10000000-0000-0000-0000-000000000005'));

-- ---- problems: anyone raises, no approval ---------------------------------
insert into problems(id, title, raised_by) values
  ('20000000-0000-0000-0000-000000000001','Recurring latency','00000000-0000-0000-0000-0000000000c1');
select t.check('problem gets PRB- number, team and starts Identified',
  (select number like 'PRB-%' and status = 'Identified' and team_id = (select id from teams where name='Development')
     from problems where id='20000000-0000-0000-0000-000000000001'));
select t.fails('problem cannot skip states',
  $$update problems set status='Closed' where id='20000000-0000-0000-0000-000000000001'$$, 'invalid_transition');
update problems set status='Investigating' where id='20000000-0000-0000-0000-000000000001';
update problems set status='Root Cause Identified', root_cause='Slow query' where id='20000000-0000-0000-0000-000000000001';
update problems set status='Fix Planned' where id='20000000-0000-0000-0000-000000000001';
update problems set status='Resolved' where id='20000000-0000-0000-0000-000000000001';
update problems set status='Closed' where id='20000000-0000-0000-0000-000000000001';
select t.check('problem walks all six states with no approval',
  (select status = 'Closed' from problems where id='20000000-0000-0000-0000-000000000001')
  and (select count(*) = 0 from approvals where record_type = 'problem'));

-- ---- changes: manager raises, admin approves ------------------------------
select t.fails('employee cannot raise a change',
  $$insert into changes(title, requester_id) values ('x','00000000-0000-0000-0000-0000000000c1')$$, 'forbidden');
insert into changes(id, title, requester_id, type, risk) values
  ('30000000-0000-0000-0000-000000000003','Admin change','00000000-0000-0000-0000-0000000000a1','Normal','Low');
update changes set status='Submitted' where id='30000000-0000-0000-0000-000000000003';
update changes set status='Under Review' where id='30000000-0000-0000-0000-000000000003';
update changes set status='Approval Pending', updated_by='00000000-0000-0000-0000-0000000000a1' where id='30000000-0000-0000-0000-000000000003';
update approvals set status='approved', decided_by='00000000-0000-0000-0000-0000000000a1' where record_id='30000000-0000-0000-0000-000000000003';
select t.check('admin can raise a change and approve their own request',
  (select status = 'Scheduled' from changes where id='30000000-0000-0000-0000-000000000003'));
insert into releases(id, name, owner_id) values
  ('40000000-0000-0000-0000-000000000002','Admin release','00000000-0000-0000-0000-0000000000a1');
update releases set status='Under Review', updated_by='00000000-0000-0000-0000-0000000000a1' where id='40000000-0000-0000-0000-000000000002';
update approvals set status='approved', decided_by='00000000-0000-0000-0000-0000000000a1' where record_id='40000000-0000-0000-0000-000000000002';
select t.check('admin can raise a release and approve their own request',
  (select status = 'Approved' from releases where id='40000000-0000-0000-0000-000000000002'));
insert into changes(id, title, requester_id, type, risk) values
  ('30000000-0000-0000-0000-000000000001','Deploy fix','00000000-0000-0000-0000-0000000000b1','Emergency','High'),
  ('30000000-0000-0000-0000-000000000002','Config update','00000000-0000-0000-0000-0000000000b2','Normal','Medium');
select t.check('manager raises a change: CHG- number, Draft, own team',
  (select number like 'CHG-%' and status = 'Draft' and team_id = (select id from teams where name='Development')
     from changes where id='30000000-0000-0000-0000-000000000001'));
update changes set status='Submitted' where id='30000000-0000-0000-0000-000000000001';
update changes set status='Under Review' where id='30000000-0000-0000-0000-000000000001';
update changes set status='Approval Pending', updated_by='00000000-0000-0000-0000-0000000000b1' where id='30000000-0000-0000-0000-000000000001';
select t.check('change in Approval Pending opens an admin approval',
  (select count(*) = 1 from approvals where record_id='30000000-0000-0000-0000-000000000001' and approver_role='admin' and status='pending'));
select t.fails('a manager cannot approve a change',
  $$update approvals set status='approved', decided_by='00000000-0000-0000-0000-0000000000b2' where record_id='30000000-0000-0000-0000-000000000001'$$, 'forbidden');
select t.fails('the requesting manager cannot approve their own change',
  $$update approvals set status='approved', decided_by='00000000-0000-0000-0000-0000000000b1' where record_id='30000000-0000-0000-0000-000000000001'$$, 'forbidden');
update approvals set status='approved', decided_by='00000000-0000-0000-0000-0000000000a1' where record_id='30000000-0000-0000-0000-000000000001';
select t.check('admin approval moves the change to Scheduled',
  (select status = 'Scheduled' from changes where id='30000000-0000-0000-0000-000000000001'));
update changes set status='Implementation' where id='30000000-0000-0000-0000-000000000001';
update changes set status='Implemented'    where id='30000000-0000-0000-0000-000000000001';
update changes set status='Closed'         where id='30000000-0000-0000-0000-000000000001';
select t.check('approved change completes to Closed',
  (select status = 'Closed' from changes where id='30000000-0000-0000-0000-000000000001'));
update changes set status='Submitted' where id='30000000-0000-0000-0000-000000000002';
update changes set status='Under Review' where id='30000000-0000-0000-0000-000000000002';
update changes set status='Approval Pending', updated_by='00000000-0000-0000-0000-0000000000b2' where id='30000000-0000-0000-0000-000000000002';
update approvals set status='rejected', decided_by='00000000-0000-0000-0000-0000000000a1' where record_id='30000000-0000-0000-0000-000000000002';
select t.check('rejected change returns to Draft',
  (select status = 'Draft' from changes where id='30000000-0000-0000-0000-000000000002'));

-- ---- releases: manager raises, admin approves -----------------------------
select t.fails('employee cannot raise a release',
  $$insert into releases(name, owner_id) values ('x','00000000-0000-0000-0000-0000000000c1')$$, 'forbidden');
insert into releases(id, name, owner_id, environment) values
  ('40000000-0000-0000-0000-000000000001','Finance patch','00000000-0000-0000-0000-0000000000b1','Production');
select t.check('release gets REL- number and starts Planned',
  (select number like 'REL-%' and status = 'Planned' from releases where id='40000000-0000-0000-0000-000000000001'));
update releases set status='Under Review', updated_by='00000000-0000-0000-0000-0000000000b1' where id='40000000-0000-0000-0000-000000000001';
select t.check('release Under Review opens an admin approval',
  (select count(*) = 1 from approvals where record_id='40000000-0000-0000-0000-000000000001' and approver_role='admin' and status='pending'));
select t.fails('manager cannot approve a release',
  $$update approvals set status='approved', decided_by='00000000-0000-0000-0000-0000000000b2' where record_id='40000000-0000-0000-0000-000000000001'$$, 'forbidden');
update approvals set status='approved', decided_by='00000000-0000-0000-0000-0000000000a1' where record_id='40000000-0000-0000-0000-000000000001';
select t.check('admin approval moves the release to Approved',
  (select status = 'Approved' from releases where id='40000000-0000-0000-0000-000000000001'));
update releases set status='Ready to Deploy' where id='40000000-0000-0000-0000-000000000001';
update releases set status='Deployment'      where id='40000000-0000-0000-0000-000000000001';
update releases set status='Validated'       where id='40000000-0000-0000-0000-000000000001';
update releases set status='Closed'          where id='40000000-0000-0000-0000-000000000001';
select t.check('approved release completes to Closed',
  (select status = 'Closed' from releases where id='40000000-0000-0000-0000-000000000001'));

-- ---- audit trail ----------------------------------------------------------
select t.check('audit log records incident status changes with actor and old/new values',
  exists (select 1 from audit_log
           where table_name = 'incidents' and record_id = '10000000-0000-0000-0000-000000000001'
             and action = 'UPDATE' and actor_id = '00000000-0000-0000-0000-0000000000a1'
             and old_values ->> 'status' = 'Pending Approval' and new_values ->> 'status' = 'Closed'));
select t.check('audit log records approvals and creations',
  exists (select 1 from audit_log where table_name = 'approvals')
  and exists (select 1 from audit_log where table_name = 'incidents' and action = 'INSERT'));
select t.fails('audit log cannot be edited',  $$update audit_log set action = 'X'$$, 'append-only');
select t.fails('audit log cannot be deleted', $$delete from audit_log$$, 'append-only');

-- ---- security posture -----------------------------------------------------
select t.check('row level security is on for every table',
  (select count(*) = 0 from pg_class c join pg_namespace n on n.oid = c.relnamespace
    where n.nspname = 'public' and c.relkind = 'r' and not c.relrowsecurity));

-- ---- report ---------------------------------------------------------------
select case when ok then 'PASS' else 'FAIL' end as result, name, case when ok then '' else detail end as detail
  from t.results order by ok, name;
select count(*) filter (where ok) as passed, count(*) filter (where not ok) as failed from t.results;

rollback;
