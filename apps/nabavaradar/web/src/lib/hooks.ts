import { useQuery } from '@tanstack/react-query';
import type { CountyGeo } from '../components/CountyMap';
import { api } from './api';

/** County polygons (static file, Eurostat GISCO NUTS3 2021). */
export function useCountiesGeo() {
  return useQuery({
    queryKey: ['counties-geo'],
    staleTime: Infinity,
    queryFn: async (): Promise<CountyGeo> => {
      const res = await fetch('/data/counties-hr.geojson');
      if (!res.ok) throw new Error('Granice županija nisu dostupne.');
      return (await res.json()) as CountyGeo;
    },
  });
}

export const useCounties = () =>
  useQuery({
    queryKey: ['counties'],
    staleTime: Infinity,
    queryFn: ({ signal }) => api.counties(signal),
  });

export const useStatus = () =>
  useQuery({
    queryKey: ['status'],
    staleTime: 60_000,
    queryFn: ({ signal }) => api.status(signal),
  });
