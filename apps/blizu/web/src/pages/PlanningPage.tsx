import { ErrorState, LoadingSkeleton, SourceBadge } from '@dt/ui';
import { useMutation, useQuery } from '@tanstack/react-query';
import { Suspense, lazy, useEffect, useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { CountUp } from '../components/CountUp';
import { LazyMount } from '../components/LazyMount';
import { PersonaControl } from '../components/PersonaControl';
import { NO_NEED_COLOR, legendClasses } from '../lib/legend';
import { api } from '../lib/api';
import { formatInt, formatPercent, isPersona } from '../lib/labels';
import { topChangedCells } from '../lib/planner3d';
import { useSources } from '../lib/useSources';
import {
  CATEGORY_IDS,
  type CategoryId,
  type NeedCollection,
  type OptimiseResult,
  type PersonaId,
} from '../lib/types';

function Kpi({
  label,
  value,
  hint,
  testId,
}: {
  label: string;
  value: string;
  hint?: string;
  testId?: string;
}) {
  return (
    <div className="na-tile-surface na-kpi">
      <p className="na-muted text-xs">{label}</p>
      <p className="na-kpi__value dt-num" data-testid={testId}>
        {value}
      </p>
      {hint ? <p className="text-xs text-neutral-600">{hint}</p> : null}
    </div>
  );
}

// The map library is large: load it in its own chunk, after the page's text has rendered.
const PlanMap = lazy(() => import('../components/PlanMap').then((m) => ({ default: m.PlanMap })));

export function downloadGeoJson(need: NeedCollection, optimise: OptimiseResult | undefined): void {
  const sites = (optimise?.sites ?? []).map((s, i) => ({
    type: 'Feature' as const,
    geometry: { type: 'Point' as const, coordinates: [s.lon, s.lat] },
    properties: {
      kind: 'predlozena_lokacija',
      rang: i + 1,
      ulica: s.street,
      nove_osobe: s.newly_covered,
    },
  }));
  const collection = {
    type: 'FeatureCollection',
    features: [
      ...need.features.map((f) => ({ ...f, properties: { kind: 'celija', ...f.properties } })),
      ...sites,
    ],
    metadata: {
      kategorija: need.summary.category,
      persona: need.summary.persona,
      ciljna_skupina: need.summary.pop_group_label,
      izvor: 'Blizu (Eurostat Census 2021 mreža 1 km, OpenStreetMap)',
      generirano: new Date().toISOString(),
    },
  };
  const url = URL.createObjectURL(
    new Blob([JSON.stringify(collection)], { type: 'application/geo+json' }),
  );
  const a = document.createElement('a');
  a.href = url;
  a.download = `blizu_${need.summary.category}_${need.summary.persona}.geojson`;
  a.click();
  URL.revokeObjectURL(url);
}

/** Planner view: where is the unmet need, and where would 1-5 new facilities help most people. */
export function PlanningPage() {
  const [params] = useSearchParams();
  const focusLat = Number(params.get('lat'));
  const focusLon = Number(params.get('lon'));
  const focus = useMemo(
    () =>
      params.has('lat') &&
      params.has('lon') &&
      Number.isFinite(focusLat) &&
      Number.isFinite(focusLon)
        ? { lat: focusLat, lon: focusLon }
        : null,
    [params, focusLat, focusLon],
  );
  const [category, setCategory] = useState<CategoryId>('vrtic');
  const [persona, setPersona] = useState<PersonaId>(
    isPersona(params.get('persona')) ? (params.get('persona') as PersonaId) : 'roditelj',
  );
  const [k, setK] = useState(3);
  const { byId } = useSources();

  const scoring = useQuery({
    queryKey: ['scoring'],
    queryFn: () => api.scoring(),
    staleTime: Infinity,
  });
  const need = useQuery({
    queryKey: ['need', category, persona],
    queryFn: ({ signal }) => api.need(category, persona, signal),
  });
  const optimise = useMutation({ mutationFn: () => api.optimise(category, persona, k) });
  const reset = optimise.reset;
  useEffect(() => {
    reset(); // a new category/persona invalidates earlier suggestions
  }, [category, persona, reset]);

  const summary = need.data?.summary;
  const classes = useMemo(() => {
    if (!need.data) return [];
    const max = Math.max(0, ...need.data.features.map((f) => f.properties.unmet));
    return legendClasses(need.data.summary.breaks, Math.ceil(max));
  }, [need.data]);
  const gridSource = byId.get('eurostat-census-grid-2021');
  const sites = optimise.data?.sites ?? [];

  return (
    <div className="na-screen na-screen--plan">
      <div className="na-panel">
        <h1 className="text-2xl" style={{ margin: 0 }}>
          Planiranje usluga
        </h1>
        <p className="mb-4 text-neutral-700">
          Gdje su stanovnici najdalje od usluge i gdje bi nova ustanova koristila najviše ljudi.
        </p>

        <div className="mb-4">
          <label htmlFor="category" className="na-overline mb-1 block">
            Kategorija usluge
          </label>
          <select
            id="category"
            value={category}
            onChange={(e) => setCategory(e.target.value as CategoryId)}
            className="na-select w-full"
          >
            {CATEGORY_IDS.map((id) => (
              <option key={id} value={id}>
                {scoring.data?.categories[id]?.label ?? id}
              </option>
            ))}
          </select>
        </div>
        <div className="mb-5">
          <PersonaControl
            value={persona}
            onChange={setPersona}
            label="Persona (brzina hoda i graf)"
          />
        </div>

        <div aria-live="polite">
          {need.isPending ? <LoadingSkeleton lines={4} label="Učitavam kartu potrebe…" /> : null}
          {need.isError ? (
            <ErrorState message={need.error.message} onRetry={() => void need.refetch()} />
          ) : null}
          {summary ? (
            <>
              <div className="grid gap-3 sm:grid-cols-2">
                <Kpi
                  label={`Ciljna skupina: ${summary.pop_group_label}`}
                  value={formatInt(summary.pop_group_total)}
                  testId="kpi-total"
                />
                <Kpi
                  label={`Unutar ${summary.good_min} min hoda`}
                  value={formatPercent(summary.share_within_g)}
                  hint="udio skupine u ćelijama čiji je prosjek unutar granice"
                  testId="kpi-share"
                />
              </div>
              {!summary.has_age_groups ? (
                <p className="mt-2 text-sm text-warning-fg" role="status">
                  Dobne skupine nisu dostupne u mreži stanovništva, pa se koristi ukupno
                  stanovništvo.
                </p>
              ) : null}
            </>
          ) : null}
        </div>

        {summary ? (
          <section className="mt-5" aria-labelledby="legend-title">
            <h2 id="legend-title" className="mb-2 text-base font-semibold">
              Nezadovoljena potreba (osoba po ćeliji 1 km²)
            </h2>
            <ul className="space-y-1 text-sm">
              <li>
                <span
                  className="blizu-legend-swatch"
                  style={{ background: NO_NEED_COLOR }}
                  aria-hidden="true"
                />{' '}
                bez nezadovoljene potrebe
              </li>
              {classes.map((c) => (
                <li key={c.color} data-testid="legend-class">
                  <span
                    className="blizu-legend-swatch"
                    style={{ background: c.color }}
                    aria-hidden="true"
                  />{' '}
                  <span className="dt-num">
                    {c.from === 0 ? '> 0' : `> ${formatInt(c.from)}`}
                    {c.to !== null ? ` do ${formatInt(c.to)}` : ''}
                  </span>
                </li>
              ))}
            </ul>
          </section>
        ) : null}

        <section className="na-tile-surface mt-2 p-4" aria-labelledby="opt-title">
          <h2 id="opt-title" className="mb-2 text-lg font-semibold">
            Predloži lokacije
          </h2>
          <label htmlFor="k" className="block text-sm font-medium text-neutral-700">
            Broj novih ustanova: <span className="dt-num">{k}</span>
          </label>
          <input
            id="k"
            type="range"
            min={1}
            max={5}
            step={1}
            value={k}
            onChange={(e) => setK(Number(e.target.value))}
            aria-valuetext={`${k} nove ustanove`}
            className="mb-3 w-full"
          />
          <button
            type="button"
            className="na-btn"
            disabled={optimise.isPending || !summary}
            onClick={() => optimise.mutate()}
          >
            {optimise.isPending ? 'Računam…' : 'Predloži lokacije'}
          </button>

          <div aria-live="polite" className="mt-3">
            {optimise.isError ? (
              <ErrorState message={optimise.error.message} onRetry={() => optimise.mutate()} />
            ) : null}
            {optimise.data ? (
              <div data-testid="optimise-result">
                <p
                  className="na-counter"
                  data-testid="optimise-headline"
                  style={{ margin: '0 0 0.75rem' }}
                >
                  Nove lokacije donose doseg za{' '}
                  <CountUp
                    value={optimise.data.total_newly_covered}
                    prefix="+"
                    suffix=" osoba"
                    testId="headline-count"
                  />
                </p>
                <div className="grid gap-3 sm:grid-cols-2">
                  <Kpi
                    label="Prije (unutar granice)"
                    value={formatPercent(optimise.data.share_before)}
                    testId="kpi-before"
                  />
                  <Kpi
                    label="Poslije"
                    value={formatPercent(optimise.data.share_after)}
                    hint={`+${formatInt(optimise.data.total_newly_covered)} osoba`}
                    testId="kpi-after"
                  />
                </div>
                {optimise.data.sites.length === 0 ? (
                  <p className="mt-2 text-sm">Nema lokacije koja bi dodatno pokrila potrebu.</p>
                ) : (
                  <ol className="mt-3 list-decimal pl-5 text-sm">
                    {optimise.data.sites.map((s, i) => (
                      <li key={i}>
                        {s.street ?? 'ulica nepoznata'} –{' '}
                        <span className="dt-num">+{formatInt(s.newly_covered)}</span> osoba
                      </li>
                    ))}
                  </ol>
                )}
                {optimise.data.sites.length > 0 ? (
                  <div className="dt-table-wrap mt-4" data-testid="optimise-table">
                    <table className="na-table">
                      <caption className="dt-sr-only">
                        Isti brojevi kao na karti: predložene lokacije i ćelije s najvećom promjenom
                      </caption>
                      <thead>
                        <tr>
                          <th scope="col">Lokacija</th>
                          <th scope="col">Nove osobe u dosegu</th>
                        </tr>
                      </thead>
                      <tbody>
                        {optimise.data.sites.map((s, i) => (
                          <tr key={`s${i}`}>
                            <th scope="row">{s.street ?? 'ulica nepoznata'}</th>
                            <td className="dt-num">+{formatInt(s.newly_covered)}</td>
                          </tr>
                        ))}
                      </tbody>
                      <thead>
                        <tr>
                          <th scope="col">Ćelija 1 km² (najveći pad)</th>
                          <th scope="col">Osoba izvan dosega prije → poslije</th>
                        </tr>
                      </thead>
                      <tbody>
                        {topChangedCells(optimise.data.cells).map((c) => (
                          <tr key={c.cell_id}>
                            <th scope="row" className="dt-num">
                              {c.cell_id.replace(/^CRS3035RES1000m/, '')}
                            </th>
                            <td className="dt-num">
                              {formatInt(c.unmet_before)} → {formatInt(c.unmet_after)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        </section>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            type="button"
            className="na-btn na-btn--ghost na-btn--sm"
            disabled={!need.data}
            onClick={() => need.data && downloadGeoJson(need.data, optimise.data)}
          >
            Preuzmi GeoJSON
          </button>
        </div>
        <p className="mt-4 text-xs text-neutral-600">
          Granice po ćelijama od 1 km² ne prikazuju stvarni raspored stanovnika unutar ćelije; vidi{' '}
          <a href="/metodologija" className="underline">
            metodologiju
          </a>
          .
        </p>
        {gridSource ? (
          <p className="mt-2 text-sm">
            <SourceBadge
              publisher={gridSource.publisher}
              title={gridSource.title}
              url={gridSource.url}
              retrievedAt={gridSource.retrieved_at}
            />
          </p>
        ) : null}
      </div>

      <div className="na-mapcol">
        <LazyMount placeholder={<LoadingSkeleton lines={6} label="Karta će se učitati…" />}>
          <Suspense fallback={<LoadingSkeleton lines={6} label="Učitavam kartu…" />}>
            <PlanMap need={need.data} optimise={optimise.data} sites={sites} focus={focus} />
          </Suspense>
        </LazyMount>
      </div>
    </div>
  );
}
