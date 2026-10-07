-- Walled-off storage for the job radar inside the existing Supabase project.
-- Not exposed through the Data API. Only the job-radar edge function reads or writes it,
-- through the database connection, after checking a token hash.
create schema if not exists job_radar;
revoke all on schema job_radar from public, anon, authenticated;

create table if not exists job_radar.config (
  id int primary key default 1 check (id = 1),
  token_hash text not null,
  updated_at timestamptz not null default now()
);

create table if not exists job_radar.swipes (
  job_id text primary key,
  decision text not null check (decision in ('like', 'pass', 'applied', 'interview', 'offer', 'rejected', 'withdrawn', 'superlike')),
  at timestamptz not null default now(),
  device text,
  snapshot jsonb
);

create table if not exists job_radar.events (
  id bigserial primary key,
  kind text not null,
  job_id text,
  payload jsonb,
  at timestamptz not null default now()
);

create table if not exists job_radar.facts (
  key text primary key,
  value text,
  at timestamptz not null default now()
);

alter table job_radar.config enable row level security;
alter table job_radar.swipes enable row level security;
alter table job_radar.events enable row level security;
alter table job_radar.facts enable row level security;
revoke all on all tables in schema job_radar from public, anon, authenticated;

-- insert into job_radar.config (id, token_hash) values (1, '<sha256 of the sync token>')
--   on conflict (id) do update set token_hash = excluded.token_hash, updated_at = now();
