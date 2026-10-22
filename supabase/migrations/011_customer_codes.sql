-- 011: every customer has a short code (Apple -> A, a second "A..." customer -> AM, ...).
-- Record numbers use it: INCA-1, PRBA-1, CHGA-1, RELA-1, DEFA-1. Safe to run more than once.

alter table projects add column if not exists code text;
create unique index if not exists projects_code_key on projects(code) where code is not null;
