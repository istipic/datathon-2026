import { useQuery } from '@tanstack/react-query';
import { ApiError, api } from './api';
import type { PersonaId } from './types';

/** Walking-time isochrone of an address (15 minutes); shared by the page and the map scenes via the cache. */
export function useIsochrone(lat: number, lon: number, persona: PersonaId, enabled = true) {
  return useQuery({
    queryKey: ['isochrone', lat, lon, persona],
    queryFn: ({ signal }) => api.isochrone(lat, lon, persona, 15, signal),
    enabled,
    staleTime: 10 * 60_000,
    retry: (n, e) => !(e instanceof ApiError && e.status < 500) && n < 1,
  });
}
