import { ErrorState, LoadingSkeleton, SourceBadge } from '@dt/ui';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { PersonaControl } from '../components/PersonaControl';
import { PlanMap, NO_NEED_COLOR, legendClasses } from '../components/PlanMap';
import { api } from '../lib/api';
import { formatInt, formatPercent } from '../lib/labels';
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
    <div className="rounded-xl border border-neutral-300 bg-white p-4">
      <p className="text-sm text-neutral-600">{label}</p>
      <p className="dt-num text-2xl font-semibold text-neutral-900" data-testid={testId}>
        {value}
      </p>
      {hint ? <p className="text-xs text-neutral-600">{hint}</p> : null}
    </div>
  );
}

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
  const [category, setCategory] = useState<CategoryId>('vrtic');
  const [persona, setPersona] = useState<PersonaId>('roditelj');
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
    <div className="grid gap-6 lg:grid-cols-[minmax(0,26rem)_1fr]">
      <div>
        <h1 className="mb-2 text-2xl font-semibold text-neutral-900">Planiranje usluga</h1>
        <p className="mb-4 text-neutral-700">
          Gdje su stanovnici najdalje od usluge i gdje bi nova ustanova koristila najviše ljudi.
        </p>

        <div className="mb-4">
          <label htmlFor="category" className="mb-1 block text-sm font-medium text-neutral-700">
            Kategorija usluge
          </label>
          <select
            id="category"
            value={category}
            onChange={(e) => setCategory(e.target.value as CategoryId)}
            className="min-h-[44px] w-full rounded-lg border border-neutral-400 bg-white px-3 text-base"
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

        <section
          className="mt-6 rounded-xl border border-neutral-300 bg-white p-4"
          aria-labelledby="opt-title"
        >
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
            className="dt-button"
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
              </div>
            ) : null}
          </div>
        </section>

        <div className="mt-4 flex flex-wrap items-center gap-3">
          <button
            type="button"
            className="min-h-[44px] rounded-md border border-neutral-400 bg-white px-4 font-semibold"
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

      <div className="min-h-[28rem] lg:sticky lg:top-4 lg:h-[calc(100vh-6rem)]">
        <PlanMap need={need.data} sites={sites} />
      </div>
    </div>
  );
}
