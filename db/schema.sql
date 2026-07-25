-- =============================================================================
-- HumanoidOnline — MVP v0.1 Database Schema (PostgreSQL)
-- =============================================================================
-- Commercial intelligence and transaction infrastructure for the humanoid
-- robotics economy.
--
-- DESIGN PRINCIPLES (frozen for v0.1)
--   1. Three permanent layers live in one schema:
--        Knowledge   -> manufacturer, robot, variant, spec, capability, use case,
--                       commercial status, pricing, availability, region,
--                       deployment, evidence, provider.
--        Decision    -> buyer_requirement, match_result.
--        Transaction -> commercial_lead (+ dormant offer specialisations).
--   2. Commercial MATURITY, transaction AVAILABILITY and deployment EVIDENCE are
--      THREE INDEPENDENT DIMENSIONS. A robot can be COMMERCIAL / RAAS_DEPLOYMENT,
--      have NO direct purchase offer, and carry $300M of deployment evidence all
--      at once (cf. Agility Digit v5). Never collapse these into `available bool`.
--   3. Price is never a single column. All money lives in pricing_offer, keyed by
--      transaction_type + price_type + billing_period + region + provider.
--   4. Availability is never a single column. It lives in availability_offer,
--      keyed by transaction_type + region + provider + availability_status.
--   5. Phases 3-5 (Rent / Buy / Lease-RaaS) are supported by the data model from
--      day 1 via transaction_type + provider + offer tables, but stay dormant in
--      the UI. No schema migration is required to activate them.
--   6. Every material, time-sensitive commercial claim can carry provenance via
--      evidence_source. HumanoidOnline's moat is VERIFIED commercial intelligence.
--
-- Target: PostgreSQL 14+. Uses gen_random_uuid() (built in from PG13, pgcrypto
-- provides it as a fallback). Idempotent-ish: safe to run on an empty database.
-- =============================================================================

CREATE EXTENSION IF NOT EXISTS pgcrypto;   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS pg_trgm;     -- trigram search on names / full-text

-- Optional dedicated schema; comment out to install into public.
CREATE SCHEMA IF NOT EXISTS humanoid;
SET search_path TO humanoid, public;

-- =============================================================================
-- SECTION 1 — ENUMERATED TYPES
-- These encode the "explicit states, never booleans" principle.
-- =============================================================================

-- Commercial MATURITY of a robot platform. Independent of whether you can buy it.
CREATE TYPE commercial_status AS ENUM (
    'ANNOUNCED',          -- publicly revealed, no hardware shipping
    'DEVELOPMENT',        -- actively engineered, internal only
    'PROTOTYPE',          -- working prototype(s), not sold
    'PILOT',              -- deployed in customer pilots / trials
    'EARLY_ACCESS',       -- limited external units (dev / design partners)
    'LIMITED_COMMERCIAL', -- for sale but constrained (region / quota / waitlist)
    'COMMERCIAL',         -- generally commercially available
    'RAAS_DEPLOYMENT',    -- deployed commercially as a service (not sold as a unit)
    'DISCONTINUED'        -- no longer offered
);

-- The commercial MODE of an offer / requirement. Drives Phases 3-5.
CREATE TYPE transaction_type AS ENUM (
    'PURCHASE',      -- Phase 4 (HumanoidMart)
    'RENTAL',        -- Phase 3 (RentHumanoid)
    'SUBSCRIPTION',  -- recurring access
    'LEASE',         -- Phase 5 (HumanoidLease)
    'RAAS',          -- Phase 5 robots-as-a-service
    'PILOT',         -- paid / structured pilot engagement
    'DEVELOPER',     -- developer / research edition acquisition
    'OTHER'
);

-- How a buyer's transaction preference is expressed in Phase 2 (superset of
-- transaction_type — we can capture intent before the products exist).
CREATE TYPE transaction_preference AS ENUM (
    'UNKNOWN',
    'RENT',
    'BUY',
    'LEASE',
    'RAAS',
    'FLEXIBLE'
);

-- Quality / nature of a price figure.
CREATE TYPE price_type AS ENUM (
    'PUBLIC',      -- published MSRP / store price
    'ESTIMATED',   -- HumanoidOnline estimate
    'QUOTE_ONLY',  -- price on request
    'FROM',        -- "from X" starting price
    'RANGE'        -- min-max band
);

-- Billing cadence for a price.
CREATE TYPE billing_period AS ENUM (
    'ONE_TIME',
    'HOURLY',
    'DAILY',
    'WEEKLY',
    'MONTHLY',
    'QUARTERLY',
    'ANNUAL'
);

-- Whether a specific transaction MODE is currently obtainable in a region.
CREATE TYPE availability_status AS ENUM (
    'NOT_AVAILABLE',
    'WAITLIST',
    'PREORDER',
    'LIMITED',
    'AVAILABLE',
    'ON_REQUEST',   -- quote / contact required
    'DISCONTINUED'
);

-- Kind of commercial counterparty. Bridges into Rent/Mart/Lease verticals.
CREATE TYPE provider_type AS ENUM (
    'OEM',
    'DISTRIBUTOR',
    'INTEGRATOR',
    'RENTAL_PROVIDER',
    'LEASING_PROVIDER',
    'RAAS_PROVIDER',
    'SERVICE_PROVIDER'
);

-- Locomotion form factor.
CREATE TYPE mobility_type AS ENUM (
    'BIPEDAL',
    'WHEELED',
    'HYBRID',       -- e.g. bipedal + wheeled base options
    'QUADRUPED',
    'STATIONARY',
    'OTHER'
);

-- Coarse autonomy level for filtering.
CREATE TYPE autonomy_level AS ENUM (
    'TELEOPERATED',        -- human in the loop, remote
    'ASSISTED',            -- teleop + assists
    'SUPERVISED_AUTONOMY', -- autonomous under supervision
    'TASK_AUTONOMOUS',     -- autonomous for specific tasks
    'HIGHLY_AUTONOMOUS'
);

-- Grouping for the capability catalogue (mirrors Robot Detail sections).
CREATE TYPE capability_category AS ENUM (
    'MANIPULATION',
    'MOBILITY',
    'PERCEPTION',
    'AI_AUTONOMY',
    'INTERACTION',
    'SOFTWARE',
    'SAFETY',
    'OTHER'
);

-- Geographic scope granularity.
CREATE TYPE region_type AS ENUM (
    'GLOBAL',
    'CONTINENT',
    'ECONOMIC_ZONE',  -- EU, APAC, etc.
    'COUNTRY',
    'SUBREGION'
);

-- What kind of source backs an evidence record.
CREATE TYPE source_type AS ENUM (
    'MANUFACTURER_STORE',
    'MANUFACTURER_SITE',
    'PRESS_RELEASE',
    'NEWS_ARTICLE',
    'ANALYST_REPORT',
    'FINANCIAL_FILING',
    'DIRECT_QUOTE',    -- quote HumanoidOnline obtained
    'CONFERENCE',
    'INTERVIEW',
    'OTHER'
);

-- Confidence attached to an evidence-backed claim.
CREATE TYPE confidence_level AS ENUM (
    'LOW',
    'MEDIUM',
    'HIGH',
    'VERIFIED'
);

-- Which entity a piece of evidence is about (polymorphic subject).
CREATE TYPE evidence_subject AS ENUM (
    'MANUFACTURER',
    'ROBOT',
    'ROBOT_VARIANT',
    'SPECIFICATION',
    'CAPABILITY',
    'COMMERCIAL_STATUS',
    'PRICING_OFFER',
    'AVAILABILITY_OFFER',
    'DEPLOYMENT',
    'PROVIDER'
);

-- Lifecycle of a qualified commercial lead (survives every phase).
CREATE TYPE lead_status AS ENUM (
    'NEW',
    'QUALIFYING',
    'QUALIFIED',
    'MATCHED',
    'INTRODUCED',     -- introduced to provider(s)
    'IN_DISCUSSION',
    'WON',
    'LOST',
    'DISQUALIFIED'
);

-- Why a match was surfaced (drives the labelled result cards).
CREATE TYPE match_category AS ENUM (
    'BEST_OVERALL',
    'BEST_COMMERCIAL',   -- best commercially available fit
    'BEST_LOWER_COST',
    'BEST_DEVELOPER',
    'BEST_TECHNICAL',
    'ALTERNATIVE'
);

-- Datatype of a flexible specification value.
CREATE TYPE spec_value_type AS ENUM (
    'NUMBER',
    'BOOLEAN',
    'TEXT',
    'ENUM'
);

-- Type of user in Phase 2 intake (analytics + routing).
CREATE TYPE buyer_type AS ENUM (
    'COMMERCIAL_BUYER',
    'TECHNICAL_EVALUATOR',
    'INDUSTRY_PARTICIPANT',
    'UNKNOWN'
);

-- Verified product imagery (MEDIA-01, docs/09). NO 'GENERATED' value exists for
-- identity imagery — a real robot is never depicted by a synthesized image.
CREATE TYPE image_source_type AS ENUM (
    'MANUFACTURER',
    'PRESS_KIT',
    'DISTRIBUTOR',
    'EDITORIAL',
    'VIDEO_FRAME'
);
CREATE TYPE image_type AS ENUM (
    'FRONT', 'SIDE', 'REAR', 'ACTION', 'WORKPLACE', 'DETAIL', 'DIMENSIONS'
);
-- Does the image DEPICT the exact robot/model? (kept separate from reuse rights)
CREATE TYPE image_identity_status AS ENUM (
    'VERIFIED',
    'UNVERIFIED'
);
-- Legal/licensing evidence for reuse. UNKNOWN must never behave like PERMITTED
-- (MEDIA-01.5). This is EVIDENCE, kept separate from platform display policy below.
CREATE TYPE image_rights_status AS ENUM (
    'PERMITTED',
    'ATTRIBUTION_REQUIRED',
    'UNKNOWN',
    'RESTRICTED'
);
-- Platform display POLICY basis — why HumanoidOnline displays an image even when a
-- formal reuse license is not on record. Distinct from rights_status (legal
-- evidence): OFFICIAL_MANUFACTURER_MEDIA records the ratified business decision to
-- display official manufacturer product media for the robots the platform markets,
-- WITHOUT falsely asserting an attribution license was granted (MEDIA-01 §H2).
CREATE TYPE image_usage_basis AS ENUM (
    'NONE',
    'OFFICIAL_MANUFACTURER_MEDIA'
);

-- =============================================================================
-- SECTION 2 — KNOWLEDGE LAYER: GEOGRAPHY
-- =============================================================================

CREATE TABLE region (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_id    UUID REFERENCES region(id) ON DELETE SET NULL,
    type         region_type NOT NULL,
    code         TEXT NOT NULL,          -- 'GLOBAL','EU','US','DE','CZ','APAC'...
    name         TEXT NOT NULL,
    iso_country  CHAR(2),                -- set for COUNTRY rows
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (code)
);
COMMENT ON TABLE region IS
    'Hierarchical geography (Global > Continent/Zone > Country > Subregion). '
    'Attached separately to availability, pricing, deployment and support so each '
    'commercial dimension can vary by geography (prep for Phases 3-5).';

-- =============================================================================
-- SECTION 2 — KNOWLEDGE LAYER: MANUFACTURERS & PROVIDERS
-- =============================================================================

CREATE TABLE manufacturer (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug               TEXT NOT NULL UNIQUE,          -- /manufacturers/agility-robotics
    name               TEXT NOT NULL,
    legal_name         TEXT,
    country_region_id  UUID REFERENCES region(id),
    website_url        TEXT,
    logo_url           TEXT,
    founded_year       INT CHECK (founded_year BETWEEN 1900 AND 2100),
    description        TEXT,
    target_markets     TEXT[],                        -- e.g. {manufacturing,logistics}
    commercial_model   TEXT,                          -- narrative: sell / RaaS / hybrid
    deployment_status  commercial_status,             -- coarse company-level maturity
    support_structure  TEXT,
    funding_status     TEXT,                          -- public / private / funding note
    is_public_company  BOOLEAN NOT NULL DEFAULT FALSE,
    ticker             TEXT,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE manufacturer IS 'OEM company profile. Powers /manufacturers.';

-- Provider = any commercial counterparty that can fulfil an offer. Created now,
-- mostly invisible in v0.1; it is the bridge to RentHumanoid / HumanoidMart /
-- HumanoidLease. An OEM is itself a provider (type=OEM).
CREATE TABLE provider (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug               TEXT NOT NULL UNIQUE,
    type               provider_type NOT NULL,
    name               TEXT NOT NULL,
    manufacturer_id    UUID REFERENCES manufacturer(id) ON DELETE SET NULL, -- if OEM-linked
    country_region_id  UUID REFERENCES region(id),
    website_url        TEXT,
    contact_email      TEXT,
    contact_name       TEXT,
    description        TEXT,
    is_active          BOOLEAN NOT NULL DEFAULT TRUE,
    -- monetization hooks (dormant): whether this provider can receive routed leads
    accepts_leads      BOOLEAN NOT NULL DEFAULT FALSE,
    lead_fee_model     TEXT,          -- 'per_lead' | 'referral_commission' | 'subscription'
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at         TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE provider IS
    'Commercial counterparty (OEM/distributor/integrator/rental/leasing/RaaS/service). '
    'Attached to availability & pricing offers; target of routed commercial leads.';

-- =============================================================================
-- SECTION 2 — KNOWLEDGE LAYER: ROBOTS & VARIANTS
-- =============================================================================

CREATE TABLE robot (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug                  TEXT NOT NULL UNIQUE,        -- /robots/unitree-g1
    manufacturer_id       UUID NOT NULL REFERENCES manufacturer(id) ON DELETE RESTRICT,
    name                  TEXT NOT NULL,
    model_code            TEXT,
    summary               TEXT,                        -- hero one-liner
    description           TEXT,
    hero_image_url        TEXT,
    announced_year        INT CHECK (announced_year BETWEEN 1900 AND 2100),

    -- DIMENSION 1: commercial MATURITY (current). History in robot_status_history.
    commercial_status     commercial_status NOT NULL DEFAULT 'ANNOUNCED',

    -- First-class PHYSICAL specs — the common filter columns from the catalogue.
    -- The long tail of specs lives in `specification`.
    height_cm             NUMERIC(6,1) CHECK (height_cm > 0),
    weight_kg             NUMERIC(6,1) CHECK (weight_kg > 0),
    payload_kg            NUMERIC(6,1) CHECK (payload_kg >= 0),
    walk_speed_ms         NUMERIC(5,2) CHECK (walk_speed_ms >= 0),   -- m/s
    runtime_minutes       INT CHECK (runtime_minutes >= 0),
    battery_wh            NUMERIC(8,1),
    mobility              mobility_type,
    degrees_of_freedom    INT CHECK (degrees_of_freedom >= 0),
    hand_type             TEXT,                        -- gripper / 5-finger / etc.
    hand_dof              INT CHECK (hand_dof >= 0),

    -- First-class INTELLIGENCE / capability flags for fast filtering.
    autonomy              autonomy_level,
    has_manipulation      BOOLEAN,
    has_teleoperation     BOOLEAN,
    has_vision            BOOLEAN,
    has_language_ui       BOOLEAN,

    -- First-class DEVELOPER flags.
    has_sdk               BOOLEAN,
    has_api               BOOLEAN,
    ros_support           BOOLEAN,
    developer_edition     BOOLEAN,
    simulation_support    BOOLEAN,

    -- Denormalised convenience fields (kept in sync by the app / triggers).
    -- Cheapest known purchase price for sort/badges; source of truth is pricing_offer.
    lowest_purchase_price NUMERIC(14,2),
    lowest_price_currency CHAR(3),

    search_vector         tsvector,                    -- maintained by trigger below
    is_published          BOOLEAN NOT NULL DEFAULT FALSE,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE robot IS
    'Core information object. Common filter specs are first-class columns; the long '
    'tail lives in specification. commercial_status is DIMENSION 1 (maturity) and is '
    'independent of transaction availability (availability_offer) and deployment '
    'evidence (deployment). Never add an `available bool` here.';
COMMENT ON COLUMN robot.lowest_purchase_price IS
    'Denormalised cache for sorting/badges ONLY. Authoritative money is pricing_offer.';

-- Variant / edition of a robot (developer edition, EU model, gen revisions...).
CREATE TABLE robot_variant (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    robot_id      UUID NOT NULL REFERENCES robot(id) ON DELETE CASCADE,
    slug          TEXT NOT NULL,
    name          TEXT NOT NULL,            -- "Developer Edition", "G1 EDU"...
    description   TEXT,
    is_developer  BOOLEAN NOT NULL DEFAULT FALSE,
    spec_overrides JSONB,                   -- variant-specific spec deltas
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (robot_id, slug)
);
COMMENT ON TABLE robot_variant IS 'Editions/revisions of a robot. Offers may target a variant.';

-- Append-only history of commercial maturity transitions (audit + timeline UI).
CREATE TABLE robot_status_history (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    robot_id    UUID NOT NULL REFERENCES robot(id) ON DELETE CASCADE,
    status      commercial_status NOT NULL,
    effective_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    note        TEXT,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE robot_status_history IS 'Timeline of commercial_status changes per robot.';

-- Verified product imagery (MEDIA-01, docs/09_MEDIA_CONTRACT.md). The single
-- image-truth system for a named robot: one robot -> many images, each carrying
-- its own provenance, identity verification and reuse-rights status. Reused by
-- Compare and Phases 3-5 (Rent/Buy/Lease) without a second image system.
--
-- Two invariants encoded here:
--   * THREE independent dimensions, never collapsed: identity_status (does it
--     depict THIS exact robot), rights_status (legal/licensing EVIDENCE for reuse),
--     and usage_basis (platform display POLICY). An image is display-eligible ONLY
--     when identity_status='VERIFIED' AND rights_status <> 'RESTRICTED' AND
--     (rights_status IN ('PERMITTED','ATTRIBUTION_REQUIRED') OR
--      usage_basis='OFFICIAL_MANUFACTURER_MEDIA'). A non-NULL image_url is NEVER
--     sufficient; RESTRICTED always blocks; UNKNOWN rights never acts like PERMITTED.
--   * image_url (the asset rendered) is SEPARATE from source_url (the
--     authoritative page establishing provenance) — we must be able to
--     reconstruct WHY an image was trusted, not just WHAT was shown.
-- `robot.hero_image_url` is dormant/non-canonical and is NOT the read path.
CREATE TABLE robot_image (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    robot_id        UUID NOT NULL REFERENCES robot(id) ON DELETE CASCADE,
    image_url       TEXT NOT NULL,             -- the actual asset being rendered
    source_url      TEXT,                      -- authoritative provenance page
    source_name     TEXT,                      -- e.g. 'Unitree Robotics', 'Wikimedia Commons'
    source_type     image_source_type NOT NULL,
    image_type      image_type NOT NULL DEFAULT 'FRONT',
    identity_status image_identity_status NOT NULL DEFAULT 'UNVERIFIED',
    rights_status   image_rights_status NOT NULL DEFAULT 'UNKNOWN',   -- legal evidence
    usage_basis     image_usage_basis NOT NULL DEFAULT 'NONE',        -- display policy
    is_official     BOOLEAN NOT NULL DEFAULT FALSE,
    is_primary      BOOLEAN NOT NULL DEFAULT FALSE,
    attribution     TEXT,                      -- required credit line when ATTRIBUTION_REQUIRED
    captured_at     DATE,                      -- when the photo/asset was captured, if known
    last_verified_at TIMESTAMPTZ,              -- when identity/rights were last checked
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE robot_image IS
    'MEDIA-01 verified product imagery. Display-eligible only when identity VERIFIED, '
    'rights_status <> RESTRICTED, and (rights PERMITTED/ATTRIBUTION_REQUIRED OR '
    'usage_basis OFFICIAL_MANUFACTURER_MEDIA); a non-null image_url is never '
    'sufficient. No GENERATED source exists — real robots are never depicted by '
    'synthesized imagery. Missing/ineligible -> IMAGE_UNAVAILABLE.';
-- At most one primary image per robot (partial unique — many non-primary allowed).
CREATE UNIQUE INDEX uq_robot_image_primary ON robot_image (robot_id) WHERE is_primary;
CREATE INDEX idx_robot_image_robot ON robot_image (robot_id);

-- =============================================================================
-- SECTION 2 — KNOWLEDGE LAYER: SPECIFICATIONS (flexible long tail)
-- =============================================================================

-- Catalogue of specification keys so the flexible table stays consistent.
CREATE TABLE spec_definition (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key         TEXT NOT NULL UNIQUE,        -- 'reach_cm','ip_rating','max_torque_nm'
    label       TEXT NOT NULL,
    category    capability_category NOT NULL DEFAULT 'OTHER',
    value_type  spec_value_type NOT NULL,
    unit        TEXT,                        -- 'cm','kg','Nm','V'...
    is_filterable BOOLEAN NOT NULL DEFAULT FALSE,
    sort_order  INT NOT NULL DEFAULT 0
);

CREATE TABLE specification (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    robot_id     UUID NOT NULL REFERENCES robot(id) ON DELETE CASCADE,
    variant_id   UUID REFERENCES robot_variant(id) ON DELETE CASCADE,
    definition_id UUID NOT NULL REFERENCES spec_definition(id) ON DELETE RESTRICT,
    value_number NUMERIC(18,4),
    value_bool   BOOLEAN,
    value_text   TEXT,
    unit         TEXT,                       -- overrides definition.unit if needed
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
    -- Logical uniqueness enforced by uq_specification_logical below
    -- (variant_id is nullable; see NULL-uniqueness note on availability_offer).
);
COMMENT ON TABLE specification IS
    'Long-tail structured specs (key/value with numeric+bool+text). First-class '
    'filter specs stay on robot for query speed; everything else goes here.';

-- =============================================================================
-- SECTION 2 — KNOWLEDGE LAYER: CAPABILITIES
-- =============================================================================

CREATE TABLE capability (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug        TEXT NOT NULL UNIQUE,
    name        TEXT NOT NULL,               -- 'Bimanual manipulation','Stair climbing'
    category    capability_category NOT NULL,
    description TEXT
);

CREATE TABLE robot_capability (
    robot_id     UUID NOT NULL REFERENCES robot(id) ON DELETE CASCADE,
    capability_id UUID NOT NULL REFERENCES capability(id) ON DELETE CASCADE,
    supported    BOOLEAN NOT NULL DEFAULT TRUE,
    detail       TEXT,                        -- qualifier / limitation
    PRIMARY KEY (robot_id, capability_id)
);
COMMENT ON TABLE robot_capability IS 'Robot <-> capability catalogue join with per-robot detail.';

-- =============================================================================
-- SECTION 2 — KNOWLEDGE LAYER: USE CASES (first-class entity, not tags)
-- =============================================================================

CREATE TABLE use_case (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    slug          TEXT NOT NULL UNIQUE,       -- /use-cases/warehouse-logistics
    name          TEXT NOT NULL,             -- 'Warehouse & Logistics'
    category      TEXT,                       -- industry grouping
    description   TEXT,
    typical_tasks TEXT[],                     -- {tote handling, line feeding,...}
    typical_requirements TEXT,                -- narrative deployment requirements
    key_limitations TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE use_case IS 'First-class application entity. Powers /use-cases and SEO landing pages.';

-- Fit of a robot to a use case, with an explainable readiness note.
CREATE TABLE use_case_fit (
    robot_id             UUID NOT NULL REFERENCES robot(id) ON DELETE CASCADE,
    use_case_id          UUID NOT NULL REFERENCES use_case(id) ON DELETE CASCADE,
    fit_score            NUMERIC(4,3) CHECK (fit_score BETWEEN 0 AND 1),
    is_primary           BOOLEAN NOT NULL DEFAULT FALSE,
    commercial_readiness commercial_status,   -- readiness *for this use case*
    notes                TEXT,
    limitations          TEXT,
    PRIMARY KEY (robot_id, use_case_id)
);
COMMENT ON TABLE use_case_fit IS 'Robot suitability per use case; feeds matching and use-case pages.';

-- =============================================================================
-- SECTION 3 — COMMERCIAL LAYER: PRICING (never a single column)
-- =============================================================================

CREATE TABLE pricing_offer (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    robot_id         UUID NOT NULL REFERENCES robot(id) ON DELETE CASCADE,
    variant_id       UUID REFERENCES robot_variant(id) ON DELETE CASCADE,
    provider_id      UUID REFERENCES provider(id) ON DELETE SET NULL,
    region_id        UUID REFERENCES region(id),
    transaction_type transaction_type NOT NULL,
    price_type       price_type NOT NULL,
    currency         CHAR(3) NOT NULL DEFAULT 'USD',
    price            NUMERIC(14,2),           -- point price (PUBLIC/FROM/ESTIMATED)
    price_min        NUMERIC(14,2),           -- for RANGE
    price_max        NUMERIC(14,2),           -- for RANGE
    billing_period   billing_period NOT NULL DEFAULT 'ONE_TIME',
    is_current       BOOLEAN NOT NULL DEFAULT TRUE,
    valid_from       DATE,
    valid_until      DATE,
    note             TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Frozen price_type semantics (03_DATA_DICTIONARY §3), enforced by the DB
    -- because the DDL wins over application assumptions:
    CONSTRAINT chk_price_type_shape CHECK (
        (price_type = 'QUOTE_ONLY'
            AND price IS NULL AND price_min IS NULL AND price_max IS NULL)
     OR (price_type = 'RANGE'
            AND price IS NULL AND price_min IS NOT NULL AND price_max IS NOT NULL
            AND price_max >= price_min)
     OR (price_type IN ('PUBLIC','FROM','ESTIMATED')
            AND price IS NOT NULL AND price_min IS NULL AND price_max IS NULL)
    )
);
COMMENT ON TABLE pricing_offer IS
    'ALL money. Keyed by transaction_type (purchase/rental/lease/raas/...), '
    'price_type (public/estimated/quote/from/range), billing_period, region and '
    'provider. Attach provenance via evidence_source(subject=PRICING_OFFER).';

-- =============================================================================
-- SECTION 3 — COMMERCIAL LAYER: AVAILABILITY (never a single column)
-- =============================================================================
-- DIMENSION 2: transaction AVAILABILITY, independent of maturity and evidence.

CREATE TABLE availability_offer (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    robot_id            UUID NOT NULL REFERENCES robot(id) ON DELETE CASCADE,
    variant_id          UUID REFERENCES robot_variant(id) ON DELETE CASCADE,
    provider_id         UUID REFERENCES provider(id) ON DELETE SET NULL,
    region_id           UUID REFERENCES region(id),
    transaction_type    transaction_type NOT NULL,
    availability_status availability_status NOT NULL DEFAULT 'ON_REQUEST',
    available_from      DATE,               -- e.g. general availability date
    lead_time_days      INT CHECK (lead_time_days >= 0),
    min_order_qty       INT CHECK (min_order_qty >= 0),
    note                TEXT,
    is_current          BOOLEAN NOT NULL DEFAULT TRUE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
    -- Logical uniqueness (robot × variant × provider × region × transaction) is
    -- enforced by uq_availability_logical below. A plain UNIQUE would not work:
    -- under PG14 semantics NULL <> NULL, so duplicate rows with NULL variant/
    -- provider/region would slip through. (PG15 NULLS NOT DISTINCT unavailable
    -- at our PG14 floor.)
);
COMMENT ON TABLE availability_offer IS
    'Whether a given transaction MODE is obtainable, per region/provider. This is '
    'the model that lights up Phases 3-5: a RENTAL row -> RentHumanoid, a PURCHASE '
    'row -> HumanoidMart, a LEASE/RAAS row -> HumanoidLease. No migration needed.';

-- =============================================================================
-- SECTION 3 — COMMERCIAL LAYER: DEPLOYMENTS (evidence dimension)
-- =============================================================================
-- DIMENSION 3: deployment EVIDENCE. Proof of real-world commercial use, kept
-- distinct from both maturity and purchasability (cf. Digit RaaS + $300M orders).

CREATE TABLE deployment (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    robot_id          UUID NOT NULL REFERENCES robot(id) ON DELETE CASCADE,
    provider_id       UUID REFERENCES provider(id) ON DELETE SET NULL,
    customer_name     TEXT,                 -- deploying org (may be undisclosed)
    region_id         UUID REFERENCES region(id),
    use_case_id       UUID REFERENCES use_case(id) ON DELETE SET NULL,
    transaction_type  transaction_type,     -- how it was engaged (often RAAS)
    unit_count        INT CHECK (unit_count >= 0),
    contract_value    NUMERIC(16,2),        -- e.g. multi-year contracted value
    contract_currency CHAR(3) DEFAULT 'USD',
    started_on        DATE,
    status            TEXT,                 -- 'pilot','scaling','production'...
    summary           TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE deployment IS
    'Real-world commercial deployments (the evidence dimension). Independent of '
    'maturity and availability. Back each with evidence_source(subject=DEPLOYMENT).';

-- =============================================================================
-- SECTION 3 — COMMERCIAL LAYER: EVIDENCE & PROVENANCE
-- =============================================================================
-- Polymorphic provenance for any material claim. subject_type + subject_id is a
-- deliberate soft reference (no cross-table FK) so one table can cite every
-- entity; integrity is enforced in the application layer.

CREATE TABLE evidence_source (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_type  evidence_subject NOT NULL,
    subject_id    UUID NOT NULL,
    source_url    TEXT,
    source_type   source_type NOT NULL,
    source_title  TEXT,
    excerpt       TEXT,
    published_at  DATE,
    observed_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    verified_at   TIMESTAMPTZ,
    confidence    confidence_level NOT NULL DEFAULT 'MEDIUM',
    note          TEXT,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE evidence_source IS
    'Provenance for any changing commercial claim (price, availability, status, '
    'deployment...). Polymorphic via (subject_type, subject_id). Powers the '
    '"Verified: 2026-07-24 / Source: manufacturer store" indicators. The moat.';

-- =============================================================================
-- SECTION 4 — DECISION LAYER: BUYER INTENT & MATCHING (Phase 2)
-- =============================================================================
-- The buyer_requirement is the permanent intent object. It is captured in Phase
-- 2 and becomes the transaction object for Phases 3-5 without change.

CREATE TABLE buyer_requirement (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    -- who (light-touch; may be anonymous until lead capture)
    buyer_type            buyer_type NOT NULL DEFAULT 'UNKNOWN',
    contact_name          TEXT,
    contact_email         TEXT,
    organization          TEXT,
    country_region_id     UUID REFERENCES region(id),

    -- what they need the robot to do
    use_case_id           UUID REFERENCES use_case(id) ON DELETE SET NULL,
    industry              TEXT,
    task_description      TEXT,
    environment           TEXT,               -- indoor/outdoor/warehouse/cleanroom...

    -- structured requirements used by the deterministic scorer
    payload_min_kg        NUMERIC(6,1),
    operating_hours_day   NUMERIC(4,1),
    manipulation_required BOOLEAN,
    autonomy_required     autonomy_level,
    budget_currency       CHAR(3) DEFAULT 'USD',
    budget_min            NUMERIC(14,2),
    budget_max            NUMERIC(14,2),
    required_by           DATE,               -- deployment date

    -- transaction preference captured NOW, before Rent/Buy/Lease launch
    preferred_transaction transaction_preference NOT NULL DEFAULT 'UNKNOWN',

    raw_input             JSONB,              -- full intake payload (natural language + answers)
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE buyer_requirement IS
    'The permanent Phase-2 intent object. Feeds the deterministic matcher and, on '
    'contact capture, becomes a commercial_lead. Same object survives Phases 3-5.';

-- One scored recommendation for a requirement, with an EXPLAINABLE breakdown.
CREATE TABLE match_result (
    id                 UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    requirement_id     UUID NOT NULL REFERENCES buyer_requirement(id) ON DELETE CASCADE,
    robot_id           UUID NOT NULL REFERENCES robot(id) ON DELETE CASCADE,
    score              NUMERIC(5,2) NOT NULL CHECK (score BETWEEN 0 AND 100),
    rank               INT NOT NULL CHECK (rank >= 1),
    category           match_category NOT NULL DEFAULT 'ALTERNATIVE',
    -- transparent scoring: per-criterion contributions + reasons/warnings
    score_breakdown    JSONB NOT NULL DEFAULT '{}'::jsonb,
    reasons            TEXT[],               -- "commercial deployment available",...
    warnings           TEXT[],               -- "runtime may require charging strategy"
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (requirement_id, robot_id)
);
COMMENT ON TABLE match_result IS
    'Deterministic, explainable recommendation. score_breakdown holds the weighted '
    'per-criterion contributions (use-case 25 / commercial 20 / technical 20 / '
    'geography 15 / budget 10 / deployment-readiness 10). Repeatable & testable.';

-- =============================================================================
-- SECTION 5 — TRANSACTION LAYER: COMMERCIAL LEAD (survives every phase)
-- =============================================================================
-- The single most strategically important backend entity. First monetization =
-- qualified commercial introductions; no payments/escrow in v0.1.

CREATE TABLE commercial_lead (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    requirement_id        UUID REFERENCES buyer_requirement(id) ON DELETE SET NULL,
    -- captured contact (denormalised from requirement at capture time)
    contact_name          TEXT,
    contact_email         TEXT NOT NULL,
    organization          TEXT,
    country_region_id     UUID REFERENCES region(id),
    use_case_id           UUID REFERENCES use_case(id) ON DELETE SET NULL,
    preferred_transaction transaction_preference NOT NULL DEFAULT 'UNKNOWN',
    budget_currency       CHAR(3) DEFAULT 'USD',
    budget_min            NUMERIC(14,2),
    budget_max            NUMERIC(14,2),
    timeline              DATE,               -- required-by
    requirements_snapshot JSONB,              -- frozen copy of the requirement
    message               TEXT,               -- buyer's free-text commercial inquiry (WS7)
    lead_status           lead_status NOT NULL DEFAULT 'NEW',
    outcome               TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE commercial_lead IS
    'Qualified inquiry that survives every phase: Phase 2 lead -> Phase 3 rental '
    'opportunity -> Phase 4 purchase -> Phase 5 lease/RaaS. No system migration.';

-- Robots attached to a lead (the matched shortlist that was surfaced).
CREATE TABLE commercial_lead_robot (
    lead_id     UUID NOT NULL REFERENCES commercial_lead(id) ON DELETE CASCADE,
    robot_id    UUID NOT NULL REFERENCES robot(id) ON DELETE CASCADE,
    match_score NUMERIC(5,2),
    is_selected BOOLEAN NOT NULL DEFAULT FALSE,   -- buyer's pick, if any
    PRIMARY KEY (lead_id, robot_id)
);

-- Providers a lead was (or will be) introduced to — the routing / fulfilment log.
CREATE TABLE commercial_lead_provider (
    id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    lead_id      UUID NOT NULL REFERENCES commercial_lead(id) ON DELETE CASCADE,
    provider_id  UUID NOT NULL REFERENCES provider(id) ON DELETE CASCADE,
    robot_id     UUID REFERENCES robot(id) ON DELETE SET NULL,
    status       TEXT NOT NULL DEFAULT 'PENDING',  -- PENDING/CONTACTED/ACCEPTED/DECLINED
    contacted_at TIMESTAMPTZ,
    note         TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (lead_id, provider_id, robot_id)
);
COMMENT ON TABLE commercial_lead_provider IS
    'Lead routing / introduction log. Basis of the first revenue model: fee per '
    'qualified introduction / referral commission.';

-- =============================================================================
-- SECTION 5 — DORMANT PHASE 3-5 OFFER SPECIALISATIONS
-- =============================================================================
-- NOTE ON DESIGN: the unified availability_offer + pricing_offer (keyed by
-- transaction_type) is the PRIMARY model and is enough to launch Rent/Buy/Lease.
-- The views below are convenience projections so vertical apps
-- (RentHumanoid / HumanoidMart / HumanoidLease) can read "their" offers without
-- re-implementing logic — honouring "not four independent platforms". They are
-- created but unused in v0.1.
--
-- PRICE↔AVAILABILITY MATCHING SEMANTICS (frozen):
-- A pricing_offer may attach to an availability_offer ONLY when ALL hold:
--   robot        : equal
--   transaction  : equal transaction_type
--   variant      : price.variant_id = availability.variant_id, OR price is
--                  variant-agnostic (NULL). A variant-specific price never
--                  attaches to a different variant's (or robot-level) offer.
--   provider     : price.provider_id = availability.provider_id, OR price is
--                  provider-agnostic (NULL). Provider A's availability must
--                  NEVER surface provider B's price.
--   geography    : price.region_id = availability.region_id, OR price.region is
--                  the availability region's direct parent (e.g. EU price for a
--                  DE availability), OR price.region is GLOBAL, OR price.region
--                  is NULL (region-agnostic). Deeper hierarchy resolution is
--                  application-layer via region.parent_id.
-- When several prices match, the MOST SPECIFIC one wins:
--   provider-specific > provider-agnostic; exact region > parent > GLOBAL/NULL;
--   variant-specific > variant-agnostic; then most recently updated.
-- Each availability row therefore surfaces AT MOST ONE price (LATERAL … LIMIT 1).
-- NOTE: an offer with a multi-tier tariff (e.g. rental DAILY + WEEKLY rates)
-- surfaces only its single best-matching price here; vertical apps needing the
-- full tariff read all matching pricing_offer rows directly.

CREATE VIEW commercial_offer AS
SELECT
    a.*,
    p.id             AS pricing_offer_id,
    p.price, p.price_min, p.price_max, p.currency,
    p.billing_period, p.price_type,
    p.provider_id    AS price_provider_id,
    p.region_id      AS price_region_id
FROM availability_offer a
LEFT JOIN LATERAL (
    SELECT po.*
    FROM pricing_offer po
    WHERE po.robot_id = a.robot_id
      AND po.is_current
      AND po.transaction_type = a.transaction_type
      AND (po.variant_id  = a.variant_id  OR po.variant_id  IS NULL)
      AND (po.provider_id = a.provider_id OR po.provider_id IS NULL)
      AND (   po.region_id = a.region_id
           OR po.region_id = (SELECT r.parent_id FROM region r WHERE r.id = a.region_id)
           OR po.region_id = (SELECT r2.id FROM region r2 WHERE r2.code = 'GLOBAL')
           OR po.region_id IS NULL)
    ORDER BY (po.provider_id IS NOT NULL) DESC,
             (po.region_id = a.region_id) DESC,
             (po.variant_id IS NOT NULL) DESC,
             po.updated_at DESC
    LIMIT 1
) p ON TRUE;
COMMENT ON VIEW commercial_offer IS
    'availability_offer + its single best-matching current price (semantics in '
    'the block comment above). Base projection for the Phase 3-5 vertical views.';

CREATE VIEW rental_offer   AS SELECT * FROM commercial_offer
    WHERE transaction_type IN ('RENTAL','SUBSCRIPTION');
CREATE VIEW purchase_offer AS SELECT * FROM commercial_offer
    WHERE transaction_type IN ('PURCHASE','DEVELOPER');
CREATE VIEW lease_offer    AS SELECT * FROM commercial_offer
    WHERE transaction_type IN ('LEASE','RAAS');

-- =============================================================================
-- SECTION 6 — ANALYTICS (lightweight product events; optional but cheap)
-- =============================================================================

CREATE TABLE event_log (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    occurred_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    session_id   UUID,
    event_type   TEXT NOT NULL,            -- 'robot_view','compare','match_run','lead_capture'
    robot_id     UUID REFERENCES robot(id) ON DELETE SET NULL,
    requirement_id UUID REFERENCES buyer_requirement(id) ON DELETE SET NULL,
    payload      JSONB
);

-- =============================================================================
-- SECTION 7 — INDEXES
-- =============================================================================

-- Full-text + trigram search on robots
CREATE INDEX idx_robot_search_vector ON robot USING GIN (search_vector);
CREATE INDEX idx_robot_name_trgm     ON robot USING GIN (name gin_trgm_ops);
CREATE INDEX idx_robot_manufacturer  ON robot (manufacturer_id);
CREATE INDEX idx_robot_status        ON robot (commercial_status);
CREATE INDEX idx_robot_published     ON robot (is_published) WHERE is_published;
-- common numeric filters
CREATE INDEX idx_robot_payload       ON robot (payload_kg);
CREATE INDEX idx_robot_height        ON robot (height_cm);
CREATE INDEX idx_robot_price         ON robot (lowest_purchase_price);

CREATE INDEX idx_manufacturer_name_trgm ON manufacturer USING GIN (name gin_trgm_ops);

CREATE INDEX idx_variant_robot        ON robot_variant (robot_id);
CREATE INDEX idx_spec_robot           ON specification (robot_id);
CREATE INDEX idx_spec_definition      ON specification (definition_id);
CREATE INDEX idx_robot_capability_cap ON robot_capability (capability_id);
CREATE INDEX idx_use_case_fit_uc      ON use_case_fit (use_case_id);

CREATE INDEX idx_pricing_robot        ON pricing_offer (robot_id);
CREATE INDEX idx_pricing_txn          ON pricing_offer (transaction_type) WHERE is_current;
CREATE INDEX idx_pricing_region       ON pricing_offer (region_id);

-- NULL-safe logical uniqueness (PG14: expression indexes with COALESCE stand in
-- for NULLS NOT DISTINCT). Partial on is_current so superseded history rows can
-- coexist with their replacement.
CREATE UNIQUE INDEX uq_availability_logical ON availability_offer (
    robot_id,
    COALESCE(variant_id,  '00000000-0000-0000-0000-000000000000'::uuid),
    COALESCE(provider_id, '00000000-0000-0000-0000-000000000000'::uuid),
    COALESCE(region_id,   '00000000-0000-0000-0000-000000000000'::uuid),
    transaction_type
) WHERE is_current;

CREATE UNIQUE INDEX uq_specification_logical ON specification (
    robot_id,
    COALESCE(variant_id, '00000000-0000-0000-0000-000000000000'::uuid),
    definition_id
);

CREATE INDEX idx_availability_robot   ON availability_offer (robot_id);
CREATE INDEX idx_availability_txn     ON availability_offer (transaction_type, availability_status) WHERE is_current;
CREATE INDEX idx_availability_region  ON availability_offer (region_id);
CREATE INDEX idx_availability_provider ON availability_offer (provider_id);

CREATE INDEX idx_deployment_robot     ON deployment (robot_id);
CREATE INDEX idx_deployment_provider  ON deployment (provider_id);
CREATE INDEX idx_deployment_region    ON deployment (region_id);

CREATE INDEX idx_evidence_subject     ON evidence_source (subject_type, subject_id);
CREATE INDEX idx_evidence_verified    ON evidence_source (verified_at);

CREATE INDEX idx_requirement_use_case ON buyer_requirement (use_case_id);
CREATE INDEX idx_match_requirement    ON match_result (requirement_id);
CREATE INDEX idx_match_robot          ON match_result (robot_id);

CREATE INDEX idx_lead_status          ON commercial_lead (lead_status);
CREATE INDEX idx_lead_requirement     ON commercial_lead (requirement_id);
CREATE INDEX idx_lead_provider_lead   ON commercial_lead_provider (lead_id);
CREATE INDEX idx_lead_provider_prov   ON commercial_lead_provider (provider_id);

CREATE INDEX idx_provider_type        ON provider (type);
CREATE INDEX idx_provider_leads       ON provider (accepts_leads) WHERE accepts_leads;

CREATE INDEX idx_event_type_time      ON event_log (event_type, occurred_at);
CREATE INDEX idx_region_parent        ON region (parent_id);

-- =============================================================================
-- SECTION 8 — TRIGGERS
-- =============================================================================

-- 8.1 updated_at maintenance
CREATE OR REPLACE FUNCTION set_updated_at() RETURNS trigger AS $$
BEGIN
    NEW.updated_at = now();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DO $$
DECLARE t TEXT;
BEGIN
    FOR t IN
        SELECT unnest(ARRAY[
            'manufacturer','provider','robot','specification','pricing_offer',
            'availability_offer','deployment','commercial_lead'
        ])
    LOOP
        EXECUTE format(
            'CREATE TRIGGER trg_%1$s_updated BEFORE UPDATE ON %1$s
             FOR EACH ROW EXECUTE FUNCTION set_updated_at();', t);
    END LOOP;
END$$;

-- 8.2 robot full-text search vector
CREATE OR REPLACE FUNCTION robot_search_vector_update() RETURNS trigger AS $$
BEGIN
    NEW.search_vector :=
        setweight(to_tsvector('simple', coalesce(NEW.name,'')), 'A') ||
        setweight(to_tsvector('simple', coalesce(NEW.model_code,'')), 'A') ||
        setweight(to_tsvector('english', coalesce(NEW.summary,'')), 'B') ||
        setweight(to_tsvector('english', coalesce(NEW.description,'')), 'C');
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_robot_search
    BEFORE INSERT OR UPDATE OF name, model_code, summary, description ON robot
    FOR EACH ROW EXECUTE FUNCTION robot_search_vector_update();

-- =============================================================================
-- SECTION 9 — CANONICAL ACCESS PREDICATE + commercial snapshot per robot
-- =============================================================================

-- THE canonical rule for "commercially accessible", used everywhere a yes/no
-- access decision is made (snapshot, catalogue filters like transaction_type=,
-- Home's "Commercially accessible" section). One rule, one place:
--   commercially accessible ⇔ is_current AND status NOT IN (NOT_AVAILABLE, DISCONTINUED)
-- WAITLIST / PREORDER / LIMITED / ON_REQUEST all COUNT as accessible
-- (constrained, future, constrained, bespoke — but a real commercial path).
CREATE FUNCTION commercially_accessible(status availability_status)
RETURNS boolean
LANGUAGE sql IMMUTABLE PARALLEL SAFE
RETURN status NOT IN ('NOT_AVAILABLE','DISCONTINUED');

COMMENT ON FUNCTION commercially_accessible(availability_status) IS
    'Canonical commercial-access predicate. Any query deciding "can a buyer '
    'engage?" MUST use this function (plus is_current) — never an ad-hoc status list.';

CREATE VIEW robot_commercial_snapshot AS
SELECT
    r.id,
    r.slug,
    r.name,
    r.commercial_status                             AS maturity,          -- DIMENSION 1
    EXISTS (SELECT 1 FROM availability_offer a
            WHERE a.robot_id = r.id AND a.is_current
              AND commercially_accessible(a.availability_status))
                                                    AS is_obtainable,     -- DIMENSION 2
    (SELECT count(*) FROM deployment d WHERE d.robot_id = r.id)
                                                    AS deployment_count,  -- DIMENSION 3
    (SELECT sum(d.contract_value) FROM deployment d WHERE d.robot_id = r.id)
                                                    AS contracted_value,
    array(SELECT DISTINCT a.transaction_type::text FROM availability_offer a
          WHERE a.robot_id = r.id AND a.is_current
            AND commercially_accessible(a.availability_status))
                                                    AS available_modes
FROM robot r;
COMMENT ON VIEW robot_commercial_snapshot IS
    'Maturity, obtainability and deployment evidence as three independent columns '
    '- the shape that lets a robot be COMMERCIAL, not directly purchasable, and '
    'heavily deployed simultaneously.';

-- =============================================================================
-- END OF SCHEMA
-- =============================================================================
