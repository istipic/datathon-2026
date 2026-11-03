import { EmptyState, ErrorState, LoadingSkeleton } from '@dt/ui';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Suspense, lazy, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { AccessCard } from '../components/AccessCard';
import { LazyMount } from '../components/LazyMount';
import { PersonaControl } from '../components/PersonaControl';
import type { MapFocus, MapPlace } from '../components/MapPanel';
import { ApiError, api } from '../lib/api';
import { isPersona } from '../lib/labels';
import { useSources } from '../lib/useSources';
import type { CategoryResult, PersonaId } from '../lib/types';

// The map library is large: load it in its own chunk so the card text renders first.
const MapPanel = lazy(() =>
  import('../components/MapPanel').then((m) => ({ default: m.MapPanel })),
);

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

  // Wait for the sources too: their (late) arrival would lengthen the footnote and shift the layout.
  const sources = useSources();
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

  if (query.isPending || sources.isPending) {
    // Same structure and heights as the loaded card, so the persona buttons do not jump.
    return (
      <div key="pending" className="grid gap-6 lg:grid-cols-2" style={{ minHeight: '100vh' }}>
        <div>
          <h1 className="mb-4 text-xl font-semibold text-neutral-900">{label}</h1>
          <div
            className="flex flex-wrap items-center gap-5"
            style={{ minHeight: 112 }}
            aria-hidden="true"
          >
            <div
              className="dt-skeleton__line"
              style={{ width: 112, height: 112, borderRadius: '50%', margin: 0 }}
            />
            <div style={{ width: 160 }}>
              <div className="dt-skeleton__line" style={{ width: '80%' }} />
              <div className="dt-skeleton__line" style={{ height: '2rem' }} />
            </div>
          </div>
          <div className="mt-5">
            <PersonaControl value={persona} onChange={setPersona} />
          </div>
          <div className="mt-4">
            <LoadingSkeleton lines={9} label="Računam dostupnost usluga…" />
          </div>
        </div>
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
    <div key="loaded" className="grid gap-6 lg:grid-cols-2">
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
        <LazyMount placeholder={<LoadingSkeleton lines={6} label="Karta će se učitati…" />}>
          <Suspense fallback={<LoadingSkeleton lines={6} label="Učitavam kartu…" />}>
            <MapPanel origin={{ lon, lat, label }} places={places} focus={focus} />
          </Suspense>
        </LazyMount>
      </div>
    </div>
  );
}
