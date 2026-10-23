-- Knowledge base articles (one table per customer schema). Run with search_path = <customer schema>, public.
create table kb_articles (
  id          uuid primary key default gen_random_uuid(),
  title       text not null,
  body        text not null default '',
  category    text,
  audience    text not null default 'everyone' check (audience in ('everyone', 'staff')),
  status      text not null default 'draft' check (status in ('draft', 'published')),
  created_by  uuid not null references profiles(id),
  updated_by  uuid references profiles(id),
  created_at  timestamptz not null default now(),
  updated_at  timestamptz not null default now()
);
create index kb_articles_status_idx on kb_articles(status, updated_at desc);
alter table kb_articles enable row level security;
create trigger kb_touch before update on kb_articles for each row execute function touch_updated_at();
