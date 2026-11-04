import type {
  CellCollection,
  CoolingResult,
  Exposure,
  GeocodeResponse,
  MunicipalityHit,
  Passport,
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
  passport: (lat: number, lon: number, signal?: AbortSignal) =>
    request<Passport>(`/passport?${qs({ lat, lon })}`, { signal }),
  municipalities: (q: string, signal?: AbortSignal) =>
    request<{ results: MunicipalityHit[] }>(`/municipalities?${qs({ q })}`, { signal }),
  exposure: (lau: string, signal?: AbortSignal) =>
    request<Exposure>(`/municipalities/${encodeURIComponent(lau)}/exposure`, { signal }),
  compute: (lau: string) =>
    request<{ status: string; started: boolean }>(
      `/municipalities/${encodeURIComponent(lau)}/compute`,
      { method: 'POST' },
    ),
  cells: (lau: string, w: { flood: number; heat: number; fire: number }, signal?: AbortSignal) =>
    request<CellCollection>(
      `/cells?${qs({ lau, w_flood: w.flood, w_heat: w.heat, w_fire: w.fire })}`,
      { signal },
    ),
  cooling: (lau_id: string, k: number, min_band: string) =>
    request<CoolingResult>('/cooling-centres', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ lau_id, k, min_band }),
    }),
};
