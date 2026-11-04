import type {
  AlertPreview,
  AlertPrefs,
  AlertSettings,
  CompanyProfile,
  CountyOption,
  CpvHit,
  Highlights,
  MatchItem,
  NoticeDetail,
  Queued,
  SoundingResult,
  StatusInfo,
  ValidationResult,
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

async function request<T>(path: string, init?: RequestInit): Promise<{ status: number; body: T }> {
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
  return { status: response.status, body: (await response.json()) as T };
}

const qs = (params: Record<string, string | number | undefined | null>) =>
  new URLSearchParams(
    Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== null && v !== '')
      .map(([k, v]) => [k, String(v)]),
  ).toString();

export interface MatchParams {
  oib?: string;
  q?: string;
  county?: number;
  counties?: string;
  cpv?: string;
  deadline_min_days?: number;
  limit?: number;
  value_min?: number;
  value_max?: number;
  hide?: string;
  dislike?: string;
  group_lots?: boolean;
}

export const api = {
  /** 200 -> profile; 202 -> the register lookup is queued (retry after `retry_after` seconds). */
  company: async (oib: string, signal?: AbortSignal): Promise<CompanyProfile | Queued> => {
    const { status, body } = await request<CompanyProfile | Queued>(`/company/${oib}`, { signal });
    return status === 202 ? { ...(body as Queued), status: 'queued' } : (body as CompanyProfile);
  },
  match: async (params: MatchParams, signal?: AbortSignal) =>
    (
      await request<MatchItem[]>(
        `/match?${qs({ ...params, group_lots: params.group_lots === false ? 'false' : undefined })}`,
        { signal },
      )
    ).body,
  notice: async (pubNo: string, signal?: AbortSignal) =>
    (await request<NoticeDetail>(`/notices/${encodeURIComponent(pubNo)}`, { signal })).body,
  sounding: async (body: { text?: string; cpv?: string; county?: number }, signal?: AbortSignal) =>
    (
      await request<SoundingResult>('/sounding', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
        signal,
      })
    ).body,
  validation: async (signal?: AbortSignal) =>
    (await request<ValidationResult>('/validation', { signal })).body,
  counties: async (signal?: AbortSignal) =>
    (await request<CountyOption[]>('/counties', { signal })).body,
  cpvSearch: async (q: string, signal?: AbortSignal) =>
    (await request<CpvHit[]>(`/cpv?${qs({ q })}`, { signal })).body,
  status: async (signal?: AbortSignal) => (await request<StatusInfo>('/status', { signal })).body,
  highlights: async (signal?: AbortSignal) =>
    (await request<Highlights>('/highlights', { signal })).body,
  consentText: async (frequency: string, minFit: number, signal?: AbortSignal) =>
    (
      await request<{ text: string }>(
        `/subscriptions/consent?${qs({ frequency, min_fit: minFit })}`,
        { signal },
      )
    ).body.text,
  alertPreview: async (
    p: { oib?: string; q?: string } & Pick<AlertPrefs, 'min_fit'> & {
        min_value_eur?: number | null;
        counties?: number[];
        cpv?: string[];
      },
    signal?: AbortSignal,
  ) =>
    (
      await request<AlertPreview>(
        `/subscriptions/preview?${qs({
          oib: p.oib,
          q: p.q,
          min_fit: p.min_fit,
          min_value_eur: p.min_value_eur,
          counties: p.counties?.join(','),
          cpv: p.cpv?.join(','),
        })}`,
        { signal },
      )
    ).body,
  subscribe: async (
    body: {
      email: string;
      oib?: string;
      query?: string;
      consent: boolean;
    } & Partial<AlertPrefs>,
  ) =>
    (
      await request<{ detail: string }>('/subscriptions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
    ).body,
  alertSettings: async (token: string, signal?: AbortSignal) =>
    (await request<AlertSettings>(`/subscriptions/settings?${qs({ token })}`, { signal })).body,
  updateAlertSettings: async (
    token: string,
    body: Partial<AlertPrefs> & { paused?: boolean; clear_min_value?: boolean },
  ) =>
    (
      await request<AlertSettings>(`/subscriptions/settings?${qs({ token })}`, {
        method: 'PUT',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body),
      })
    ).body,
  excludeNotice: async (token: string, pubNo: string) =>
    (
      await request<{ detail: string }>(`/subscriptions/exclude?${qs({ token })}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ pub_no: pubNo }),
      })
    ).body,
  confirmSubscription: async (token: string) =>
    (await request<{ detail: string }>(`/subscriptions/confirm?${qs({ token })}`)).body,
  unsubscribe: async (token: string) =>
    (
      await request<{ detail: string }>(`/subscriptions?${qs({ token })}`, {
        method: 'DELETE',
      })
    ).body,
};
