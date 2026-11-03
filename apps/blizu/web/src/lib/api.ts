import type {
  AccessResult,
  CategoryId,
  CompareResult,
  FacilityCollection,
  GeocodeResponse,
  NeedCollection,
  OptimiseResult,
  PersonaId,
  ScoringConfigJson,
} from './types';

/** Error with the server's RFC 7807 `detail` (Croatian text) when present. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

const BASE = '/api/v1';

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${BASE}${path}`, {
      ...init,
      headers: { Accept: 'application/json', ...(init?.headers ?? {}) },
    });
  } catch {
    throw new ApiError('Nije moguće doći do poslužitelja. Provjerite internetsku vezu.', 0);
  }
  if (!response.ok) {
    let detail = '';
    try {
      const problem = (await response.json()) as { detail?: unknown; title?: string };
      detail = typeof problem.detail === 'string' ? problem.detail : (problem.title ?? '');
    } catch {
      /* not JSON */
    }
    throw new ApiError(
      detail || `Poslužitelj je vratio status ${response.status}.`,
      response.status,
    );
  }
  return (await response.json()) as T;
}

const qs = (params: Record<string, string | number>) =>
  new URLSearchParams(Object.entries(params).map(([k, v]) => [k, String(v)])).toString();

export const api = {
  geocode: (q: string, signal?: AbortSignal) =>
    request<GeocodeResponse>(`/geocode?${qs({ q })}`, { signal }),
  access: (lat: number, lon: number, persona: PersonaId, signal?: AbortSignal) =>
    request<AccessResult>(`/access?${qs({ lat, lon, persona })}`, { signal }),
  compare: (a: string, b: string, persona: PersonaId) =>
    request<CompareResult>(`/compare?${qs({ a, b, persona })}`),
  facilities: (bbox: string, category?: CategoryId) =>
    request<FacilityCollection>(`/facilities?${qs({ bbox, ...(category ? { category } : {}) })}`),
  need: (category: CategoryId, persona: PersonaId, signal?: AbortSignal) =>
    request<NeedCollection>(`/plan/need?${qs({ category, persona })}`, { signal }),
  optimise: (category: CategoryId, persona: PersonaId, k: number) =>
    request<OptimiseResult>('/plan/optimise', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ category, persona, k }),
    }),
  scoring: () => request<ScoringConfigJson>('/scoring'),
};
