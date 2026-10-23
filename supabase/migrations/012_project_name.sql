-- 012: a customer can have a separate, optional project name (shown in the Customers table).
alter table projects add column if not exists project_name text;
