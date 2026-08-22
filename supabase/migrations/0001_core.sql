-- Musanga core schema for Supabase Postgres.
--
-- A port of the SQLite schema in musanga/db.py, plus the carrier bundle:
-- fuel facilities, entitlements, draws, settlements and goods-in-transit
-- policies.
--
-- Two conventions carry over from SQLite and must not be broken:
--   * all money is integer ngwee (1 ZMW = 100 ngwee); only the view layer divides
--   * references (MSG-xxxxxx, HIR-xxxxxx) are the human handle, ids are internal
--
-- Where the rules live: POLICY lives in Python (musanga/fuel.py decides how many
-- litres a load is entitled to and how much of a settlement may be netted).
-- INVARIANTS live here, as constraints, so a bug in the caller cannot corrupt
-- the ledger. Do not duplicate the policy into plpgsql - it will drift.

-- ============================================================ identity

create table if not exists users (
  id            bigint generated always as identity primary key,
  role          text        not null check (role in ('shipper','driver','ops')),
  name          text        not null,
  phone         text        not null unique,
  email         text,
  company       text,
  password_hash text        not null,
  created_at    timestamptz not null default now()
);

create table if not exists sessions (
  token      text        primary key,
  user_id    bigint      not null references users(id) on delete cascade,
  created_at timestamptz not null default now()
);
create index if not exists idx_sessions_user on sessions(user_id);

create table if not exists vehicles (
  id            bigint generated always as identity primary key,
  driver_id     bigint  not null references users(id) on delete cascade,
  equipment_key text    not null,
  plate         text    not null,
  home_zone     text    not null,
  is_online     boolean not null default false
);
create index if not exists idx_vehicles_driver on vehicles(driver_id);

-- ============================================================ freight

create table if not exists orders (
  id              bigint generated always as identity primary key,
  ref             text        not null unique,
  shipper_id      bigint      not null references users(id),
  driver_id       bigint      references users(id),
  equipment_key   text        not null,
  service_key     text        not null,
  commodity_key   text        not null default 'general',
  from_zone       text        not null,
  to_zone         text        not null,
  pickup_address  text        not null,
  dropoff_address text        not null,
  recipient_name  text        not null,
  recipient_phone text        not null,
  goods           text        not null,
  tonnes          numeric(10,2) not null default 0,
  billed_tonnes   numeric(10,2) not null default 0,
  distance_km     numeric(10,2) not null,
  eta_minutes     integer     not null,
  total_ngwee     bigint      not null check (total_ngwee >= 0),
  payout_ngwee    bigint      not null check (payout_ngwee >= 0),
  payment_method  text        not null,
  payment_status  text        not null default 'pending',
  status          text        not null default 'placed',
  scheduled_for   timestamptz,
  proof_note      text,
  created_at      timestamptz not null default now(),
  -- The carrier can never be promised more than the shipper is charged.
  constraint payout_within_total check (payout_ngwee <= total_ngwee)
);
create index if not exists idx_orders_shipper on orders(shipper_id);
create index if not exists idx_orders_driver  on orders(driver_id);
create index if not exists idx_orders_status  on orders(status);

create table if not exists events (
  id         bigint generated always as identity primary key,
  order_id   bigint      not null references orders(id) on delete cascade,
  status     text        not null,
  note       text,
  actor      text,
  created_at timestamptz not null default now()
);
create index if not exists idx_events_order on events(order_id);

-- ============================================================ plant hire

create table if not exists hires (
  id             bigint generated always as identity primary key,
  ref            text        not null unique,
  hirer_id       bigint      not null references users(id),
  plant_key      text        not null,
  site_zone      text        not null,
  site_address   text        not null,
  site_contact   text        not null,
  site_phone     text        not null,
  purpose        text        not null,
  days           integer     not null check (days > 0),
  tier           text        not null,
  depot_zone     text        not null,
  float_km       numeric(10,2) not null,
  with_operator  boolean     not null default false,
  with_fuel      boolean     not null default false,
  with_waiver    boolean     not null default true,
  total_ngwee    bigint      not null check (total_ngwee >= 0),
  payment_method text        not null,
  payment_status text        not null default 'pending',
  status         text        not null default 'requested',
  start_on       timestamptz,
  meter_note     text,
  created_at     timestamptz not null default now()
);
create index if not exists idx_hires_hirer  on hires(hirer_id);
create index if not exists idx_hires_status on hires(status);

create table if not exists hire_events (
  id         bigint generated always as identity primary key,
  hire_id    bigint      not null references hires(id) on delete cascade,
  status     text        not null,
  note       text,
  actor      text,
  created_at timestamptz not null default now()
);
create index if not exists idx_hire_events on hire_events(hire_id);

-- ============================================================ fuel credit

-- One facility per carrier. `outstanding_ngwee` is the live balance and is the
-- only number that matters at the pump; it is maintained by record_fuel_draw()
-- and settle_load() and should never be written directly.
create table if not exists fuel_facilities (
  id                bigint generated always as identity primary key,
  driver_id         bigint      not null unique references users(id) on delete cascade,
  limit_ngwee       bigint      not null default 0 check (limit_ngwee >= 0),
  outstanding_ngwee bigint      not null default 0 check (outstanding_ngwee >= 0),
  status            text        not null default 'active'
                    check (status in ('active','suspended','closed')),
  completed_loads   integer     not null default 0 check (completed_loads >= 0),
  avg_weekly_payout_ngwee bigint not null default 0 check (avg_weekly_payout_ngwee >= 0),
  rebased_at        timestamptz,
  created_at        timestamptz not null default now(),
  -- The invariant the whole product rests on. Policy decides the limit; this
  -- guarantees no path can breach it.
  constraint outstanding_within_limit check (outstanding_ngwee <= limit_ngwee)
);

-- What one load may draw. Issued when the load is assigned, closed when it is
-- delivered or cancelled. Computed by musanga.fuel.entitlement().
create table if not exists fuel_entitlements (
  id                     bigint generated always as identity primary key,
  order_id               bigint      not null unique references orders(id) on delete cascade,
  driver_id              bigint      not null references users(id),
  litres                 integer     not null check (litres > 0),
  litres_drawn           integer     not null default 0 check (litres_drawn >= 0),
  price_ngwee_per_litre  integer     not null check (price_ngwee_per_litre > 0),
  status                 text        not null default 'open'
                         check (status in ('open','closed','void')),
  created_at             timestamptz not null default now(),
  -- A driver cannot fill a second tank on our account.
  constraint drawn_within_entitlement check (litres_drawn <= litres)
);
create index if not exists idx_entitlements_driver on fuel_entitlements(driver_id);

create table if not exists fuel_draws (
  id                    bigint generated always as identity primary key,
  entitlement_id        bigint      not null references fuel_entitlements(id) on delete cascade,
  driver_id             bigint      not null references users(id),
  litres                integer     not null check (litres > 0),
  price_ngwee_per_litre integer     not null check (price_ngwee_per_litre > 0),
  value_ngwee           bigint      not null check (value_ngwee > 0),
  -- What Musanga actually paid the OMC. The spread against the ERB ceiling is
  -- the revenue on this line; null until the supplier invoice is reconciled.
  cost_ngwee_per_litre  integer     check (cost_ngwee_per_litre > 0),
  station               text,
  drawn_at              timestamptz not null default now()
);
create index if not exists idx_draws_entitlement on fuel_draws(entitlement_id);
create index if not exists idx_draws_driver on fuel_draws(driver_id);

-- One row per settled load: what the carrier earned, what was netted off for
-- fuel, and what actually left the business.
create table if not exists settlements (
  id                     bigint generated always as identity primary key,
  order_id               bigint      not null unique references orders(id) on delete cascade,
  driver_id              bigint      not null references users(id),
  gross_ngwee            bigint      not null check (gross_ngwee >= 0),
  fuel_deduction_ngwee   bigint      not null default 0 check (fuel_deduction_ngwee >= 0),
  net_ngwee              bigint      not null check (net_ngwee >= 0),
  settled_at             timestamptz not null default now(),
  -- Never take more than the load earned, and always leave the carrier able to
  -- run the next one.
  constraint deduction_within_gross check (fuel_deduction_ngwee <= gross_ngwee),
  constraint net_is_remainder check (net_ngwee = gross_ngwee - fuel_deduction_ngwee)
);
create index if not exists idx_settlements_driver on settlements(driver_id);

-- ============================================================ insurance

-- Musanga places cover as an agent. The premium belongs to the insurer; only
-- commission_ngwee is platform revenue.
create table if not exists insurance_policies (
  id                    bigint generated always as identity primary key,
  order_id              bigint      not null unique references orders(id) on delete cascade,
  commodity_key         text        not null,
  declared_value_ngwee  bigint      not null check (declared_value_ngwee > 0),
  rate_bp               integer     not null check (rate_bp > 0),
  premium_ngwee         bigint      not null check (premium_ngwee > 0),
  commission_ngwee      bigint      not null check (commission_ngwee >= 0),
  insurer               text,
  policy_ref            text,
  status                text        not null default 'quoted'
                        check (status in ('quoted','bound','cancelled')),
  created_at            timestamptz not null default now(),
  constraint commission_within_premium check (commission_ngwee <= premium_ngwee)
);

-- ============================================================ atomic operations
--
-- These exist for concurrency, not for business logic. Each one is a single
-- statement's worth of "check and write" that must not race.

-- Two drivers tapping accept at the same instant must not both win.
create or replace function claim_job(p_ref text, p_driver_id bigint)
returns orders
language sql
as $$
  update orders
     set driver_id = p_driver_id, status = 'assigned'
   where ref = p_ref and driver_id is null and status = 'placed'
  returning *;
$$;

-- Record a draw at the pump and move the balance in the same transaction.
-- The caller (musanga/fuel.py) has already applied policy; the constraints on
-- fuel_facilities and fuel_entitlements are what actually stop a bad write.
create or replace function record_fuel_draw(
  p_entitlement_id bigint,
  p_litres         integer,
  p_price_ngwee    integer,
  p_station        text default null
) returns fuel_draws
language plpgsql
as $$
declare
  v_ent   fuel_entitlements;
  v_value bigint;
  v_draw  fuel_draws;
begin
  select * into v_ent from fuel_entitlements
   where id = p_entitlement_id for update;

  if not found then
    raise exception 'No such entitlement';
  end if;
  if v_ent.status <> 'open' then
    raise exception 'That entitlement is % and cannot be drawn against', v_ent.status;
  end if;

  v_value := p_litres::bigint * p_price_ngwee;

  update fuel_entitlements
     set litres_drawn = litres_drawn + p_litres
   where id = p_entitlement_id;

  update fuel_facilities
     set outstanding_ngwee = outstanding_ngwee + v_value
   where driver_id = v_ent.driver_id;

  insert into fuel_draws (entitlement_id, driver_id, litres,
                          price_ngwee_per_litre, value_ngwee, station)
  values (p_entitlement_id, v_ent.driver_id, p_litres,
          p_price_ngwee, v_value, p_station)
  returning * into v_draw;

  return v_draw;
end;
$$;

-- Settle a delivered load: take the deduction the caller computed, pay the
-- rest, close the entitlement. Idempotent by the unique key on order_id.
create or replace function settle_load(
  p_order_id  bigint,
  p_gross     bigint,
  p_deduction bigint
) returns settlements
language plpgsql
as $$
declare
  v_driver bigint;
  v_row    settlements;
begin
  select driver_id into v_driver from orders where id = p_order_id;
  if v_driver is null then
    raise exception 'Load has no carrier to settle';
  end if;

  update fuel_facilities
     set outstanding_ngwee = outstanding_ngwee - p_deduction,
         completed_loads   = completed_loads + 1
   where driver_id = v_driver;

  update fuel_entitlements
     set status = 'closed'
   where order_id = p_order_id and status = 'open';

  insert into settlements (order_id, driver_id, gross_ngwee,
                           fuel_deduction_ngwee, net_ngwee)
  values (p_order_id, v_driver, p_gross, p_deduction, p_gross - p_deduction)
  returning * into v_row;

  return v_row;
end;
$$;

-- ============================================================ row level security
--
-- Authentication is still Musanga's own (phone + password, sessions table), not
-- Supabase Auth, so there is no auth.uid() to write policies against yet. RLS is
-- enabled and left with no permissive policy: anon and authenticated roles can
-- read nothing, and the Python backend reaches the data with the service role,
-- which bypasses RLS by design.
--
-- This is deliberate and it is the safe default - if the anon key leaks, it
-- opens nothing. When auth moves to Supabase Auth, add per-role policies here
-- and stop using the service key from the browser side.

alter table users               enable row level security;
alter table sessions            enable row level security;
alter table vehicles            enable row level security;
alter table orders              enable row level security;
alter table events              enable row level security;
alter table hires               enable row level security;
alter table hire_events         enable row level security;
alter table fuel_facilities     enable row level security;
alter table fuel_entitlements   enable row level security;
alter table fuel_draws          enable row level security;
alter table settlements         enable row level security;
alter table insurance_policies  enable row level security;
