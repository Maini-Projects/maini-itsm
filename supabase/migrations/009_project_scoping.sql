-- 009: every incident, problem, defect, change and release belongs to a project.
-- Existing records and existing Support Engineers / Customers move to the first project (the original organization).
-- Customers can now be assigned projects too (by an Administrator, or by a Support Engineer for their team's customers).
-- Safe to run more than once.

alter table incidents add column if not exists project_id uuid references projects(id);
alter table problems  add column if not exists project_id uuid references projects(id);
alter table defects   add column if not exists project_id uuid references projects(id);
alter table changes   add column if not exists project_id uuid references projects(id);
alter table releases  add column if not exists project_id uuid references projects(id);

do $$
declare first_project uuid := (select id from projects order by created_at limit 1);
begin
  if first_project is not null then
    update incidents set project_id = first_project where project_id is null;
    update problems  set project_id = first_project where project_id is null;
    update defects   set project_id = first_project where project_id is null;
    update changes   set project_id = first_project where project_id is null;
    update releases  set project_id = first_project where project_id is null;
    insert into user_projects(user_id, project_id)
      select id, first_project from profiles where role in ('manager', 'employee')
      on conflict do nothing;
  end if;
end $$;

create index if not exists incidents_project_idx on incidents(project_id);
create index if not exists problems_project_idx  on problems(project_id);
create index if not exists defects_project_idx   on defects(project_id);
create index if not exists changes_project_idx   on changes(project_id);
create index if not exists releases_project_idx  on releases(project_id);
