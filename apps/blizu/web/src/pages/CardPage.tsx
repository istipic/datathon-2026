import { EmptyState, ErrorState, LoadingSkeleton } from '@dt/ui';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { AccessCard } from '../components/AccessCard';
import { MapPanel, type MapFocus, type MapPlace } from '../components/MapPanel';
import { ApiError, api } from '../lib/api';
import { isPersona } from '../lib/labels';
import type { CategoryResult, PersonaId } from '../lib/types';

export function CardPage() {
  const [params, setParams] = useSearchParams();
  const navigate = useNavigate();
  const lat = Number(params.get('lat'));
  const lon = Number(params.get('lon'));
  const personaParam = params.get('persona');
  const persona: PersonaId = isPersona(personaParam) ? personaParam : 'opce';
  const label = params.get('q') ?? `${lat.toFixed(4)}, ${lon.toFixed(4)}`;
  const valid =
    Number.isFinite(lat) && Number.isFinite(lon) && params.has('lat') && params.has('lon');
  const [focus, setFocus] = useState<MapFocus | null>(null);

  const query = useQuery({
    queryKey: ['access', lat, lon, persona],
    queryFn: ({ signal }) => api.access(lat, lon, persona, signal),
    enabled: valid,
    placeholderData: keepPreviousData,
    retry: (count, error) => !(error instanceof ApiError && error.status < 500) && count < 1,
  });

  const places: MapPlace[] = useMemo(
    () =>
      (query.data?.categories ?? [])
        .filter((c) => c.nearest)
        .map((c) => ({
          category: c.category,
          name: c.nearest!.name,
          address: c.nearest!.address,
          lon: c.nearest!.lon,
          lat: c.nearest!.lat,
        })),
    [query.data],
  );

  function setPersona(next: PersonaId) {
    const copy = new URLSearchParams(params);
    copy.set('persona', next);
    setParams(copy, { replace: true });
  }

  function select(result: CategoryResult) {
    if (result.nearest)
      setFocus({ lon: result.nearest.lon, lat: result.nearest.lat, key: Date.now() });
  }

  if (!valid) {
    return (
      <EmptyState
        title="Nedostaje adresa"
        body="Odaberite adresu na početnoj stranici."
        action={
          <Link className="dt-button" to="/">
            Odaberi adresu
          </Link>
        }
      />
    );
  }

  if (query.isPending) {
    return (
      <div className="grid gap-6 lg:grid-cols-2">
        <LoadingSkeleton lines={8} label="Računam dostupnost usluga…" />
      </div>
    );
  }

  if (query.isError) {
    const outside = query.error instanceof ApiError && query.error.status === 422;
    return (
      <div className="mx-auto max-w-2xl">
        <ErrorState
          message={query.error.message}
          onRetry={outside ? undefined : () => void query.refetch()}
        />
        <p className="mt-4">
          <Link className="underline" to="/">
            Probajte drugu adresu
          </Link>
        </p>
      </div>
    );
  }

  const result = query.data;
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <div>
        <AccessCard
          title={label}
          result={result}
          persona={persona}
          onPersona={setPersona}
          onSelectCategory={select}
          busy={query.isFetching}
        />
        <div className="blizu-noprint mt-6 flex flex-wrap gap-3">
          <button
            type="button"
            className="dt-button"
            onClick={() =>
              navigate(
                `/usporedi?a=${lat.toFixed(6)},${lon.toFixed(6)}&persona=${persona}&aq=${encodeURIComponent(label)}`,
              )
            }
          >
            Usporedi s drugom adresom
          </button>
          <button
            type="button"
            className="min-h-[40px] rounded-md border border-neutral-400 bg-white px-4 py-2 font-semibold"
            onClick={() => window.print()}
          >
            Ispiši karticu
          </button>
        </div>
      </div>
      <div className="blizu-mapcol lg:sticky lg:top-4 lg:h-[calc(100vh-6rem)]">
        <MapPanel origin={{ lon, lat, label }} places={places} focus={focus} />
      </div>
    </div>
  );
}
