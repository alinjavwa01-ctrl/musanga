-- Onboarding and paper: who an account belongs to, and what they have signed.
--
-- Two things arrive here that the core schema did not have:
--
--   1. KYC. Signup is four fields, so everything a bank, an insurer or the
--      regulator would ask for is collected afterwards, in the app. An
--      account trades in limited mode until its file is cleared.
--   2. Agreements. Shippers sign by link, without an account, the way they
--      already expect to. The audit trail is the product here - who opened
--      it, from where, and what exact text they signed - so those columns
--      are not nullable decoration, they are the evidence.

-- ============================================================ identity

alter table users add column if not exists kyc_status text not null default 'unverified'
  check (kyc_status in ('unverified','in_review','verified','rejected'));
alter table users add column if not exists kyc_submitted_at timestamptz;
alter table users add column if not exists kyc_decided_at   timestamptz;
alter table users add column if not exists kyc_note         text;
alter table users add column if not exists kyc_reviewed_by  bigint references users(id);
alter table users add column if not exists account_status   text not null default 'active'
  check (account_status in ('active','suspended'));

-- ============================================================ kyc

create table if not exists kyc_profiles (
  user_id        bigint      primary key references users(id) on delete cascade,
  entity_type    text        not null default 'limited'
                 check (entity_type in ('limited','sole_trader','partnership','cooperative','individual')),
  legal_name     text,
  trading_name   text,
  reg_number     text,
  tin            text,
  vat_number     text,
  vat_registered boolean     not null default false,
  cross_border   boolean     not null default false,
  country        text        not null default 'ZM',
  address        text,
  sector         text,
  updated_at     timestamptz not null default now()
);

create table if not exists kyc_people (
  id            bigint      generated always as identity primary key,
  user_id       bigint      not null references users(id) on delete cascade,
  full_name     text        not null,
  position      text        not null default 'Director',
  id_type       text        not null default 'nrc' check (id_type in ('nrc','passport','drivers_licence')),
  id_number     text        not null,
  nationality   text        not null default 'ZM',
  date_of_birth date,
  ownership_pct numeric(5,2) not null default 0 check (ownership_pct between 0 and 100),
  is_control    boolean     not null default false,
  created_at    timestamptz not null default now()
);

create table if not exists kyc_documents (
  id          bigint      generated always as identity primary key,
  user_id     bigint      not null references users(id) on delete cascade,
  doc_key     text        not null,
  name        text        not null,
  reference   text,
  filename    text,
  mime        text,
  size_bytes  bigint      not null default 0,
  -- base64 in SQLite, storage object key in a real deployment
  content     text,
  storage_key text,
  status      text        not null default 'filed' check (status in ('filed','accepted','rejected')),
  note        text,
  issued_on   date,
  expires_on  date,
  filed_at    timestamptz not null default now(),
  reviewed_at timestamptz,
  unique (user_id, doc_key)
);

create table if not exists kyc_events (
  id         bigint      generated always as identity primary key,
  user_id    bigint      not null references users(id) on delete cascade,
  status     text        not null,
  note       text,
  actor      text,
  created_at timestamptz not null default now()
);

create index if not exists idx_kyc_people_user on kyc_people(user_id);
create index if not exists idx_kyc_docs_user   on kyc_documents(user_id);
create index if not exists idx_kyc_events_user on kyc_events(user_id);
create index if not exists idx_users_kyc       on users(kyc_status);

-- ============================================================ agreements

create table if not exists agreements (
  id                 bigint      generated always as identity primary key,
  ref                text        not null unique,
  kind               text        not null check (kind in ('master','shipment','hire','rate_schedule','nda')),
  title              text        not null,
  -- The exact text that was signed, frozen at send. Editing a sent agreement
  -- is not an update, it is a new agreement.
  body               text        not null,
  body_hash          text        not null,
  counterparty       text        not null,
  counterparty_email text,
  counterparty_phone text,
  account_id         bigint      references users(id),
  order_ref          text,
  hire_ref           text,
  created_by         bigint      not null references users(id),
  status             text        not null default 'draft'
                     check (status in ('draft','sent','viewed','signed','declined','void')),
  token              text        not null unique,
  expires_at         timestamptz,
  sent_at            timestamptz,
  viewed_at          timestamptz,
  signed_at          timestamptz,
  signer_name        text,
  signer_title       text,
  signer_email       text,
  signature_type     text check (signature_type in ('drawn','typed')),
  signature          text,
  signed_ip          text,
  signed_agent       text,
  decline_reason     text,
  countersigned_at   timestamptz,
  countersigned_by   bigint references users(id),
  countersignature   text,
  created_at         timestamptz not null default now()
);

-- Every touch on the document, in order. This is the evidence bundle a
-- disputed signature is defended with, so nothing here is ever updated.
create table if not exists agreement_events (
  id           bigint      generated always as identity primary key,
  agreement_id bigint      not null references agreements(id) on delete cascade,
  event        text        not null,
  actor        text,
  ip           text,
  agent        text,
  note         text,
  created_at   timestamptz not null default now()
);

create index if not exists idx_agreements_account on agreements(account_id);
create index if not exists idx_agreements_status  on agreements(status);
create index if not exists idx_agreement_events   on agreement_events(agreement_id, created_at);
