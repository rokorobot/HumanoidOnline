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

export interface RobotListItem {
  id: string;
  slug: string;
  name: string;
  manufacturer: ManufacturerRef;
  summary?: string | null;
  hero_image_url?: string | null;
  commercial_status: string;
  payload_kg?: number | null;
  height_cm?: number | null;
  mobility?: string | null;
  price_display?: PriceDisplay | null;
  available_modes: string[];
  deployment_count: number;
}

export interface StatusHistoryEntry {
  status: string;
  effective_at: string;
  note?: string | null;
}

export interface SpecsBlock {
  height_cm?: number | null;
  weight_kg?: number | null;
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
  evidence?: Evidence | null;
}

export interface AvailabilityOffer {
  transaction_type: string;
  availability_status: string;
  region?: string | null;
  provider?: string | null;
  available_from?: string | null;
  lead_time_days?: number | null;
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
  status_history: StatusHistoryEntry[];
  specs: SpecsBlock;
  extended_specs: ExtendedSpec[];
  capabilities: Capability[];
  variants: Variant[];
  use_case_fits: UseCaseFit[];
  pricing_offers: PricingOffer[];
  availability_offers: AvailabilityOffer[];
  deployments: Deployment[];
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
  robot_count: number;
  deployment_status?: string | null;
  // Derived from published robots' commercial_status (not the deployment column).
  portfolio_status?: string | null;
}

export interface ManufacturerRobot {
  slug: string;
  name: string;
  commercial_status: string;
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

export interface ManufacturerDetail {
  id: string;
  slug: string;
  name: string;
  legal_name?: string | null;
  country?: string | null;
  website_url?: string | null;
  founded_year?: number | null;
  description?: string | null;
  commercial_model?: string | null;
  deployment_status?: string | null;
  is_public_company: boolean;
  ticker?: string | null;
  robots: ManufacturerRobot[];
  providers: Provider[];
  deployments: ManufacturerDeployment[];
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

export interface MarketSnapshot {
  total_tracked: number;
  commercially_accessible: number;
  in_deployment_or_pilot: number;
  manufacturers: number;
  rental_offers_present: boolean;
  latest_observed_at?: string | null;
}
