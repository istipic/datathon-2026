import { EmptyState, ErrorState, LoadingSkeleton } from '@dt/ui';
import { keepPreviousData, useQuery } from '@tanstack/react-query';
import { Suspense, lazy, useMemo, useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { AccessCard } from '../components/AccessCard';
import { LazyMount } from '../components/LazyMount';
import { PersonaControl } from '../components/PersonaControl';
import type { MapFocus, MapPlace } from '../components/MapPanel';
import { Button, Icon } from '../components/ui';
import { ApiError, api } from '../lib/api';
import { isPersona } from '../lib/labels';
import { useSources } from '../lib/useSources';
import type { CategoryId, CategoryResult, PersonaId } from '../lib/types';

// The map library is large: load it in its own chunk so the card text renders first.
const MapPanel = lazy(() =>
  import('../components/MapPanel').then((m) => ({ default: m.MapPanel })),
);

function MapPlaceholder({ label }: { label: string }) {
  return (
    <div className="na-skel" style={{ position: 'absolute', inset: 0, borderRadius: 0 }}>
      <p className="dt-sr-only">{label}</p>
    </div>
  );
}

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
  const [selected, setSelected] = useState<CategoryId | null>(null);
  const [sheet, setSheet] = useState<'peek' | 'expanded'>('peek');

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
    setSelected(result.category);
    if (result.nearest)
      setFocus({ lon: result.nearest.lon, lat: result.nearest.lat, key: Date.now() });
  }

  if (!valid) {
    return (
      <div className="na-wrap">
        <EmptyState
          title="Nedostaje adresa"
          body="Odaberite adresu na početnoj stranici."
          action={
            <Link className="na-btn" to="/">
              Odaberi adresu
            </Link>
          }
        />
      </div>
    );
  }

  const backLink = (
    <Link to="/" className="na-muted inline-flex items-center gap-2 text-sm no-underline">
      <Icon name="back" size={16} /> Nova pretraga
    </Link>
  );

  if (query.isPending || sources.isPending) {
    // Same structure as the loaded screen, so nothing jumps when the result arrives.
    return (
      <div key="pending" className="na-screen">
        <div className="na-panel" data-state="expanded">
          {backLink}
          <h1 className="text-xl" style={{ margin: 0, overflowWrap: 'anywhere' }}>
            {label}
          </h1>
          <div aria-hidden="true" className="na-skel" style={{ height: 112 }} />
          <PersonaControl value={persona} onChange={setPersona} compact />
          <LoadingSkeleton lines={9} label="Računam dostupnost usluga…" />
        </div>
        <div className="na-mapcol">
          <MapPlaceholder label="Karta će se učitati…" />
        </div>
      </div>
    );
  }

  if (query.isError) {
    const outside = query.error instanceof ApiError && query.error.status === 422;
    return (
      <div className="na-wrap" style={{ maxWidth: '42rem' }}>
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
  const plannerHref = `/planiranje?lat=${lat.toFixed(6)}&lon=${lon.toFixed(6)}&persona=${persona}`;
  return (
    <div key="loaded" className="na-screen">
      <div className="na-panel" data-state={sheet} id="results-panel">
        <button
          type="button"
          className="na-sheet-handle"
          aria-expanded={sheet === 'expanded'}
          aria-controls="results-panel"
          onClick={() => setSheet((s) => (s === 'peek' ? 'expanded' : 'peek'))}
        >
          {sheet === 'peek' ? 'Prikaži sve' : 'Sažmi'}
        </button>
        <div className="blizu-noprint">{backLink}</div>
        <AccessCard
          title={label}
          result={result}
          persona={persona}
          onPersona={setPersona}
          onSelectCategory={select}
          selectedCategory={selected}
          busy={query.isFetching}
          compact
        />
        <div className="blizu-noprint flex flex-wrap gap-2">
          <Button
            variant="ghost"
            size="sm"
            onClick={() =>
              navigate(
                `/usporedi?a=${lat.toFixed(6)},${lon.toFixed(6)}&persona=${persona}&aq=${encodeURIComponent(label)}`,
              )
            }
          >
            Usporedi s drugom adresom
          </Button>
          <Button variant="ghost" size="sm" onClick={() => window.print()}>
            Ispiši karticu
          </Button>
        </div>
      </div>
      <div className="na-mapcol blizu-mapcol">
        <LazyMount placeholder={<MapPlaceholder label="Karta će se učitati…" />}>
          <Suspense fallback={<MapPlaceholder label="Učitavam kartu…" />}>
            <MapPanel
              origin={{ lon, lat, label }}
              places={places}
              focus={focus}
              plannerHref={plannerHref}
            />
          </Suspense>
        </LazyMount>
      </div>
    </div>
  );
}
