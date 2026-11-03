import { useQuery } from '@tanstack/react-query';
import { formatDateTime, toIso } from '../lib/format';
import { EmptyState } from './EmptyState';
import { ErrorState } from './ErrorState';
import { FreshnessChip } from './FreshnessChip';
import { LoadingSkeleton } from './LoadingSkeleton';

/** One item of `GET /api/v1/sources` (see opendata_core.provenance.sources_summary). */
export interface SourceSummary {
  id: string;
  title: string;
  publisher: string;
  url: string;
  license_name: string | null;
  license_url: string | null;
  access_method: 'api' | 'download' | 'wms' | 'derived';
  tier: 'official' | 'eu_official' | 'community' | 'derived';
  notes: string | null;
  last_run: {
    id: number;
    rows: number | null;
    sha256: string | null;
    retrieved_url: string | null;
    source_last_modified: string | null;
  } | null;
  retrieved_at: string | null;
  freshness_days: number | null;
}

export interface SourcesResponse {
  sources: SourceSummary[];
  generated_at: string;
}

const TIER_LABEL: Record<SourceSummary['tier'], string> = {
  official: 'Službeni',
  eu_official: 'Službeni (EU)',
  community: 'Zajednica',
  derived: 'Izvedeni',
};
const ACCESS_LABEL: Record<SourceSummary['access_method'], string> = {
  api: 'API',
  download: 'Preuzimanje',
  wms: 'WMS',
  derived: 'Izvedeno',
};

/** Error carrying the server's RFC 7807 `detail`, when present. */
export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

export async function fetchSources(
  endpoint: string,
  signal?: AbortSignal,
): Promise<SourcesResponse> {
  const response = await fetch(endpoint, { headers: { Accept: 'application/json' }, signal });
  if (!response.ok) {
    let detail = '';
    try {
      const problem = (await response.json()) as { detail?: string; title?: string };
      detail = problem.detail ?? problem.title ?? '';
    } catch {
      /* body is not JSON */
    }
    throw new ApiError(
      detail || `Poslužitelj je vratio status ${response.status}.`,
      response.status,
    );
  }
  return (await response.json()) as SourcesResponse;
}

export interface DataSourcesPageProps {
  /** Defaults to "/api/v1/sources". Requires a QueryClientProvider above. */
  endpoint?: string;
  title?: string;
}

/** "Izvori podataka": every data source with publisher, licence, retrieval time and freshness. */
export function DataSourcesPage({
  endpoint = '/api/v1/sources',
  title = 'Izvori podataka',
}: DataSourcesPageProps) {
  const query = useQuery({
    queryKey: ['dt-sources', endpoint],
    queryFn: ({ signal }) => fetchSources(endpoint, signal),
  });

  let content;
  if (query.isPending) {
    content = <LoadingSkeleton lines={4} label="Učitavanje izvora podataka…" />;
  } else if (query.isError) {
    content = (
      <ErrorState
        message={query.error instanceof Error ? query.error.message : 'Nepoznata pogreška.'}
        onRetry={() => void query.refetch()}
      />
    );
  } else if (query.data.sources.length === 0) {
    content = (
      <EmptyState
        title="Još nema učitanih izvora"
        body="Nijedan izvor podataka još nije registriran u ovoj bazi."
      />
    );
  } else {
    content = (
      <div className="dt-table-wrap">
        <table className="dt-table">
          <caption>Popis izvora podataka i vrijeme njihova dohvaćanja</caption>
          <thead>
            <tr>
              <th scope="col">Izvor</th>
              <th scope="col">Izdavač</th>
              <th scope="col">Licencija</th>
              <th scope="col">Pristup</th>
              <th scope="col">Razina</th>
              <th scope="col">Dohvaćeno</th>
              <th scope="col">Starost podataka</th>
              <th scope="col">Redaka</th>
            </tr>
          </thead>
          <tbody>
            {query.data.sources.map((source) => (
              <tr key={source.id}>
                <th scope="row">
                  <a
                    className="dt-link"
                    href={source.url}
                    target="_blank"
                    rel="noopener noreferrer"
                  >
                    {source.title}
                  </a>
                  {source.notes ? <div>{source.notes}</div> : null}
                </th>
                <td>{source.publisher}</td>
                <td>
                  {source.license_url ? (
                    <a
                      className="dt-link"
                      href={source.license_url}
                      target="_blank"
                      rel="noopener noreferrer"
                    >
                      {source.license_name ?? source.license_url}
                    </a>
                  ) : (
                    (source.license_name ?? 'Nije navedena')
                  )}
                </td>
                <td>{ACCESS_LABEL[source.access_method]}</td>
                <td>{TIER_LABEL[source.tier]}</td>
                <td>
                  {source.retrieved_at ? (
                    <time dateTime={toIso(source.retrieved_at)}>
                      {formatDateTime(source.retrieved_at)}
                    </time>
                  ) : (
                    'Još nije dohvaćeno'
                  )}
                </td>
                <td>
                  <FreshnessChip days={source.freshness_days} />
                </td>
                <td className="dt-num">{source.last_run?.rows ?? '–'}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    );
  }

  return (
    <section aria-labelledby="dt-sources-title">
      <h1 id="dt-sources-title">{title}</h1>
      <div aria-live="polite">{content}</div>
    </section>
  );
}
