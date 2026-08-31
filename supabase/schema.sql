-- Musanga on Supabase Postgres.
--
-- GENERATED FILE - do not edit. Regenerate with:
--     python3 supabase/generate_schema.py
--
-- The source of truth is the SQLite schema in musanga/db.py. Everything here
-- is a mechanical translation of it, so the database the tests run against and
-- the database production runs on are the same shape.
--
-- Conventions carried over unchanged:
--   * money is integer ngwee (1 ZMW = 100 ngwee); only the view layer divides
--   * timestamps are epoch seconds as bigint, written by db.now()
--   * flags are smallint 0/1, because that is what the queries compare against
--   * references (MSG-xxxxxx, AGR-xxxxxx) are the human handle; ids are internal
--
-- Applying it is idempotent: every statement is IF NOT EXISTS or an
-- ADD COLUMN IF NOT EXISTS, so it doubles as the migration for a database that
-- already holds data.


CREATE TABLE IF NOT EXISTS users (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  role          text NOT NULL CHECK (role IN ('shipper','driver','ops')),
  name          text NOT NULL,
  phone         text NOT NULL UNIQUE,
  email         text,
  company       text,
  password_hash text NOT NULL,
  created_at    bigint NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
  token      text PRIMARY KEY,
  user_id    bigint NOT NULL REFERENCES users(id),
  created_at bigint NOT NULL
);

CREATE TABLE IF NOT EXISTS vehicles (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  driver_id   bigint NOT NULL REFERENCES users(id),
  equipment_key text NOT NULL,
  plate       text NOT NULL,
  home_zone   text NOT NULL,
  is_online   smallint NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS orders (
  id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ref                  text NOT NULL UNIQUE,
  shipper_id           bigint NOT NULL REFERENCES users(id),
  driver_id            bigint REFERENCES users(id),
  equipment_key        text NOT NULL,
  service_key          text NOT NULL,
  commodity_key        text NOT NULL DEFAULT 'general',
  from_zone            text NOT NULL,
  to_zone              text NOT NULL,
  pickup_address       text NOT NULL,
  dropoff_address      text NOT NULL,
  recipient_name       text NOT NULL,
  recipient_phone      text NOT NULL,
  goods                text NOT NULL,
  tonnes               double precision NOT NULL DEFAULT 0,
  billed_tonnes        double precision NOT NULL DEFAULT 0,
  distance_km          double precision NOT NULL,
  eta_minutes          bigint NOT NULL,
  total_ngwee          bigint NOT NULL,
  payout_ngwee         bigint NOT NULL,
  payment_method       text NOT NULL,
  payment_status       text NOT NULL DEFAULT 'pending',
  status               text NOT NULL DEFAULT 'placed',
  scheduled_for        bigint,
  proof_note           text,
  created_at           bigint NOT NULL
);

CREATE TABLE IF NOT EXISTS hires (
  id               bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ref              text NOT NULL UNIQUE,
  hirer_id         bigint NOT NULL REFERENCES users(id),
  plant_key        text NOT NULL,
  site_zone        text NOT NULL,
  site_address     text NOT NULL,
  site_contact     text NOT NULL,
  site_phone       text NOT NULL,
  purpose          text NOT NULL,
  days             bigint NOT NULL,
  tier             text NOT NULL,
  depot_zone       text NOT NULL,
  float_km         double precision NOT NULL,
  with_operator    smallint NOT NULL DEFAULT 0,
  with_fuel        smallint NOT NULL DEFAULT 0,
  with_waiver      smallint NOT NULL DEFAULT 1,
  total_ngwee      bigint NOT NULL,
  payment_method   text NOT NULL,
  payment_status   text NOT NULL DEFAULT 'pending',
  status           text NOT NULL DEFAULT 'requested',
  start_on         bigint,
  meter_note       text,
  created_at       bigint NOT NULL
);

CREATE TABLE IF NOT EXISTS hire_events (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  hire_id    bigint NOT NULL REFERENCES hires(id),
  status     text NOT NULL,
  note       text,
  actor      text,
  created_at bigint NOT NULL
);

CREATE TABLE IF NOT EXISTS events (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id   bigint NOT NULL REFERENCES orders(id),
  status     text NOT NULL,
  note       text,
  actor      text,
  created_at bigint NOT NULL
);

CREATE TABLE IF NOT EXISTS fuel_facilities (
  id                bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  driver_id         bigint NOT NULL UNIQUE REFERENCES users(id),
  limit_ngwee       bigint NOT NULL DEFAULT 0,
  outstanding_ngwee bigint NOT NULL DEFAULT 0,
  status            text NOT NULL DEFAULT 'active',
  completed_loads   bigint NOT NULL DEFAULT 0,
  avg_weekly_payout_ngwee bigint NOT NULL DEFAULT 0,
  rebased_at        bigint,
  created_at        bigint NOT NULL
);

CREATE TABLE IF NOT EXISTS fuel_entitlements (
  id                    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id              bigint NOT NULL UNIQUE REFERENCES orders(id),
  driver_id             bigint NOT NULL REFERENCES users(id),
  litres                bigint NOT NULL,
  litres_drawn          bigint NOT NULL DEFAULT 0,
  price_ngwee_per_litre bigint NOT NULL,
  status                text NOT NULL DEFAULT 'open',
  created_at            bigint NOT NULL
);

CREATE TABLE IF NOT EXISTS fuel_draws (
  id                    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  entitlement_id        bigint NOT NULL REFERENCES fuel_entitlements(id),
  driver_id             bigint NOT NULL REFERENCES users(id),
  litres                bigint NOT NULL,
  price_ngwee_per_litre bigint NOT NULL,
  value_ngwee           bigint NOT NULL,
  cost_ngwee_per_litre  bigint,
  station               text,
  drawn_at              bigint NOT NULL
);

CREATE TABLE IF NOT EXISTS settlements (
  id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id             bigint NOT NULL UNIQUE REFERENCES orders(id),
  driver_id            bigint NOT NULL REFERENCES users(id),
  gross_ngwee          bigint NOT NULL,
  fuel_deduction_ngwee bigint NOT NULL DEFAULT 0,
  net_ngwee            bigint NOT NULL,
  settled_at           bigint NOT NULL
);

CREATE TABLE IF NOT EXISTS insurance_policies (
  id                   bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id             bigint NOT NULL UNIQUE REFERENCES orders(id),
  commodity_key        text NOT NULL,
  declared_value_ngwee bigint NOT NULL,
  rate_bp              bigint NOT NULL,
  premium_ngwee        bigint NOT NULL,
  commission_ngwee     bigint NOT NULL,
  insurer              text,
  policy_ref           text,
  status               text NOT NULL DEFAULT 'quoted',
  created_at           bigint NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_orders_shipper ON orders(shipper_id);

CREATE INDEX IF NOT EXISTS idx_orders_driver  ON orders(driver_id);

CREATE INDEX IF NOT EXISTS idx_orders_status  ON orders(status);

CREATE INDEX IF NOT EXISTS idx_events_order   ON events(order_id);

CREATE TABLE IF NOT EXISTS order_stops (
  id              bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id        bigint NOT NULL REFERENCES orders(id),
  seq             bigint NOT NULL,
  node_key        text NOT NULL,
  address         text NOT NULL,
  recipient_name  text NOT NULL,
  recipient_phone text NOT NULL,
  tonnes          double precision NOT NULL DEFAULT 0,
  discharged_kg   bigint,
  status          text NOT NULL DEFAULT 'pending',
  proof_note      text,
  completed_at    bigint
);

CREATE TABLE IF NOT EXISTS order_documents (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id    bigint NOT NULL REFERENCES orders(id),
  doc_key     text NOT NULL,
  name        text NOT NULL,
  owner       text NOT NULL,
  stage       text NOT NULL,
  mandatory   smallint NOT NULL DEFAULT 1,
  note        text,
  status      text NOT NULL DEFAULT 'outstanding',
  reference   text,
  filed_by    text,
  filed_at    bigint,
  expires_on  bigint,
  UNIQUE (order_id, doc_key)
);

CREATE TABLE IF NOT EXISTS order_positions (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  order_id   bigint NOT NULL REFERENCES orders(id),
  lat        double precision NOT NULL,
  lng        double precision NOT NULL,
  node_key   text,
  place      text,
  km_done    double precision,
  km_left    double precision,
  source     text NOT NULL DEFAULT 'driver',
  note       text,
  created_at bigint NOT NULL
);

CREATE TABLE IF NOT EXISTS contracts (
  id                  bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ref                 text NOT NULL UNIQUE,
  shipper_id          bigint NOT NULL REFERENCES users(id),
  name                text NOT NULL,
  commodity_key       text NOT NULL,
  equipment_key       text NOT NULL,
  from_zone           text NOT NULL,
  to_zone             text NOT NULL,
  tonnes_committed    double precision NOT NULL,
  tonnes_called_off   double precision NOT NULL DEFAULT 0,
  rate_ngwee_per_tonne bigint NOT NULL,
  currency            text NOT NULL DEFAULT 'ZMW',
  tolerance_pct       double precision NOT NULL DEFAULT 0.5,
  starts_on           bigint NOT NULL,
  ends_on             bigint NOT NULL,
  status              text NOT NULL DEFAULT 'active',
  created_at          bigint NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_stops_order     ON order_stops(order_id);

CREATE INDEX IF NOT EXISTS idx_docs_order      ON order_documents(order_id);

CREATE INDEX IF NOT EXISTS idx_positions_order ON order_positions(order_id);

CREATE INDEX IF NOT EXISTS idx_contracts_ship  ON contracts(shipper_id);

CREATE INDEX IF NOT EXISTS idx_hires_hirer     ON hires(hirer_id);

CREATE INDEX IF NOT EXISTS idx_hires_status    ON hires(status);

CREATE INDEX IF NOT EXISTS idx_hire_events     ON hire_events(hire_id);

CREATE INDEX IF NOT EXISTS idx_entitlements_dr ON fuel_entitlements(driver_id);

CREATE INDEX IF NOT EXISTS idx_draws_driver    ON fuel_draws(driver_id);

CREATE INDEX IF NOT EXISTS idx_settlements_dr  ON settlements(driver_id);

CREATE TABLE IF NOT EXISTS kyc_profiles (
  user_id        bigint PRIMARY KEY REFERENCES users(id),
  entity_type    text NOT NULL DEFAULT 'limited',
  legal_name     text,
  trading_name   text,
  reg_number     text,
  tin            text,
  vat_number     text,
  vat_registered smallint NOT NULL DEFAULT 0,
  cross_border   smallint NOT NULL DEFAULT 0,
  country        text NOT NULL DEFAULT 'ZM',
  address        text,
  sector         text,
  updated_at     bigint NOT NULL
);

CREATE TABLE IF NOT EXISTS kyc_people (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id       bigint NOT NULL REFERENCES users(id),
  full_name     text NOT NULL,
  position      text NOT NULL DEFAULT 'Director',
  id_type       text NOT NULL DEFAULT 'nrc',
  id_number     text NOT NULL,
  nationality   text NOT NULL DEFAULT 'ZM',
  date_of_birth text,
  ownership_pct double precision NOT NULL DEFAULT 0,
  is_control    smallint NOT NULL DEFAULT 0,
  created_at    bigint NOT NULL
);

CREATE TABLE IF NOT EXISTS kyc_documents (
  id          bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id     bigint NOT NULL REFERENCES users(id),
  doc_key     text NOT NULL,
  name        text NOT NULL,
  reference   text,
  filename    text,
  mime        text,
  size_bytes  bigint NOT NULL DEFAULT 0,
  content     text,
  status      text NOT NULL DEFAULT 'filed',
  note        text,
  issued_on   text,
  expires_on  text,
  filed_at    bigint NOT NULL,
  reviewed_at bigint,
  UNIQUE (user_id, doc_key)
);

CREATE TABLE IF NOT EXISTS kyc_events (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  user_id    bigint NOT NULL REFERENCES users(id),
  status     text NOT NULL,
  note       text,
  actor      text,
  created_at bigint NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_kyc_people_user ON kyc_people(user_id);

CREATE INDEX IF NOT EXISTS idx_kyc_docs_user   ON kyc_documents(user_id);

CREATE INDEX IF NOT EXISTS idx_kyc_events_user ON kyc_events(user_id);

CREATE TABLE IF NOT EXISTS agreements (
  id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ref                text NOT NULL UNIQUE,
  kind               text NOT NULL,
  title              text NOT NULL,
  body               text NOT NULL,
  body_hash          text NOT NULL,
  counterparty       text NOT NULL,
  counterparty_email text,
  counterparty_phone text,
  account_id         bigint REFERENCES users(id),
  order_ref          text,
  hire_ref           text,
  created_by         bigint NOT NULL REFERENCES users(id),
  status             text NOT NULL DEFAULT 'draft',
  token              text NOT NULL UNIQUE,
  expires_at         bigint,
  sent_at            bigint,
  viewed_at          bigint,
  signed_at          bigint,
  signer_name        text,
  signer_title       text,
  signer_email       text,
  signature_type     text,
  signature          text,
  signed_ip          text,
  signed_agent       text,
  decline_reason     text,
  countersigned_at   bigint,
  countersigned_by   bigint REFERENCES users(id),
  countersignature   text,
  created_at         bigint NOT NULL
);

CREATE TABLE IF NOT EXISTS agreement_views (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  agreement_id bigint NOT NULL REFERENCES agreements(id),
  view_token   text NOT NULL UNIQUE,
  viewer_email text,
  ip           text,
  agent        text,
  seconds      bigint NOT NULL DEFAULT 0,
  max_section  bigint NOT NULL DEFAULT 0,
  sections     bigint NOT NULL DEFAULT 0,
  downloaded   smallint NOT NULL DEFAULT 0,
  signed       smallint NOT NULL DEFAULT 0,
  opened_at    bigint NOT NULL,
  last_seen_at bigint NOT NULL
);

CREATE TABLE IF NOT EXISTS agreement_events (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  agreement_id bigint NOT NULL REFERENCES agreements(id),
  event        text NOT NULL,
  actor        text,
  ip           text,
  agent        text,
  note         text,
  created_at   bigint NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_agreements_account ON agreements(account_id);

CREATE INDEX IF NOT EXISTS idx_agreements_status  ON agreements(status);

CREATE INDEX IF NOT EXISTS idx_agreement_events   ON agreement_events(agreement_id);

CREATE INDEX IF NOT EXISTS idx_agreement_views    ON agreement_views(agreement_id);

CREATE TABLE IF NOT EXISTS quotes (
  id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ref                text NOT NULL UNIQUE,
  token              text NOT NULL UNIQUE,
  status             text NOT NULL DEFAULT 'sent',
  equipment_key      text NOT NULL,
  service_key        text NOT NULL,
  commodity_key      text NOT NULL,
  from_zone          text NOT NULL,
  to_zone            text NOT NULL,
  tonnes             double precision NOT NULL DEFAULT 0,
  stops_json         text,
  pickup_address     text,
  dropoff_address    text,
  goods              text,
  total_ngwee        bigint NOT NULL,
  net_ngwee          bigint NOT NULL,
  vat_ngwee          bigint NOT NULL DEFAULT 0,
  currency           text NOT NULL DEFAULT 'ZMW',
  distance_km        double precision NOT NULL DEFAULT 0,
  eta_minutes        bigint NOT NULL DEFAULT 0,
  counterparty       text NOT NULL,
  counterparty_email text,
  counterparty_phone text,
  payment_method     text NOT NULL,
  payment_ref        text,
  proof_note         text,
  paid_at            bigint,
  paid_by            bigint REFERENCES users(id),
  order_ref          text,
  note               text,
  document_name      text,
  document_mime      text,
  document_size      bigint,
  document_content   text,
  require_signature  bigint NOT NULL DEFAULT 1,
  require_payment    bigint NOT NULL DEFAULT 0,
  signed_at          bigint,
  signer_name        text,
  signer_email       text,
  signature          text,
  signed_ip          text,
  reminder_days      text,
  last_reminded_at   bigint,
  reminder_count     bigint NOT NULL DEFAULT 0,
  created_by         bigint NOT NULL REFERENCES users(id),
  created_at         bigint NOT NULL,
  sent_at            bigint,
  viewed_at          bigint,
  accepted_at        bigint,
  expires_at         bigint
);

CREATE INDEX IF NOT EXISTS idx_quotes_status  ON quotes(status);

CREATE INDEX IF NOT EXISTS idx_quotes_created ON quotes(created_by);

CREATE TABLE IF NOT EXISTS quote_views (
  id           bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  quote_id     bigint NOT NULL REFERENCES quotes(id),
  view_token   text NOT NULL UNIQUE,
  viewer_email text,
  ip           text,
  agent        text,
  seconds      bigint NOT NULL DEFAULT 0,
  downloaded   smallint NOT NULL DEFAULT 0,
  signed       smallint NOT NULL DEFAULT 0,
  opened_at    bigint NOT NULL,
  last_seen_at bigint NOT NULL
);

CREATE TABLE IF NOT EXISTS quote_events (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  quote_id   bigint NOT NULL REFERENCES quotes(id),
  event      text NOT NULL,
  actor      text,
  ip         text,
  agent      text,
  note       text,
  created_at bigint NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_quote_views  ON quote_views(quote_id);

CREATE INDEX IF NOT EXISTS idx_quote_events ON quote_events(quote_id);

CREATE TABLE IF NOT EXISTS rfps (
  id                 bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  ref                text NOT NULL UNIQUE,
  title              text NOT NULL,
  corridor           text NOT NULL,
  from_place         text NOT NULL,
  to_place           text NOT NULL,
  commodity          text NOT NULL,
  equipment          text NOT NULL,
  tonnes_total       double precision NOT NULL DEFAULT 0,
  trucks_needed      bigint NOT NULL DEFAULT 0,
  loading_from       text,
  loading_to         text,
  currency           text NOT NULL DEFAULT 'ZMW',
  target_ngwee_per_tonne bigint,
  cover_min          text,
  notes              text,
  terms_body         text NOT NULL,
  terms_hash         text NOT NULL,
  status             text NOT NULL DEFAULT 'open',
  closes_at          bigint,
  created_by         bigint NOT NULL REFERENCES users(id),
  created_at         bigint NOT NULL
);

CREATE TABLE IF NOT EXISTS rfp_invites (
  id            bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  rfp_id        bigint NOT NULL REFERENCES rfps(id),
  token         text NOT NULL UNIQUE,
  carrier_name  text NOT NULL,
  carrier_email text,
  carrier_phone text,
  account_id    bigint REFERENCES users(id),
  status        text NOT NULL DEFAULT 'sent',
  sent_at       bigint,
  opened_at     bigint,
  submitted_at  bigint,
  declined_at   bigint,
  decline_reason text,
  created_at    bigint NOT NULL
);

CREATE TABLE IF NOT EXISTS rfp_bids (
  id                    bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  rfp_id                bigint NOT NULL REFERENCES rfps(id),
  invite_id             bigint NOT NULL REFERENCES rfp_invites(id),
  rate_ngwee_per_tonne  bigint NOT NULL,
  currency              text NOT NULL DEFAULT 'ZMW',
  trucks_offered        bigint NOT NULL DEFAULT 0,
  capacity_tonnes       double precision NOT NULL DEFAULT 0,
  available_from        text,
  available_to          text,
  notes                 text,
  signer_name           text NOT NULL,
  signer_title          text,
  signer_email          text,
  signature             text,
  terms_hash            text NOT NULL,
  ip                    text,
  agent                 text,
  status                text NOT NULL DEFAULT 'submitted',
  awarded_at            bigint,
  awarded_by            bigint REFERENCES users(id),
  created_at            bigint NOT NULL
);

CREATE TABLE IF NOT EXISTS rfp_events (
  id         bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
  rfp_id     bigint NOT NULL REFERENCES rfps(id),
  invite_id  bigint REFERENCES rfp_invites(id),
  bid_id     bigint REFERENCES rfp_bids(id),
  event      text NOT NULL,
  actor      text,
  ip         text,
  agent      text,
  note       text,
  created_at bigint NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rfp_invites_rfp ON rfp_invites(rfp_id);

CREATE INDEX IF NOT EXISTS idx_rfp_bids_rfp    ON rfp_bids(rfp_id);

CREATE INDEX IF NOT EXISTS idx_rfp_events_rfp  ON rfp_events(rfp_id);

-- ------------------------------------------------ later additions
-- Columns that arrived after the first release. In SQLite these are
-- applied by inspection; Postgres says it in one line.
alter table orders add column if not exists contract_id bigint REFERENCES contracts(id);
alter table orders add column if not exists currency text NOT NULL DEFAULT 'ZMW';
alter table orders add column if not exists corridor text;
alter table orders add column if not exists is_export smallint NOT NULL DEFAULT 0;
alter table orders add column if not exists stops_count bigint NOT NULL DEFAULT 0;
alter table orders add column if not exists loaded_kg bigint;
alter table orders add column if not exists discharged_kg bigint;
alter table orders add column if not exists variance_kg bigint;
alter table orders add column if not exists tolerance_pct double precision NOT NULL DEFAULT 0.5;
alter table orders add column if not exists last_lat double precision;
alter table orders add column if not exists last_lng double precision;
alter table orders add column if not exists last_place text;
alter table orders add column if not exists last_ping_at bigint;
alter table users add column if not exists kyc_status text NOT NULL DEFAULT 'unverified';
alter table users add column if not exists kyc_submitted_at bigint;
alter table users add column if not exists kyc_decided_at bigint;
alter table users add column if not exists kyc_note text;
alter table users add column if not exists kyc_reviewed_by bigint;
alter table users add column if not exists account_status text NOT NULL DEFAULT 'active';
alter table agreements add column if not exists require_email smallint NOT NULL DEFAULT 0;
alter table agreements add column if not exists allow_download smallint NOT NULL DEFAULT 1;
alter table agreements add column if not exists link_disabled smallint NOT NULL DEFAULT 0;
alter table agreements add column if not exists esign_consent smallint NOT NULL DEFAULT 0;
alter table agreements add column if not exists authority_attested smallint NOT NULL DEFAULT 0;
alter table agreements add column if not exists auth_method text;
alter table quotes add column if not exists document_name text;
alter table quotes add column if not exists document_mime text;
alter table quotes add column if not exists document_size bigint;
alter table quotes add column if not exists document_content text;
alter table quotes add column if not exists require_signature bigint NOT NULL DEFAULT 1;
alter table quotes add column if not exists require_payment bigint NOT NULL DEFAULT 0;
alter table quotes add column if not exists signed_at bigint;
alter table quotes add column if not exists signer_name text;
alter table quotes add column if not exists signer_email text;
alter table quotes add column if not exists signature text;
alter table quotes add column if not exists signed_ip text;
alter table quotes add column if not exists reminder_days text;
alter table quotes add column if not exists last_reminded_at bigint;
alter table quotes add column if not exists reminder_count bigint NOT NULL DEFAULT 0;
alter table quotes add column if not exists slot_count bigint NOT NULL DEFAULT 1;
alter table quotes add column if not exists carrier_ngwee bigint;
alter table quotes add column if not exists pass_through_ngwee bigint;
alter table quotes add column if not exists reserve_by bigint;
alter table quotes add column if not exists released_at bigint;
alter table quotes add column if not exists conditions_json text;
alter table rfp_bids add column if not exists trucks_json text;
alter table rfps add column if not exists payment_terms text;


-- ---------------------------------------------------------------- security
--
-- Row level security on, with no policies defined. That is not an oversight:
-- the backend connects as the service role, which bypasses RLS entirely, and
-- every other role - including anon, the key that ships to browsers - is
-- denied every row. Authorisation lives in musanga/api.py, which is the only
-- thing that ever talks to this database.
--
-- If Supabase Auth is ever adopted for the browser to query directly, add
-- per-role policies here and nowhere else.

alter table users enable row level security;
alter table sessions enable row level security;
alter table vehicles enable row level security;
alter table orders enable row level security;
alter table hires enable row level security;
alter table hire_events enable row level security;
alter table events enable row level security;
alter table fuel_facilities enable row level security;
alter table fuel_entitlements enable row level security;
alter table fuel_draws enable row level security;
alter table settlements enable row level security;
alter table insurance_policies enable row level security;
alter table order_stops enable row level security;
alter table order_documents enable row level security;
alter table order_positions enable row level security;
alter table contracts enable row level security;
alter table kyc_profiles enable row level security;
alter table kyc_people enable row level security;
alter table kyc_documents enable row level security;
alter table kyc_events enable row level security;
alter table agreements enable row level security;
alter table agreement_views enable row level security;
alter table agreement_events enable row level security;
alter table quotes enable row level security;
alter table quote_views enable row level security;
alter table quote_events enable row level security;
alter table rfps enable row level security;
alter table rfp_invites enable row level security;
alter table rfp_bids enable row level security;
alter table rfp_events enable row level security;
