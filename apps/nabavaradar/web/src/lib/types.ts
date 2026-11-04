export interface CountyRef {
  code: number;
  name: string;
  nuts3: string;
}

export interface CompanyActivity {
  code: string;
  version: string;
  label: string | null;
  is_main: boolean;
}

export interface CompanyProfile {
  oib: string;
  mbs: number;
  name: string;
  status: number;
  county: CountyRef | null;
  activities: CompanyActivity[];
  data_as_of: string | null;
  snapshot_id: number;
  retrieved_at: string | null;
  source: { id: string; environment: 'test' | 'production' };
}

export interface Queued {
  status: 'queued';
  oib: string;
  retry_after: number;
  detail: string;
}

export interface CompetitionInfo {
  median_submissions: number | null;
  single_bid_share: number | null;
  n: number;
  flag: boolean;
  scope: string | null;
}

export interface GroupedNotice {
  pub_no: string;
  pub_date: string;
  title: string | null;
  fit: number;
  deadline: string | null;
  url_html: string | null;
}

export interface MatchItem {
  pub_no: string;
  title: string | null;
  buyer: string | null;
  nuts3: string | null;
  county: string | null;
  deadline: string | null;
  deadline_kind: 'tender' | 'request' | null;
  days_left: number | null;
  value_eur: number | null;
  fit: number;
  similarity: number;
  components: { S: number; C: number; G: number; T: number };
  best_activity: { label: string; code: string | null; version: string | null };
  procedure_id?: string | null;
  notice_type?: string;
  signals?: { main_activity: boolean; cpv_group_match: boolean; disliked_group: boolean };
  group?: { size: number; others: GroupedNotice[] };
  cpv_group?: string | null;
  cpv_main: string | null;
  cpv_division: string | null;
  cpv_division_label: string | null;
  division_rank: number | null;
  competition: CompetitionInfo;
  url_html: string | null;
  pub_date: string;
}

export interface NoticeAward {
  lot_id: string;
  lot_status: string | null;
  winner: string | null;
  winner_oib: string | null;
  received_submissions: number | null;
}

export interface CompetitionDetail extends CompetitionInfo {
  cpv_group: string | null;
  window_start: string | null;
  window_end: string | null;
}

export interface NoticeDetail {
  pub_no: string;
  type: 'competition' | 'result';
  notice_type: string;
  pub_date: string;
  title: string | null;
  description: string | null;
  buyer: string | null;
  buyer_nuts: string | null;
  place_nuts: string | null;
  cpv_codes: string[];
  cpv_main: string | null;
  deadline: string | null;
  deadline_kind: 'tender' | 'request' | null;
  value_eur: number | null;
  currency: string | null;
  n_lots: number | null;
  url_html: string | null;
  url_pdf: string | null;
  retrieved_at: string | null;
  competition: CompetitionDetail;
  awards: NoticeAward[];
}

export interface CpvSuggestion {
  code: string;
  label: string | null;
  similarity: number | null;
  division: string;
  group: string | null;
}

export interface CountySuppliers {
  county_code: number;
  county: string;
  nuts3: string;
  nuts2: string;
  count: number;
}

export interface AdviceItem {
  rule: string;
  text: string;
  source_url: string;
  source_label: string;
}

export interface SoundingResult {
  cpv_suggestions: CpvSuggestion[];
  division: { code: string; label: string | null };
  cpv_group: string | null;
  suppliers: {
    tau: number;
    tau_calibrated: boolean;
    total: number;
    in_county: number | null;
    in_region: number | null;
    companies_in_register: number;
  };
  suppliers_by_county: CountySuppliers[];
  competition: CompetitionDetail & { national: CompetitionDetail };
  advice: AdviceItem[];
  data: Record<string, string | null>;
  generated_at: string;
}

export interface CpvHit {
  code: string;
  check_digit: string | null;
  label: string;
  division: string;
  group: string;
}

export interface RecallPair {
  'recall@10': number | null;
  'recall@20': number | null;
}

export interface ValidationResult {
  computed_at: string;
  mode: 'linked' | 'result_fallback';
  mode_note: string;
  n: number;
  n_scored: number;
  n_without_activities: number;
  fit: RecallPair;
  fts_baseline: RecallPair;
  random_baseline: RecallPair;
  fit_scored_only: RecallPair;
  fts_baseline_scored_only: RecallPair;
  window: { first_month: string | null; last_month: string | null };
  months: string[];
  tau: { tau: number | null; f1?: number; precision?: number; recall?: number; winners?: number };
  stored_at: string;
}

export interface StatusInfo {
  environment: 'test' | 'production';
  companies: number;
  [key: string]: string | number | null;
}

export interface CountyOption {
  code: number;
  name: string;
  nuts3: string;
  nuts2: string;
}

export interface Highlights {
  open_notices: number;
  total_value_eur: number;
  retrieved_at: string | null;
  top_buyers: { name: string; open_notices: number }[];
  top_cpv_areas: { division: string; label: string | null; open_notices: number }[];
}

export type Frequency = 'daily' | 'weekly';

export interface AlertPrefs {
  min_fit: number;
  min_value_eur: number | null;
  counties: number[];
  cpv_divisions: string[];
  frequency: Frequency;
}

export interface AlertSettings extends AlertPrefs {
  email: string;
  oib: string | null;
  query: string | null;
  paused: boolean;
  confirmed: boolean;
  excluded: number;
}

export interface AlertPreview {
  count: number;
  top: { pub_no: string; title: string | null; fit: number }[];
}
