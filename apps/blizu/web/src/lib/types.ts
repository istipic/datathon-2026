import type { Feature, FeatureCollection, MultiLineString, Point, Polygon } from 'geojson';

/** Types of the Blizu API responses (see apps/blizu/api/src/blizu_api/service.py, planner.py). */

export type PersonaId = 'opce' | 'starija' | 'roditelj' | 'kolica';
export type CategoryId =
  | 'lijecnik'
  | 'ljekarna'
  | 'vrtic'
  | 'skola'
  | 'knjiznica'
  | 'posta'
  | 'prijevoz'
  | 'park'
  | 'namirnice';
export type Grade = 'A' | 'B' | 'C' | 'D' | 'E';
export type ConfidenceLevel = 'visoka' | 'srednja' | 'niska';

export const PERSONA_IDS: PersonaId[] = ['opce', 'starija', 'roditelj', 'kolica'];
export const CATEGORY_IDS: CategoryId[] = [
  'lijecnik',
  'ljekarna',
  'vrtic',
  'skola',
  'knjiznica',
  'posta',
  'prijevoz',
  'park',
  'namirnice',
];

export interface NearestFacility {
  name: string;
  address: string | null;
  lon: number;
  lat: number;
  source_id: string;
}

export interface CategoryResult {
  category: CategoryId;
  label: string;
  minutes: number | null;
  score: number;
  weight: number;
  nearest: NearestFacility | null;
  tier: string | null;
  freshness_days: number | null;
  confidence: number | null;
  has_data: boolean;
  good_min: number;
  max_min: number;
  distance_m?: number;
  beyond_limit_m?: number;
}

export interface AccessResult {
  index: number | null;
  grade: Grade | null;
  confidence: { value: number; label: ConfidenceLevel } | null;
  persona: PersonaId;
  snapped_distance_m: number;
  categories: CategoryResult[];
  warnings: string[];
  scoring_version: number;
  computed_at: string;
}

export interface CompareResult {
  persona: PersonaId;
  a: AccessResult;
  b: AccessResult;
  differences: {
    category: CategoryId;
    label: string;
    minutes_diff: number | null;
    score_diff: number;
  }[];
  index_diff: number | null;
}

export interface GeocodeItem {
  label: string;
  /** Short title built by the API, e.g. "Ilica 200". */
  title: string;
  lat: number;
  lon: number;
  type: string | null;
}
export interface GeocodeResponse {
  results: GeocodeItem[];
  attribution: string;
  fetched_at: string;
  from_cache: boolean;
}

export interface NeedSummary {
  category: CategoryId;
  persona: PersonaId;
  pop_group_label: string;
  has_age_groups: boolean;
  pop_group_total: number;
  share_within_g: number | null;
  good_min: number;
  max_min: number;
  unmet_total: number;
  breaks: number[];
}
export interface NeedCollection {
  type: 'FeatureCollection';
  features: Feature<
    Polygon,
    { grd_id: string; pop_group: number; mean_minutes: number | null; unmet: number }
  >[];
  summary: NeedSummary;
}

export interface OptimiseSite {
  lon: number;
  lat: number;
  street: string | null;
  newly_covered: number;
}
export interface OptimiseResult {
  category: CategoryId;
  persona: PersonaId;
  k: number;
  pop_group_label: string;
  radius_m: number;
  good_min: number;
  sites: OptimiseSite[];
  total_newly_covered: number;
  share_before: number;
  share_after: number;
  cells: OptimiseCell[];
}

export interface FacilityCollection {
  type: 'FeatureCollection';
  features: Feature<
    Point,
    {
      id: number;
      category: CategoryId;
      name: string;
      address: string | null;
      source_id: string;
      tier: string;
    }
  >[];
  total: number;
  truncated: boolean;
}

export interface ScoringConfigJson {
  version: number;
  updated: string;
  personas: Record<PersonaId, { label: string; speed_mps: number; graph: string }>;
  categories: Record<
    CategoryId,
    {
      label: string;
      good_min: number;
      max_min: number;
      group: string;
      weights: Record<PersonaId, number>;
    }
  >;
  group_labels: Record<string, string>;
  grades: Record<string, number>;
  confidence: {
    tier_factor: Record<string, number>;
    freshness: { max_months: number | null; factor: number }[];
    labels: Record<string, number>;
  };
}

/** `GET /api/v1/isochrone`: streets grouped in 0.25-minute buckets plus the facilities in reach. */
export interface IsochroneFacility {
  id: number;
  category: CategoryId;
  name: string;
  t: number;
  lon: number;
  lat: number;
}
export interface IsochroneResult {
  origin: { lon: number; lat: number; snapped_m: number };
  persona: PersonaId;
  speed_mps: number;
  max_min: number;
  bucket_min: number;
  buckets: FeatureCollection<MultiLineString, { t: number }>;
  facilities: IsochroneFacility[];
  /** Cumulative counts per threshold in minutes ("5", "10", ...), categories with zero omitted. */
  counts: Record<string, Partial<Record<CategoryId, number>>>;
}

/** `GET /api/v1/route`: shortest walking path to the nearest facility of a category. */
export interface RouteResult {
  persona: PersonaId;
  category: CategoryId;
  speed_mps: number;
  origin: { lon: number; lat: number; snapped_m: number };
  minutes: number;
  distance_m: number;
  facility: {
    id: number;
    category: CategoryId;
    name: string;
    address: string | null;
    lon: number;
    lat: number;
    source_id: string;
    tier: string;
  };
  coordinates: [number, number][];
}

/** One 1 km cell before/after the suggested sites (`cells` of `POST /plan/optimise`). */
export interface OptimiseCell {
  cell_id: string;
  /** People of the target group beyond the good limit; sums to `total_newly_covered`. */
  unmet_before: number;
  unmet_after: number;
  /** Same units as `/plan/need` `unmet` (the legend thresholds apply to these). */
  need_before: number;
  need_after: number;
}
