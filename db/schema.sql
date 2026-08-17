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
    'UNKNOWN',            -- maturity NOT YET VERIFIED. Asserts nothing: it is not
                          -- ANNOUNCED, not NOT_AVAILABLE, not DISCONTINUED, not
                          -- false and not zero. Because it makes no commercial
                          -- claim, G2 demands no evidence for it (every other
                          -- value does). First in the enum so an unverified
                          -- profile never sorts above one with a real claim.
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
    -- Defaults to UNKNOWN, not ANNOUNCED: a row inserted without an explicit
    -- maturity has not had one verified, and must not silently claim one.
    commercial_status     commercial_status NOT NULL DEFAULT 'UNKNOWN',

    -- First-class PHYSICAL specs — the common filter columns from the catalogue.
    -- The long tail of specs lives in `specification`.
    height_cm             NUMERIC(6,1) CHECK (height_cm > 0),
    weight_kg             NUMERIC(6,1) CHECK (weight_kg > 0),
    -- Horizontal extent. Two measurements, never derived from one another:
    -- span is fingertip-to-fingertip, reach is one arm from its shoulder.
    arm_span_cm           NUMERIC(6,1) CHECK (arm_span_cm > 0),
    reach_cm              NUMERIC(6,1) CHECK (reach_cm > 0),
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
-- SECTION 10 — DISCOVERY LAYER (DATA-D1, docs/11_DATA_D1_CONTRACT.md, RATIFIED v0.1)
-- =============================================================================
-- Noncanonical competitive-discovery research queue. STRUCTURALLY SEPARATE from
-- canonical (§5 / DATA-D1.10 / Gate K): no canonical table above is altered and
-- none gains a foreign key to a discovery table. The only cross-references point
-- FROM a candidate TO canonical (possible_*/promoted_robot_id), never the reverse.
-- Mirrored by db/migrations/0003_add_discovery_layer.sql.

-- DATA-D1.LIVE §4 (docs/16, RATIFIED v0.1) widened this vocabulary ADDITIVELY for
-- official-first, multi-source radar. Every value DATA-D1 shipped in migration
-- 0003 is retained verbatim — no rename, no removal, no re-mapping of existing
-- rows — and four classes are appended. Class predicts nothing about eligibility
-- (§5): an aggregator is reviewed by exactly the same procedure as a manufacturer.
CREATE TYPE discovery_source_class AS ENUM (
    'COMPETITOR_DIRECTORY', 'MARKETPLACE', 'EDITORIAL', 'SEARCH_RESULT',
    'DISTRIBUTOR', 'MANUFACTURER', 'PRESS_RELEASE', 'OFFICIAL_DOCUMENT',
    'OFFICIAL_VIDEO', 'OTHER',
    -- DATA-D1.LIVE §4 additions (migration 0004).
    'AGGREGATOR', 'AUTHORIZED_DISTRIBUTOR', 'OFFICIAL_STORE', 'COMMUNITY');

-- DATA-D1.9: an AFFIRMATIVE decision that automated access is permitted — not
-- merely that a review happened. PROHIBITED/RESTRICTED/UNKNOWN block enablement.
CREATE TYPE tos_status AS ENUM ('UNKNOWN', 'ALLOWED', 'RESTRICTED', 'PROHIBITED');
CREATE TYPE robots_status AS ENUM ('UNKNOWN', 'ALLOWED', 'DISALLOWED', 'NOT_APPLICABLE');

CREATE TYPE candidate_entity_type AS ENUM (
    'ROBOT', 'MANUFACTURER', 'VARIANT', 'SPEC', 'PRICING', 'AVAILABILITY',
    'DEPLOYMENT', 'IMAGE', 'OTHER');

CREATE TYPE candidate_identity_status AS ENUM (
    'UNRESOLVED', 'MATCHED_EXISTING', 'NEW_ENTITY', 'AMBIGUOUS', 'POSSIBLE_DUPLICATE');

CREATE TYPE candidate_status AS ENUM (
    'DISCOVERED', 'IDENTITY_REVIEW', 'SOURCE_TRACE', 'VERIFICATION',
    'READY_FOR_PROMOTION', 'PROMOTED', 'POSSIBLE_DUPLICATE', 'CONFLICT',
    'INSUFFICIENT_EVIDENCE', 'REJECTED', 'STALE', 'RECHECK_REQUIRED');

CREATE TYPE trace_state AS ENUM (
    'NOT_TRACED', 'TRACE_CONFIRMED', 'TRACE_PARTIAL', 'TRACE_FAILED');

CREATE TYPE claim_status AS ENUM (
    'NOT_VERIFIED', 'VERIFIED', 'CONFLICT', 'REJECTED', 'UNKNOWN');

-- ---------------------------------------------------------------------------
-- DATA-D1.LIVE (docs/16_DATA_D1_LIVE_MARKET_ACQUISITION_CONTRACT.md, RATIFIED
-- v0.1) — live-acquisition types. Slice A is SCHEMA ONLY: these types and the
-- tables below exist so an acquisition run can be recorded, but no adapter, HTTP
-- client, robots fetcher or crawler exists in this slice. Mirrored by
-- db/migrations/0004_add_live_acquisition_layer.sql.
-- ---------------------------------------------------------------------------

-- HALTED_BY_POLICY is first-class, not an error: robots changed, the terms review
-- expired mid-run, or the source began denying access (§7).
CREATE TYPE crawl_run_status AS ENUM (
    'RUNNING', 'COMPLETED', 'FAILED', 'HALTED_BY_POLICY', 'CANCELLED');

-- LIVE.4: v0.1 has exactly one trigger. No scheduler, cron, queue or worker may
-- start a run; a named human does, locally. The enum has one value so that
-- adding an automated trigger is a visible schema change, not a config flag.
CREATE TYPE crawl_trigger AS ENUM ('MANUAL');

CREATE TYPE fetch_outcome AS ENUM (
    'FETCHED', 'NOT_MODIFIED', 'FROM_CACHE', 'BLOCKED_BY_ROBOTS',
    'BLOCKED_BY_SOURCE', 'ERROR', 'SKIPPED_UNCHANGED');

CREATE TYPE extraction_method AS ENUM (
    'SELECTOR', 'JSONLD', 'MICRODATA', 'PATTERN', 'MANUAL');

-- LIVE.8 / owner decision D-6: how sure the PARSER is that it read the page
-- correctly. Deliberately has no VERIFIED value — verification is a human act on
-- claim_status, and a parser must not be able to express it.
CREATE TYPE extraction_confidence AS ENUM ('LOW', 'MEDIUM', 'HIGH');

-- LIVE.7: the three axes that must never collapse into one status label.
CREATE TYPE signal_axis AS ENUM ('MATURITY', 'OBTAINABILITY', 'PRICE');

CREATE TYPE eligibility_decision AS ENUM (
    'ALLOWED', 'RESTRICTED', 'PROHIBITED', 'UNKNOWN');

CREATE TYPE extraction_status AS ENUM (
    'EXTRACTED', 'NOTHING_FOUND', 'AMBIGUOUS', 'ERROR');

-- Which discovery record an evidence excerpt belongs to (§9). A soft subject
-- reference rather than three nullable FKs: the excerpt table is written by the
-- same code path for all three, and a CHECK keeps the pair meaningful.
CREATE TYPE evidence_subject_type AS ENUM (
    'CLAIM', 'COMMERCIAL_SIGNAL', 'IMAGE_REF');

-- Radar registry. DATA-D1.9: is_enabled requires an AFFIRMATIVE ToS-permits-
-- automation decision, a robots decision that is not a disallow, and recorded
-- review attribution + time. Reviewing a source is NOT the same as being allowed.
CREATE TABLE discovery_source (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    key                     TEXT NOT NULL UNIQUE,
    name                    TEXT NOT NULL,
    source_class            discovery_source_class NOT NULL,
    homepage_url            TEXT,
    tos_status              tos_status NOT NULL DEFAULT 'UNKNOWN',
    robots_status           robots_status NOT NULL DEFAULT 'UNKNOWN',
    eligibility_reviewed_at TIMESTAMPTZ,
    eligibility_reviewed_by TEXT,
    is_enabled              BOOLEAN NOT NULL DEFAULT FALSE,
    notes                   TEXT,
    -- DATA-D1.LIVE §5 / LIVE.2 (migration 0004). Asymmetric validity is
    -- deliberate: a terms page is a legal document that changes rarely and
    -- deliberately (90 days, void on a material hash change), while a robots
    -- policy is an operational signal that can change any day and is therefore
    -- re-read every run and never answered from a stored decision (24h max).
    allowed_path_prefixes   TEXT[],       -- exactly what the review covered
    tos_reviewed_at         TIMESTAMPTZ,
    tos_expires_at          TIMESTAMPTZ,  -- reviewed_at + 90d (owner decision D-2)
    tos_page_hash           TEXT,         -- SHA-256; a change voids the review
    last_robots_hash        TEXT,
    last_robots_checked_at  TIMESTAMPTZ,  -- staler than 24h = must re-check
    last_crawled_at         TIMESTAMPTZ,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_discovery_source_eligible CHECK (
        NOT is_enabled OR (
            tos_status = 'ALLOWED'
            AND robots_status IN ('ALLOWED', 'NOT_APPLICABLE')
            AND eligibility_reviewed_at IS NOT NULL
            AND eligibility_reviewed_by IS NOT NULL
        )
    )
);
COMMENT ON TABLE discovery_source IS
    'DATA-D1 radar registry. is_enabled requires an affirmative ToS-permits-automation '
    'decision + non-disallow robots decision + recorded review attribution (DATA-D1.9).';

-- DATA-D1.LIVE §5 — APPEND-ONLY eligibility review record.
--
-- discovery_source carries the *effective* decision; this carries its *history*,
-- so a decision can be audited and re-reviewed rather than silently overwritten.
-- Append-only because an eligibility decision is the artefact that authorizes
-- contacting a third party: if it could be edited, the authorization could be
-- backdated. Enforced at ORM level (models/acquisition.py) and by ON DELETE
-- RESTRICT here, exactly as promotion_audit is.
--
-- The first real use of this record (2026-07-29) found two of three official
-- manufacturer sources PROHIBITING automated access while their robots.txt was
-- permissive — which is why both axes are recorded separately, with their own
-- URL, hash and excerpt.
CREATE TABLE source_eligibility_review (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id           UUID NOT NULL REFERENCES discovery_source(id) ON DELETE RESTRICT,
    -- robots axis
    robots_url          TEXT,
    robots_decision     robots_status NOT NULL DEFAULT 'UNKNOWN',
    robots_page_hash    TEXT,
    robots_excerpt      TEXT,
    -- terms / legal axis
    tos_url             TEXT,
    tos_decision        eligibility_decision NOT NULL DEFAULT 'UNKNOWN',
    tos_page_hash       TEXT,
    tos_excerpt         TEXT,
    -- scope + attribution. reviewed_by is NOT NULL: an unattributed review is
    -- not a review (DATA-D1.9).
    path_prefixes       TEXT[],
    reviewed_by         TEXT NOT NULL,
    reviewed_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    expires_at          TIMESTAMPTZ,
    -- Provisional recommendation vs the owner's decision, kept separate: an
    -- assessment is evidence, enabling the source is a human act (§5 step 5).
    recommendation      eligibility_decision NOT NULL DEFAULT 'UNKNOWN',
    notes               TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_source_eligibility_review_excerpt_len CHECK (
        (robots_excerpt IS NULL OR char_length(robots_excerpt) <= 1000)
        AND (tos_excerpt IS NULL OR char_length(tos_excerpt) <= 1000)
    )
);
COMMENT ON TABLE source_eligibility_review IS
    'DATA-D1.LIVE §5 append-only eligibility history (robots axis + terms axis, each with '
    'URL/hash/excerpt). Append-only: this record is what authorizes contacting a third party.';

-- DATA-D1.LIVE §7 — one acquisition run.
CREATE TABLE crawl_run (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id         UUID NOT NULL REFERENCES discovery_source(id) ON DELETE RESTRICT,
    adapter_key       TEXT NOT NULL,
    adapter_version   TEXT NOT NULL,   -- bump => re-extraction is meaningful (§8)
    trigger           crawl_trigger NOT NULL DEFAULT 'MANUAL',
    operator          TEXT NOT NULL,   -- the named human (LIVE.4)
    status            crawl_run_status NOT NULL DEFAULT 'RUNNING',
    started_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at       TIMESTAMPTZ,
    resume_of_run_id  UUID REFERENCES crawl_run(id) ON DELETE SET NULL,
    run_manifest      JSONB,           -- planned URLs, limits, rate policy, UA, robots hash
    counters          JSONB,           -- the §18 report figures
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- A finished run must say when it finished; a RUNNING one must not.
    CONSTRAINT ck_crawl_run_finished CHECK (
        (status = 'RUNNING' AND finished_at IS NULL)
        OR (status <> 'RUNNING' AND finished_at IS NOT NULL)
    ),
    CONSTRAINT ck_crawl_run_not_self_resume CHECK (resume_of_run_id IS DISTINCT FROM id)
);
COMMENT ON TABLE crawl_run IS
    'DATA-D1.LIVE §7 acquisition run. trigger is MANUAL-only in v0.1 (LIVE.4): no scheduler, '
    'queue or worker may start one. Slice A records runs; it cannot perform them.';

-- DATA-D1.LIVE §8 — per-URL outcome. NO BODY COLUMN: bodies live in the
-- content-addressed on-disk cache outside the database (LIVE.10 / decision D-3),
-- and only the hash, the validators and the outcome are durable here. This table
-- is also what makes a run resumable (§7): a resumed run skips URLs already
-- FETCHED by its parent.
CREATE TABLE fetched_page (
    id                       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crawl_run_id             UUID NOT NULL REFERENCES crawl_run(id) ON DELETE CASCADE,
    source_id                UUID NOT NULL REFERENCES discovery_source(id) ON DELETE RESTRICT,
    url                      TEXT NOT NULL,
    canonical_url            TEXT,
    http_status              INTEGER,
    content_type             TEXT,
    content_length           BIGINT,
    content_hash             TEXT,       -- SHA-256 of the normalized body
    etag                     TEXT,
    last_modified            TEXT,
    retrieved_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    outcome                  fetch_outcome NOT NULL,
    robots_decision_at_fetch robots_status,   -- what robots said AT the request
    error_class              TEXT,
    created_at               TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE fetched_page IS
    'DATA-D1.LIVE §8 per-URL fetch outcome. Deliberately has NO body column (LIVE.10): the '
    'evidence of what a page said is durable, the page itself is not.';

CREATE TABLE discovery_candidate (
    id                        UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_id                 UUID NOT NULL REFERENCES discovery_source(id) ON DELETE CASCADE,
    entity_type               candidate_entity_type NOT NULL DEFAULT 'ROBOT',
    candidate_name            TEXT,
    candidate_manufacturer    TEXT,
    discovery_url             TEXT,
    external_ref              TEXT NOT NULL,            -- required for dependable dedup
    candidate_data            JSONB,                   -- allowlisted leads only (DATA-D1.10)
    identity_status           candidate_identity_status NOT NULL DEFAULT 'UNRESOLVED',
    status                    candidate_status NOT NULL DEFAULT 'DISCOVERED',
    -- Trace = an EXPLICIT confirmation of an authoritative source, distinct from a
    -- discovered lead. A bare official-URL lead never sets these (DATA-D1.2/§9).
    trace_state               trace_state NOT NULL DEFAULT 'NOT_TRACED',
    trace_url                 TEXT,
    trace_source_type         source_type,
    trace_verified_by         TEXT,
    trace_verified_at         TIMESTAMPTZ,
    possible_robot_id         UUID REFERENCES robot(id) ON DELETE SET NULL,
    possible_manufacturer_id  UUID REFERENCES manufacturer(id) ON DELETE SET NULL,
    promoted_robot_id         UUID REFERENCES robot(id) ON DELETE SET NULL,
    discovered_at             TIMESTAMPTZ NOT NULL DEFAULT now(),
    last_seen_at              TIMESTAMPTZ NOT NULL DEFAULT now(),
    created_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at                TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_candidate_source_ref UNIQUE (source_id, external_ref)
);
COMMENT ON TABLE discovery_candidate IS
    'DATA-D1 noncanonical research candidate. Never public (§22/Gate I); canonical '
    'only after the promotion gate (§7). Minimal retention (DATA-D1.10), not a shadow DB.';

CREATE TABLE candidate_claim (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id        UUID NOT NULL REFERENCES discovery_candidate(id) ON DELETE CASCADE,
    field_key           TEXT NOT NULL,
    claimed_value       TEXT,              -- NULL = UNKNOWN (never 0/false)
    unit                TEXT,
    claim_status        claim_status NOT NULL DEFAULT 'NOT_VERIFIED',
    -- DATA-D1.LIVE §9.1: THE claim-level provenance anchor. Every claim resolves
    -- to exactly one classified source (discovery_source.source_class), so two
    -- sources asserting the same value are two rows and never one blended row.
    --
    -- NOT NULL + RESTRICT, not nullable + SET NULL. Gate X requires a write with
    -- no resolvable source to be REJECTED, and "nullable with SET NULL" fails that
    -- twice over: an unattributed claim could be inserted, and deleting a source
    -- would silently strip provenance from claims already made — turning "an
    -- aggregator said so" into an anonymous assertion precisely when the audit
    -- trail matters. RESTRICT makes the source undeletable while its claims live.
    discovery_source_id UUID NOT NULL REFERENCES discovery_source(id) ON DELETE RESTRICT,
    evidence_url        TEXT,
    note                TEXT,
    -- DATA-D1.LIVE §9 (migration 0004). Extraction provenance; the exact
    -- supporting passages live in discovery_evidence_excerpt, not here.
    extractor_key         TEXT,
    extractor_version     TEXT,
    extraction_method     extraction_method,
    extraction_confidence extraction_confidence,   -- never VERIFIED (LIVE.8)
    crawl_run_id          UUID REFERENCES crawl_run(id) ON DELETE SET NULL,
    fetched_page_id       UUID REFERENCES fetched_page(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE candidate_claim IS
    'Per-field claims. Conflicting values are retained side-by-side, never averaged (DATA-D1.8). '
    'discovery_source_id is the DATA-D1.LIVE §9.1 provenance anchor: one claim, one classified source.';

-- Reference-only candidate imagery (R3): http/https URL + metadata, NO binary.
CREATE TABLE candidate_image_ref (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id        UUID NOT NULL REFERENCES discovery_candidate(id) ON DELETE CASCADE,
    image_url           TEXT NOT NULL,
    discovery_source_id UUID REFERENCES discovery_source(id) ON DELETE SET NULL,
    credited_to         TEXT,
    media_status        TEXT NOT NULL DEFAULT 'CANDIDATE',
    note                TEXT,
    -- DATA-D1.LIVE §10 (migration 0004). RETRIEVAL provenance, which is not the
    -- same as claimed authorship: an image credited to a manufacturer but seen on
    -- an aggregator is retrieval_source_class = AGGREGATOR (the Figure 02
    -- precedent). The extractor sets NO MEDIA-01 verdict — identity, rights and
    -- usage basis stay human decisions, so there is deliberately no is_official,
    -- rights_status or usage_basis column here.
    page_url               TEXT,        -- the page it was seen on
    retrieved_at           TIMESTAMPTZ,
    declared_credit        TEXT,        -- the credit line as printed
    attribution_claimed    TEXT,        -- who the page CLAIMS made it (claim only)
    alt_text               TEXT,
    retrieval_source_class discovery_source_class,
    crawl_run_id           UUID REFERENCES crawl_run(id) ON DELETE SET NULL,
    fetched_page_id        UUID REFERENCES fetched_page(id) ON DELETE SET NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_candidate_image_ref_scheme CHECK (image_url ~* '^https?://')
);
COMMENT ON TABLE candidate_image_ref IS
    'DATA-D1 R3: reference-only imagery (http/https URL + metadata, no binary). MEDIA-01 authoritative. '
    'DATA-D1.LIVE §10: retrieval_source_class records where it was SEEN, never claimed authorship.';

-- DATA-D1.LIVE §9 — what one extractor pass over one page produced.
CREATE TABLE extraction_result (
    id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    crawl_run_id      UUID NOT NULL REFERENCES crawl_run(id) ON DELETE CASCADE,
    fetched_page_id   UUID NOT NULL REFERENCES fetched_page(id) ON DELETE CASCADE,
    candidate_id      UUID REFERENCES discovery_candidate(id) ON DELETE SET NULL,
    extractor_key     TEXT NOT NULL,
    extractor_version TEXT NOT NULL,
    entity_type       candidate_entity_type NOT NULL DEFAULT 'ROBOT',
    status            extraction_status NOT NULL,
    notes             TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE extraction_result IS
    'DATA-D1.LIVE §9: one extractor pass over one page. AMBIGUOUS is a real outcome for a human, '
    'never a guess.';

-- DATA-D1.LIVE §9 / LIVE.7 — a commercial signal is NOT a scalar field/value
-- pair, so it is not forced into candidate_claim. The three axes are recorded
-- separately and never merged into one status label: a robot may legitimately be
-- AVAILABLE for PURCHASE in one region and ON_REQUEST elsewhere, which a single
-- label cannot express. UNKNOWN is the absence of a signal and never becomes
-- NOT_AVAILABLE; QUOTE_ONLY is a PRICE fact and never becomes UNKNOWN.
CREATE TABLE candidate_commercial_signal (
    id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id          UUID NOT NULL REFERENCES discovery_candidate(id) ON DELETE CASCADE,
    -- §9.1 provenance anchor, same rule as candidate_claim: one signal, one
    -- classified source. NOT NULL here because this table is new — there is no
    -- pre-existing unattributed row to accommodate.
    discovery_source_id   UUID NOT NULL REFERENCES discovery_source(id) ON DELETE RESTRICT,
    crawl_run_id          UUID REFERENCES crawl_run(id) ON DELETE SET NULL,
    fetched_page_id       UUID REFERENCES fetched_page(id) ON DELETE SET NULL,
    axis                  signal_axis NOT NULL,
    maturity_value        commercial_status,     -- axis = MATURITY
    availability_value    availability_status,   -- axis = OBTAINABILITY
    transaction_type      transaction_type,
    region_code           TEXT,
    buyer_type            buyer_type,
    price_type            price_type,            -- axis = PRICE
    price_amount          NUMERIC(14, 2),
    price_currency        CHAR(3),
    billing_period        billing_period,
    extractor_key         TEXT,
    extractor_version     TEXT,
    extraction_method     extraction_method,
    extraction_confidence extraction_confidence,
    -- Only a human moves this off NOT_VERIFIED (LIVE.8 / DATA-D1.2).
    claim_status          claim_status NOT NULL DEFAULT 'NOT_VERIFIED',
    note                  TEXT,
    created_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at            TIMESTAMPTZ NOT NULL DEFAULT now(),
    -- Each axis carries its OWN value and may not set another axis's. This is
    -- the "three axes never merge" law expressed as a constraint rather than a
    -- convention, so a maturity signal physically cannot write availability.
    CONSTRAINT ck_commercial_signal_axis_value CHECK (
        (axis = 'MATURITY'      AND availability_value IS NULL AND price_type IS NULL)
     OR (axis = 'OBTAINABILITY' AND maturity_value     IS NULL AND price_type IS NULL)
     OR (axis = 'PRICE'         AND maturity_value     IS NULL AND availability_value IS NULL)
    ),
    -- A price amount is meaningless without both a currency and a stated price
    -- semantics; QUOTE_ONLY legitimately has no amount.
    CONSTRAINT ck_commercial_signal_price CHECK (
        price_amount IS NULL
        OR (price_currency IS NOT NULL AND price_type IS NOT NULL)
    )
);
COMMENT ON TABLE candidate_commercial_signal IS
    'DATA-D1.LIVE §9/LIVE.7: maturity, obtainability and price semantics as SEPARATE '
    'evidence-bound signals. A CHECK stops one axis writing another. Conflicts are separate rows.';

-- DATA-D1.LIVE §9 / LIVE.6 (owner decision D-7) — the exact supporting passages.
-- One claim or signal, MANY excerpts: a price and the region it applies to may
-- sit in different parts of a page, so a single column could not honestly justify
-- a claim. 1000 UNICODE CHARACTERS per excerpt, CHECK-enforced — char_length()
-- counts characters, not bytes, which is what the ratified limit says.
CREATE TABLE discovery_evidence_excerpt (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    subject_type    evidence_subject_type NOT NULL,
    subject_id      UUID NOT NULL,          -- soft ref: claim / signal / image_ref
    -- §9.1: an excerpt is evidence FOR a claim, so it carries the same source FK
    -- the claim does. Without it an excerpt could be quoted at a claim it did not
    -- come from, which is the one thing an evidence table must make impossible.
    -- The polymorphic subject cannot be a real FK, so a trigger
    -- (assert_evidence_excerpt_subject) enforces that the subject exists, has a
    -- source, and that its source is THIS one.
    discovery_source_id UUID NOT NULL REFERENCES discovery_source(id) ON DELETE RESTRICT,
    crawl_run_id    UUID REFERENCES crawl_run(id) ON DELETE SET NULL,
    fetched_page_id UUID REFERENCES fetched_page(id) ON DELETE SET NULL,
    excerpt_text    TEXT NOT NULL,
    page_url        TEXT NOT NULL,
    retrieved_at    TIMESTAMPTZ NOT NULL,
    page_hash       TEXT,
    locator         TEXT,                   -- selector / XPath / pointer / offset:A-B
    ordinal         INTEGER NOT NULL DEFAULT 0,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT ck_evidence_excerpt_len CHECK (char_length(excerpt_text) <= 1000),
    CONSTRAINT ck_evidence_excerpt_not_blank CHECK (btrim(excerpt_text) <> ''),
    UNIQUE (subject_type, subject_id, ordinal)
);
COMMENT ON TABLE discovery_evidence_excerpt IS
    'DATA-D1.LIVE §9/LIVE.6: exact supporting passages, <=1000 Unicode chars each, many per '
    'claim. A claim that cannot carry its supporting text is not recorded.';

-- Promotion lineage (§19 / Gate J). Durable: ON DELETE RESTRICT so a candidate
-- with promotion history cannot be deleted out from under the audit trail.
CREATE TABLE promotion_audit (
    id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    candidate_id         UUID NOT NULL REFERENCES discovery_candidate(id) ON DELETE RESTRICT,
    action               TEXT NOT NULL,
    promoted_entity_type candidate_entity_type,
    promoted_robot_id    UUID REFERENCES robot(id) ON DELETE SET NULL,
    evidence_source_id   UUID,   -- soft ref to evidence_source(id)
    approved_by          TEXT NOT NULL,
    detail               JSONB,
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);
COMMENT ON TABLE promotion_audit IS
    'DATA-D1 §19/Gate J: human-approval + promotion lineage (candidate -> evidence -> robot). '
    'Append-only + delete-restricted so lineage survives.';

CREATE INDEX idx_candidate_source          ON discovery_candidate (source_id);
CREATE INDEX idx_candidate_status          ON discovery_candidate (status);
CREATE INDEX idx_candidate_possible_robot  ON discovery_candidate (possible_robot_id);
CREATE INDEX idx_candidate_claim_candidate ON candidate_claim (candidate_id);
CREATE INDEX idx_candidate_image_candidate ON candidate_image_ref (candidate_id);
CREATE INDEX idx_promotion_audit_candidate ON promotion_audit (candidate_id);

-- DATA-D1.LIVE §16 acquisition-layer indexes.
CREATE INDEX idx_eligibility_review_source   ON source_eligibility_review (source_id, reviewed_at DESC);
CREATE INDEX idx_crawl_run_source            ON crawl_run (source_id, started_at DESC);
CREATE INDEX idx_crawl_run_status            ON crawl_run (status);
CREATE INDEX idx_fetched_page_run            ON fetched_page (crawl_run_id);
CREATE INDEX idx_fetched_page_url            ON fetched_page (source_id, url);
CREATE INDEX idx_fetched_page_hash           ON fetched_page (content_hash);
CREATE INDEX idx_extraction_result_run       ON extraction_result (crawl_run_id);
CREATE INDEX idx_extraction_result_candidate ON extraction_result (candidate_id);
CREATE INDEX idx_commercial_signal_candidate ON candidate_commercial_signal (candidate_id);
CREATE INDEX idx_commercial_signal_source    ON candidate_commercial_signal (discovery_source_id);
CREATE INDEX idx_evidence_excerpt_subject    ON discovery_evidence_excerpt (subject_type, subject_id);
CREATE INDEX idx_candidate_claim_source      ON candidate_claim (discovery_source_id);

-- =============================================================================
-- DATA-D1.LIVE integrity enforcement — the DATABASE refuses forbidden states
-- =============================================================================
-- The distinction these triggers exist to close: "the normal ORM path behaves
-- correctly" is not the same as "the database cannot represent a forbidden
-- state". ORM listeners are cooperative — raw SQL, a Core bulk statement, a psql
-- session or SQLAdmin's bulk paths all bypass them, and the earlier SQLAdmin
-- mutation bypass is exactly that failure already having happened once here.

-- §5 — source_eligibility_review is append-only, enforced by the database.
--
-- FOR EACH STATEMENT, not FOR EACH ROW: a row-level trigger never fires for a
-- statement that matches nothing, so `UPDATE ... WHERE <no match>` would appear
-- to succeed. Statement level refuses the *attempt*, which is the honest
-- semantics for a record that authorizes contacting a third party — if it could
-- be edited, an authorization could be backdated and DATA-D1.9 would be
-- forgeable.
CREATE OR REPLACE FUNCTION refuse_eligibility_review_mutation()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    RAISE EXCEPTION
        'source_eligibility_review is append-only (DATA-D1.LIVE §5): % refused. '
        'Record a NEW review instead — an eligibility decision is evidence, and '
        'evidence is not edited.', TG_OP
        USING ERRCODE = 'restrict_violation';
END$$;
COMMENT ON FUNCTION refuse_eligibility_review_mutation() IS
    'DATA-D1.LIVE §5: refuses UPDATE/DELETE on source_eligibility_review at the database '
    'level, so raw SQL and bulk Core statements cannot bypass it.';

CREATE TRIGGER trg_source_eligibility_review_no_update
    BEFORE UPDATE ON source_eligibility_review
    FOR EACH STATEMENT EXECUTE FUNCTION refuse_eligibility_review_mutation();
CREATE TRIGGER trg_source_eligibility_review_no_delete
    BEFORE DELETE ON source_eligibility_review
    FOR EACH STATEMENT EXECUTE FUNCTION refuse_eligibility_review_mutation();

-- §9.1 / §8 — run / page / source lineage must agree.
--
-- A row may name a crawl run, a fetched page and a source. Postgres cannot
-- express "this page belongs to that run" as a foreign key, so without this a
-- claim could cite a page fetched during a different run, or from a different
-- source, and the provenance chain would read as sound while being false.
-- Reads NEW through to_jsonb so one function serves every table that carries
-- some subset of the three columns.
CREATE OR REPLACE FUNCTION assert_acquisition_lineage()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    row_json  JSONB := to_jsonb(NEW);
    v_run_id  UUID  := NULLIF(row_json->>'crawl_run_id', '')::UUID;
    v_page_id UUID  := NULLIF(row_json->>'fetched_page_id', '')::UUID;
    -- `fetched_page` names its source column `source_id`; everything else uses
    -- `discovery_source_id`. Reading only the latter made the root-level check
    -- (a page must belong to its run's source) silently skip — the trigger was
    -- present and passing while enforcing nothing there.
    v_src_id  UUID  := COALESCE(
        NULLIF(row_json->>'discovery_source_id', '')::UUID,
        NULLIF(row_json->>'source_id', '')::UUID
    );
    page_run  UUID;
    page_src  UUID;
    run_src   UUID;
BEGIN
    IF v_page_id IS NOT NULL THEN
        SELECT crawl_run_id, source_id INTO page_run, page_src
        FROM fetched_page WHERE id = v_page_id;

        IF v_run_id IS NOT NULL AND page_run <> v_run_id THEN
            RAISE EXCEPTION
                '%.fetched_page_id % belongs to crawl run %, not %',
                TG_TABLE_NAME, v_page_id, page_run, v_run_id
                USING ERRCODE = 'foreign_key_violation';
        END IF;
        IF v_src_id IS NOT NULL AND page_src <> v_src_id THEN
            RAISE EXCEPTION
                '%.fetched_page_id % was fetched from source %, not %',
                TG_TABLE_NAME, v_page_id, page_src, v_src_id
                USING ERRCODE = 'foreign_key_violation';
        END IF;
    END IF;

    IF v_run_id IS NOT NULL AND v_src_id IS NOT NULL THEN
        SELECT source_id INTO run_src FROM crawl_run WHERE id = v_run_id;
        IF run_src <> v_src_id THEN
            RAISE EXCEPTION
                '%.crawl_run_id % ran against source %, not %',
                TG_TABLE_NAME, v_run_id, run_src, v_src_id
                USING ERRCODE = 'foreign_key_violation';
        END IF;
    END IF;

    RETURN NEW;
END$$;
COMMENT ON FUNCTION assert_acquisition_lineage() IS
    'DATA-D1.LIVE: run/page/source lineage must agree. Postgres cannot express '
    '"this page belongs to that run" as a foreign key, so this closes it.';

-- §9 — an evidence excerpt must belong to a real subject, with the SAME source.
--
-- `subject_type + subject_id` is a polymorphic soft reference, so no foreign key
-- can protect it. Left unchecked it accepts any random UUID, which would make the
-- evidence table capable of holding excerpts attached to nothing at all — an
-- orphan quotation is indistinguishable from a fabricated one.
CREATE OR REPLACE FUNCTION assert_evidence_excerpt_subject()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
DECLARE
    subject_src UUID;
    found       BOOLEAN := FALSE;
BEGIN
    CASE NEW.subject_type
        WHEN 'CLAIM' THEN
            SELECT discovery_source_id, TRUE INTO subject_src, found
            FROM candidate_claim WHERE id = NEW.subject_id;
        WHEN 'COMMERCIAL_SIGNAL' THEN
            SELECT discovery_source_id, TRUE INTO subject_src, found
            FROM candidate_commercial_signal WHERE id = NEW.subject_id;
        WHEN 'IMAGE_REF' THEN
            SELECT discovery_source_id, TRUE INTO subject_src, found
            FROM candidate_image_ref WHERE id = NEW.subject_id;
        ELSE
            RAISE EXCEPTION 'unknown evidence subject_type %', NEW.subject_type
                USING ERRCODE = 'check_violation';
    END CASE;

    IF NOT found THEN
        RAISE EXCEPTION
            'evidence excerpt subject %/% does not exist — an orphan excerpt is '
            'indistinguishable from a fabricated one (DATA-D1.LIVE §9)',
            NEW.subject_type, NEW.subject_id
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    -- candidate_image_ref.discovery_source_id predates this contract and is
    -- nullable; an excerpt may not hang off an unattributed subject regardless.
    IF subject_src IS NULL THEN
        RAISE EXCEPTION
            'evidence excerpt subject %/% has no source, so its evidence cannot '
            'be attributed (DATA-D1.LIVE §9.1)', NEW.subject_type, NEW.subject_id
            USING ERRCODE = 'not_null_violation';
    END IF;

    IF subject_src <> NEW.discovery_source_id THEN
        RAISE EXCEPTION
            'evidence excerpt source % does not match subject %/% source % — an '
            'excerpt must be evidence FOR the claim it is attached to',
            NEW.discovery_source_id, NEW.subject_type, NEW.subject_id, subject_src
            USING ERRCODE = 'foreign_key_violation';
    END IF;

    RETURN NEW;
END$$;
COMMENT ON FUNCTION assert_evidence_excerpt_subject() IS
    'DATA-D1.LIVE §9/§9.1: the polymorphic excerpt subject must exist, have a source, '
    'and share it with the excerpt. No foreign key can express this.';

CREATE TRIGGER trg_evidence_excerpt_subject
    BEFORE INSERT OR UPDATE ON discovery_evidence_excerpt
    FOR EACH ROW EXECUTE FUNCTION assert_evidence_excerpt_subject();

-- Lineage applies to every acquisition row that can name a run and a page.
CREATE TRIGGER trg_fetched_page_lineage
    BEFORE INSERT OR UPDATE ON fetched_page
    FOR EACH ROW EXECUTE FUNCTION assert_acquisition_lineage();
CREATE TRIGGER trg_extraction_result_lineage
    BEFORE INSERT OR UPDATE ON extraction_result
    FOR EACH ROW EXECUTE FUNCTION assert_acquisition_lineage();
CREATE TRIGGER trg_candidate_claim_lineage
    BEFORE INSERT OR UPDATE ON candidate_claim
    FOR EACH ROW EXECUTE FUNCTION assert_acquisition_lineage();
CREATE TRIGGER trg_commercial_signal_lineage
    BEFORE INSERT OR UPDATE ON candidate_commercial_signal
    FOR EACH ROW EXECUTE FUNCTION assert_acquisition_lineage();
CREATE TRIGGER trg_evidence_excerpt_lineage
    BEFORE INSERT OR UPDATE ON discovery_evidence_excerpt
    FOR EACH ROW EXECUTE FUNCTION assert_acquisition_lineage();

-- discovery_source / discovery_candidate / candidate_claim carry updated_at; give
-- them the same maintenance trigger as the canonical tables above.
DO $$
DECLARE t TEXT;
BEGIN
    FOR t IN SELECT unnest(ARRAY['discovery_source','discovery_candidate','candidate_claim',
                                 'candidate_commercial_signal'])
    LOOP
        EXECUTE format(
            'CREATE TRIGGER trg_%1$s_updated BEFORE UPDATE ON %1$s
             FOR EACH ROW EXECUTE FUNCTION set_updated_at();', t);
    END LOOP;
END$$;

-- =============================================================================
-- END OF SCHEMA
-- =============================================================================
