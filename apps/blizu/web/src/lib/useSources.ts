import type { SourceSummary, SourcesResponse } from '@dt/ui';
import { useQuery } from '@tanstack/react-query';

/** Data sources (`/api/v1/sources`) indexed by id; used for per-number attribution. */
export function useSources() {
  const query = useQuery({
    queryKey: ['sources'],
    queryFn: async (): Promise<SourcesResponse> => {
      const response = await fetch('/api/v1/sources', { headers: { Accept: 'application/json' } });
      if (!response.ok)
        throw new Error(`Izvori podataka nisu dostupni (status ${response.status}).`);
      return (await response.json()) as SourcesResponse;
    },
    staleTime: 10 * 60_000,
  });
  const byId = new Map<string, SourceSummary>((query.data?.sources ?? []).map((s) => [s.id, s]));
  return { ...query, byId };
}
