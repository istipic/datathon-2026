import type { Feature, Polygon } from 'geojson';

export type Band = 'niska' | 'umjerena' | 'visoka' | 'vrlo visoka';
export type Confidence = 'visoka' | 'srednja' | 'niska';

export interface GeocodeItem {
  label: string;
  title: string;
  lat: number;
  lon: number;
  type: string | null;
}
export interface GeocodeResponse {
  results: GeocodeItem[];
  attribution: string;
  cached: boolean;
}

export interface ActionItem {
  id: string;
  text: string;
  source_title: string;
  source_url: string;
}

export interface FloodBlock {
  level: number | null;
  band: Band | null;
  method: string;
  message: string | null;
  map_year: number;
  disclaimer: string;
  ladder: string;
  wms: { url: string; layers: Record<'high' | 'medium' | 'low', string> };
}

export interface HeatBlock {
  status: 'ready' | 'unavailable';
  message: string | null;
  band: Band | null;
  score: number | null;
  percentile?: number | null;
  base_hot_days?: number;
  future_hot_days?: { mean: number; min: number; max: number };
  base_tropical_nights?: number | null;
  future_tropical_nights?: number | null;
  models?: string[];
  periods?: { base: string; future: string };
  model_point?: { lat: number; lon: number; approximate: boolean; distance_km: number };
  grid_points?: number;
  confidence?: Confidence;
  confidence_reasons?: string[];
  attribution?: string;
  note?: string;
}

export interface Passport {
  location: { lat: number; lon: number; municipality: { lau_id: string; name: string } };
  flood: FloodBlock;
  heat: HeatBlock;
  fire: { status: string; message: string };
  actions: { flood: ActionItem[]; heat: ActionItem[]; fire: ActionItem[] };
  sources: { id: string; title: string; note: string | null }[];
  computed_at: string;
}

export interface MunicipalityHit {
  lau_id: string;
  name: string;
  pop_total: number;
  status: string;
  demo: boolean;
}

export interface BandTally {
  band: Band;
  cells: number;
  pop_total: number;
  pop_65p: number;
}
export interface Exposure {
  municipality: {
    lau_id: string;
    name: string;
    area_km2: number | null;
    cells: number;
    pop_total: number;
    pop_65p: number;
    demo: boolean;
  };
  status: 'ready' | 'computing' | 'unavailable';
  message: string | null;
  can_compute: boolean;
  reason: string | null;
  hazards: {
    flood: { status: string; message: string };
    heat: {
      status: string;
      bands: BandTally[];
      without_data: { cells: number; pop_total: number; pop_65p: number };
      coverage: {
        cells: number;
        heat_exact: number;
        heat_approximate: number;
        heat_missing: number;
        grid_points: number;
      } | null;
    };
    fire: { status: string; message: string };
  };
  kpis: {
    flood_high_pop: number | null;
    flood_high_pop_65p: number | null;
    heat_high_pop: number | null;
    heat_high_pop_65p: number | null;
  };
}

export interface CellProperties {
  grd_id: string;
  pop_total: number;
  pop_65p: number;
  heat_score: number | null;
  heat_band: Band | null;
  heat_fut_days: number | null;
  heat_base_days: number | null;
  priority: number;
  priority_class: number;
}
export interface CellCollection {
  type: 'FeatureCollection';
  features: Feature<Polygon, CellProperties>[];
  summary: {
    lau_id: string;
    cells: number;
    weights: Record<'flood' | 'heat' | 'fire', number>;
    weights_effective: Record<'flood' | 'heat' | 'fire', number>;
    breaks: number[];
    pop_total: number;
    pop_65p: number;
  };
}

export interface CoolingResult {
  lau_id: string;
  k: number;
  min_band: string;
  sites: {
    id: number;
    name: string | null;
    kind: string;
    lon: number;
    lat: number;
    newly_covered_65p: number;
  }[];
  covered_before: number;
  covered_after: number;
  demand_total: number;
  candidates: number;
  radius_m: number;
  note: string;
}
