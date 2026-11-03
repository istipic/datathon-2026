import type { Feature, Point, Polygon } from 'geojson';

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
