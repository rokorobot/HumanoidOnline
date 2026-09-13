// Typed mirror of the HumanoidOnline READ API (docs/04_API_CONTRACT.md).
// Enum-valued fields are typed as string: values arrive verbatim from the API
// and are rendered verbatim (docs/03_DATA_DICTIONARY.md). `null` always means
// UNKNOWN — never 0/false/"" (API contract §conventions).

export interface Page<T> {
  items: T[];
  total: number;
  limit: number;
  offset: number;
}

export interface ManufacturerRef {
  slug: string;
  name: string;
  country?: string | null;
}

export interface PriceDisplay {
  // `type` is a price_type enum: PUBLIC | FROM | RANGE | ESTIMATED | QUOTE_ONLY.
  // The whole object is null (not present) when there are no pricing rows
  // (UNKNOWN price). QUOTE_ONLY is a *known* fact with amount null.
  type: string;
  amount?: number | null;
  amount_min?: number | null;
  amount_max?: number | null;
  currency?: string | null;
  billing_period?: string | null;
  // All of this comes from the SAME offer row as the amount above: the seller,
  // the region that offer is scoped to, the basis it is quoted on and whether it
  // can be ordered. Rendering the number without them would show one supplier's
  // price under another supplier's terms.
  provider?: string | null;
  region?: string | null;
  price_basis?: string | null;
  order_status_note?: string | null;
  // null = the edition match was never assessed. Never render it as "confirmed".
  edition_confirmed?: boolean | null;
  // The configuration this amount was quoted for, when the offer is scoped to
  // one. Rendered with the price so a variant's figure is never read as the
  // price of every configuration.
  variant?: string | null;
}

export interface Evidence {
  source_type: string;
  confidence: string;
  // observed_at is always present (TIMESTAMPTZ NOT NULL); published/verified are
  // nullable. These three dates stay SEPARATE — never a synthetic freshness value.
  observed_at: string;
  verified_at?: string | null;
  published_at?: string | null;
  source_url?: string | null;
}

export interface RobotImagePrimary {
  image_url: string;
  source_name?: string | null;
  is_official: boolean;
}

export interface RobotListItem {
  id: string;
  slug: string;
  name: string;
  manufacturer: ManufacturerRef;
  summary?: string | null;
  hero_image_url?: string | null;
  // MEDIA-01 catalogue-card image (display-eligible primary; null -> unavailable).
  primary_image?: RobotImagePrimary | null;
  commercial_status: string;
  payload_kg?: number | null;
  height_cm?: number | null;
  mobility?: string | null;
  price_display?: PriceDisplay | null;
  available_modes: string[];
  deployment_count: number;
  updated_at: string; // sitemap lastmod (AGENT-01)
}

export interface StatusHistoryEntry {
  status: string;
  effective_at: string;
  note?: string | null;
}

export interface SpecsBlock {
  height_cm?: number | null;
  weight_kg?: number | null;
  // Span is fingertip-to-fingertip, reach is one arm from its shoulder. Two
  // different measurements; a missing one stays null, never borrowed from the other.
  arm_span_cm?: number | null;
  reach_cm?: number | null;
  payload_kg?: number | null;
  walk_speed_ms?: number | null;
  runtime_minutes?: number | null;
  battery_wh?: number | null;
  mobility?: string | null;
  degrees_of_freedom?: number | null;
  hand_type?: string | null;
  hand_dof?: number | null;
  autonomy?: string | null;
  has_manipulation?: boolean | null;
  has_teleoperation?: boolean | null;
  has_vision?: boolean | null;
  has_language_ui?: boolean | null;
  has_sdk?: boolean | null;
  has_api?: boolean | null;
  ros_support?: boolean | null;
  developer_edition?: boolean | null;
  simulation_support?: boolean | null;
}

export interface ExtendedSpec {
  key: string;
  label: string;
  value?: number | boolean | string | null;
  unit?: string | null;
  category: string;
  // Attribution travels with the value (these specs carry no evidence row).
  source_label?: string | null;
  source_url?: string | null;
  // MANUFACTURER | MANUFACTURER_DOC | COMPONENT_MANUFACTURER | RESELLER_CLAIM
  source_kind?: string | null;
  // THIS_EDITION | PRODUCT_LINE | PLATFORM
  edition_scope?: string | null;
  observed_at?: string | null;
}

export interface SpecCaveat {
  // The spec field this explains. A caveat explains a NULL; it never fills one.
  field: string;
  text: string;
}

export interface Capability {
  slug: string;
  name: string;
  supported: boolean;
  detail?: string | null;
}

export interface Variant {
  slug: string;
  name: string;
  is_developer: boolean;
}

export interface UseCaseFit {
  use_case: string;
  fit_score?: number | null;
  commercial_readiness?: string | null;
  limitations?: string | null;
}

export interface PricingOffer {
  transaction_type: string;
  price_type: string;
  price?: number | null;
  price_min?: number | null;
  price_max?: number | null;
  currency: string;
  billing_period: string;
  region?: string | null;
  provider?: string | null;
  // One fact per field, so none of them has to be parsed out of prose.
  price_basis?: string | null;
  shipping_terms?: string | null;
  package_contents?: string | null;
  // What THIS seller warrants. A manufacturer's edition-level warranty is a
  // property of the robot and appears among the extended specifications.
  warranty_terms?: string | null;
  order_status_note?: string | null;
  // null = not assessed (never shown as confirmed); false = qualified listing.
  edition_confirmed?: boolean | null;
  edition_note?: string | null;
  evidence?: Evidence | null;
}

export interface AvailabilityOffer {
  transaction_type: string;
  availability_status: string;
  region?: string | null;
  provider?: string | null;
  available_from?: string | null;
  lead_time_days?: number | null;
  // The seller's own sentence, and a delivery estimate that states the country
  // it was given for. Never widen a domestic estimate to a region.
  seller_wording?: string | null;
  delivery_estimate_label?: string | null;
  evidence?: Evidence | null;
}

export interface Deployment {
  customer_name?: string | null;
  region?: string | null;
  use_case?: string | null;
  transaction_type?: string | null;
  unit_count?: number | null;
  contract_value?: number | null;
  summary?: string | null;
  evidence?: Evidence | null;
}

export interface RobotDetail {
  id: string;
  slug: string;
  name: string;
  manufacturer: ManufacturerRef;
  commercial_status: string;
  summary?: string | null;
  description?: string | null;
  hero_image_url?: string | null;
  announced_year?: number | null;
  // The manufacturer's own page for this model (identity/provenance).
  official_url?: string | null;
  status_history: StatusHistoryEntry[];
  specs: SpecsBlock;
  // Why a spec is UNKNOWN, or which sources conflict, keyed by field name.
  spec_caveats: SpecCaveat[];
  extended_specs: ExtendedSpec[];
  capabilities: Capability[];
  variants: Variant[];
  use_case_fits: UseCaseFit[];
  pricing_offers: PricingOffer[];
  availability_offers: AvailabilityOffer[];
  deployments: Deployment[];
  // MEDIA-01: display-eligible verified images only (primary first). Empty -> the
  // UI must render the IMAGE_UNAVAILABLE state, never a generated/placeholder fill.
  images: RobotImage[];
}

export interface RobotImage {
  image_url: string;
  image_type: string;
  source_name?: string | null;
  source_url?: string | null;
  source_type: string;
  is_official: boolean;
  is_primary: boolean;
  attribution?: string | null;
  // The asset shows the product line/chassis, not this exact edition. When true
  // the caption MUST be rendered with the image — an unlabelled stand-in reads
  // as a claim about the exact edition (docs/09 §4).
  is_representative?: boolean;
  representative_note?: string | null;
}

export interface CompareRow {
  group: string;
  key: string;
  label: string;
  values: Record<string, number | boolean | string | null>;
}

export interface CompareResponse {
  robots: RobotDetail[];
  rows: CompareRow[];
}

export interface ManufacturerListItem {
  slug: string;
  name: string;
  country?: string | null;
  // Tracked = all catalogue records for this maker; published = those with a
  // public profile. Kept apart so a card can never claim a maker has no robots.
  tracked_robot_count: number;
  published_robot_count: number;
  deployment_status?: string | null;
  // Derived from published robots' commercial_status (not the deployment column).
  portfolio_status?: string | null;
  updated_at: string; // sitemap lastmod (AGENT-01)
}

export interface ManufacturerRobot {
  slug: string;
  name: string;
  commercial_status: string;
  // MEDIA-01 governed thumbnail (display-eligible primary; null -> unavailable).
  primary_image?: RobotImagePrimary | null;
}

export interface Provider {
  slug: string;
  name: string;
  type: string;
}

export interface ManufacturerDeployment {
  robot_slug: string;
  customer_name?: string | null;
  region?: string | null;
  summary?: string | null;
}

export interface ManufacturerSource {
  // Profile fields this company-level source supports.
  claim_fields: string[];
  source_type: string;
  source_title?: string | null;
  source_url?: string | null;
  published_at?: string | null;
  observed_at: string;
  verified_at?: string | null;
  confidence: string;
  // "AGENT_ASSISTED_RESEARCH" when an agent retrieved the source (docs/26).
  retrieval?: string | null;
}

export interface ManufacturerDetail {
  id: string;
  slug: string;
  name: string;
  legal_name?: string | null;
  // Headquarters country code — not incorporation, not an operating location.
  country?: string | null;
  headquarters_city?: string | null;
  incorporation?: string | null;
  operating_locations: string[];
  website_url?: string | null;
  founded_year?: number | null;
  description?: string | null;
  target_markets: string[];
  commercial_model?: string | null;
  // Humanoid deployment status and the basis it rests on.
  deployment_status?: string | null;
  deployment_note?: string | null;
  // null = unknown; never rendered as NO.
  is_public_company?: boolean | null;
  ticker?: string | null;
  parent_company?: string | null;
  parent_listing?: string | null;
  parent_relationship?: string | null;
  tracked_robot_count: number;
  published_robot_count: number;
  robots: ManufacturerRobot[];
  providers: Provider[];
  deployments: ManufacturerDeployment[];
  sources: ManufacturerSource[];
}

export interface UseCaseListItem {
  slug: string;
  name: string;
  category?: string | null;
  robot_count: number;
}

export interface SuitableRobot {
  slug: string;
  name: string;
  fit_score?: number | null;
  commercial_readiness?: string | null;
  limitations?: string | null;
  // MEDIA-01 governed thumbnail (display-eligible primary; null -> unavailable).
  primary_image?: RobotImagePrimary | null;
}

export interface UseCaseDetail {
  id: string;
  slug: string;
  name: string;
  category?: string | null;
  description?: string | null;
  typical_tasks?: string[] | null;
  typical_requirements?: string | null;
  key_limitations?: string | null;
  suitable_robots: SuitableRobot[];
}

export interface RegionListItem {
  code: string;
  name: string;
  type: string;
  iso_country?: string | null;
}

export interface MatchRobotRef {
  slug: string;
  name: string;
  manufacturer: string;
}

export interface MatchItem {
  robot: MatchRobotRef;
  score: number;
  rank: number;
  category: string;
  // Six stable keys; each value is the criterion's weighted contribution in points.
  score_breakdown: Record<string, number>;
  reasons: string[];
  warnings: string[];
}

export interface MatchResponse {
  requirement_id: string;
  matches: MatchItem[];
  excluded_count: number;
  no_match_explanation?: string | null;
}

// Anonymous requirement read (Adjust Requirements prefill). raw_input carries the
// versioned wizard answers the wizard re-seeds from.
export interface RequirementRead {
  id: string;
  use_case?: string | null;
  country?: string | null;
  raw_input?: Record<string, unknown> | null;
}

// TRACKED = everything the intelligence catalogue holds. PUBLISHED = the
// editorially approved subset with a public profile. Never label one as the
// other. Obtainability and pilot/deployment stay published-scoped.
export interface MarketSnapshot {
  total_tracked: number;
  total_published: number;
  commercially_accessible: number;
  in_deployment_or_pilot: number;
  manufacturers_tracked: number;
  manufacturers_published: number;
  rental_offers_present: boolean;
  latest_observed_at?: string | null;
}

// ---- DATA-D1 operator review surface ---------------------------------------
// NONCANONICAL. A discovery candidate is what a source CLAIMS exists; it is not a
// catalogue robot and carries no verified fact. Deliberately no specs, price,
// availability, maturity or imagery — see apps/api/app/schemas/discovery_review.py.
export interface DiscoveryCandidateReview {
  id: string;
  candidate_name: string | null;
  candidate_manufacturer: string | null;
  external_ref: string;
  discovery_url: string | null;
  /** An official-URL LEAD, not a confirmed trace. `null` when there is none. */
  official_url: string | null;
  source_name: string;
  source_class: string;
  status: string;
  identity_status: string;
  trace_state: string;
  discovered_at: string;
  last_seen_at: string;
}
