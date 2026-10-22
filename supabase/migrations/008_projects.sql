-- 008: projects, and which projects each Administrator / Support Engineer works on.
-- Customers are never assigned projects. Administrators see every project. Safe to run more than once.

create table if not exists projects (
  id          uuid primary key default gen_random_uuid(),
  name        text not null,
  created_at  timestamptz not null default now()
);
create unique index if not exists projects_name_key on projects(lower(name));

create table if not exists user_projects (
  user_id     uuid not null references profiles(id) on delete cascade,
  project_id  uuid not null references projects(id) on delete cascade,
  primary key (user_id, project_id)
);
create index if not exists user_projects_project_idx on user_projects(project_id);

-- the existing organization becomes the first project, and current staff work on it
insert into projects(name)
select value from settings where key = 'organization_name'
on conflict do nothing;

insert into user_projects(user_id, project_id)
select p.id, pr.id from profiles p cross join projects pr
 where p.role in ('admin', 'manager') and lower(pr.name) = lower((select value from settings where key = 'organization_name'))
on conflict do nothing;

alter table projects enable row level security;
alter table user_projects enable row level security;
revoke all on projects, user_projects from anon, authenticated;
grant all on projects, user_projects to service_role;
