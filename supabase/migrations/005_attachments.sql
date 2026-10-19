-- ============================================================================
-- Migration 005 - file attachments (images and documents, 1 MB each)
--
-- The files themselves live in a private Supabase Storage bucket called "attachments". This table keeps
-- one row per file: which record it belongs to, its name, type, size and who uploaded it. Nobody can
-- reach the bucket or this table directly; the API checks who may see a record before it hands out a file.
-- Works for incidents, problems, defects, changes and releases.
--
-- Safe to run more than once. Run it in the Supabase SQL editor after 001 to 004.
-- ============================================================================

create table if not exists attachments (
  id            uuid primary key default gen_random_uuid(),
  record_type   text not null check (record_type in ('incident', 'problem', 'defect', 'change', 'release')),
  record_id     uuid not null,
  file_name     text not null,
  content_type  text not null,
  size_bytes    integer not null check (size_bytes > 0 and size_bytes <= 1048576),   -- 1 MB
  storage_path  text not null unique,
  uploaded_by   uuid not null references profiles(id),
  created_at    timestamptz not null default now()
);
create index if not exists attachments_record_idx on attachments(record_type, record_id);

alter table attachments enable row level security;
revoke all on attachments from anon, authenticated;
grant all on attachments to service_role;

-- The private bucket (only on Supabase; a plain Postgres has no storage schema). The bucket enforces the
-- 1 MB limit and the allowed file types too, so even a direct upload could not get around them.
do $$
begin
  if to_regclass('storage.buckets') is not null then
    insert into storage.buckets (id, name, public, file_size_limit, allowed_mime_types)
    values ('attachments', 'attachments', false, 1048576, array[
      'image/png', 'image/jpeg', 'image/gif', 'image/webp',
      'application/pdf', 'text/plain', 'text/csv',
      'application/msword', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
      'application/vnd.ms-excel', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      'application/vnd.ms-powerpoint', 'application/vnd.openxmlformats-officedocument.presentationml.presentation'
    ])
    on conflict (id) do update
      set public = false,
          file_size_limit = excluded.file_size_limit,
          allowed_mime_types = excluded.allowed_mime_types;
  end if;
end $$;
