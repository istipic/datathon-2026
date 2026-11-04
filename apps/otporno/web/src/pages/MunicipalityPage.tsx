import { EmptyState, ErrorState, LoadingSkeleton } from '@dt/ui';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { CoolingPanel } from '../components/CoolingPanel';
import { PriorityMap } from '../components/PriorityMap';
import { WeightSliders, type Weights } from '../components/WeightSliders';
import { api } from '../lib/api';
import { BANDS, BAND_LABEL, HEAT_FILL } from '../lib/bands';
import { fmtInt } from '../lib/format';
import type { CellProperties, CoolingResult, Exposure } from '../lib/types';

const DEFAULT_W: Weights = { flood: 0.5, heat: 0.35, fire: 0.15 };
const POLL_MS = 5000;

function Kpi({
  label,
  value,
  note,
  tone,
}: {
  label: string;
  value: string;
  note?: string;
  tone?: 'heat' | 'flood';
}) {
  const colour =
    tone === 'heat'
      ? 'rgb(var(--heat-700))'
      : tone === 'flood'
        ? 'rgb(var(--flood-700))'
        : undefined;
  return (
    <div className="ot-card p-4">
      <p className="text-sm font-bold text-neutral-700">{label}</p>
      <p className="ot-display ot-num mt-1 text-2xl" style={{ color: colour }}>
        {value}
      </p>
      {note ? <p className="mt-1 text-sm text-neutral-700">{note}</p> : null}
    </div>
  );
}

function BandTable({ ex }: { ex: Exposure }) {
  const heat = ex.hazards.heat;
  const max = Math.max(1, ...heat.bands.map((b) => b.pop_total));
  return (
    <table className="w-full border-collapse text-left">
      <caption className="mb-2 text-left font-bold">Stanovnici po razini toplinskog rizika</caption>
      <thead>
        <tr className="border-b-2 border-neutral-700 text-sm">
          <th scope="col" className="py-2 pr-3">
            Razina
          </th>
          <th scope="col" className="py-2 pr-3 text-right">
            Ćelija
          </th>
          <th scope="col" className="py-2 pr-3 text-right">
            Stanovnika
          </th>
          <th scope="col" className="py-2 pr-3 text-right">
            od toga 65+
          </th>
          <th scope="col" className="py-2">
            <span className="dt-sr-only">Udio</span>
          </th>
        </tr>
      </thead>
      <tbody>
        {BANDS.map((b) => {
          const row = heat.bands.find((x) => x.band === b);
          return (
            <tr key={b} className="border-b border-neutral-300">
              <th scope="row" className="py-2 pr-3 font-bold">
                {BAND_LABEL[b]}
              </th>
              <td className="ot-num py-2 pr-3 text-right">{fmtInt(row?.cells ?? 0)}</td>
              <td className="ot-num py-2 pr-3 text-right">{fmtInt(row?.pop_total ?? 0)}</td>
              <td className="ot-num py-2 pr-3 text-right">{fmtInt(row?.pop_65p ?? 0)}</td>
              <td className="w-1/4 py-2" aria-hidden="true">
                <div className="h-3 rounded bg-neutral-200">
                  <div
                    className="h-3 rounded"
                    style={{
                      width: `${((row?.pop_total ?? 0) / max) * 100}%`,
                      background: HEAT_FILL[b],
                    }}
                  />
                </div>
              </td>
            </tr>
          );
        })}
        {heat.without_data.cells > 0 ? (
          <tr className="text-neutral-700">
            <th scope="row" className="py-2 pr-3 font-normal">
              Bez klimatskih podataka
            </th>
            <td className="ot-num py-2 pr-3 text-right">{fmtInt(heat.without_data.cells)}</td>
            <td className="ot-num py-2 pr-3 text-right">{fmtInt(heat.without_data.pop_total)}</td>
            <td className="ot-num py-2 pr-3 text-right">{fmtInt(heat.without_data.pop_65p)}</td>
            <td />
          </tr>
        ) : null}
      </tbody>
    </table>
  );
}

export function MunicipalityPage() {
  const { lau = '' } = useParams();
  const qc = useQueryClient();
  const [weights, setWeights] = useState<Weights>(DEFAULT_W);
  const [debounced, setDebounced] = useState<Weights>(DEFAULT_W);
  const [cooling, setCooling] = useState<CoolingResult | null>(null);
  const [picked, setPicked] = useState<CellProperties | null>(null);

  useEffect(() => {
    const t = setTimeout(() => setDebounced(weights), 250);
    return () => clearTimeout(t);
  }, [weights]);

  const exposure = useQuery({
    queryKey: ['exposure', lau],
    queryFn: ({ signal }) => api.exposure(lau, signal),
    retry: false,
    refetchInterval: (q) => (q.state.data?.status === 'computing' ? POLL_MS : false),
  });
  const compute = useMutation({
    mutationFn: () => api.compute(lau),
    onSuccess: () => void qc.invalidateQueries({ queryKey: ['exposure', lau] }),
  });
  const ready = exposure.data?.status === 'ready';
  const cells = useQuery({
    queryKey: ['cells', lau, debounced],
    queryFn: ({ signal }) => api.cells(lau, debounced, signal),
    enabled: ready,
    placeholderData: (prev) => prev,
    retry: false,
  });
  const top = useMemo(
    () =>
      [...(cells.data?.features ?? [])]
        .sort((a, b) => b.properties.priority - a.properties.priority)
        .slice(0, 8)
        .map((f) => f.properties),
    [cells.data],
  );

  if (exposure.isPending) {
    return <LoadingSkeleton lines={5} label="Učitavam podatke o općini…" />;
  }
  if (exposure.isError) {
    return (
      <div className="grid gap-4">
        <ErrorState
          message={
            exposure.error instanceof Error ? exposure.error.message : 'Učitavanje nije uspjelo.'
          }
          onRetry={() => void exposure.refetch()}
        />
        <Link className="underline" to="/opcina">
          Natrag na pretragu općina
        </Link>
      </div>
    );
  }

  const ex = exposure.data;
  const m = ex.municipality;
  const cov = ex.hazards.heat.coverage;
  return (
    <div className="grid gap-8">
      <header>
        <p className="ot-eyebrow">Općina / grad</p>
        <h1 className="ot-display mt-1 text-2xl sm:text-3xl">{m.name}</h1>
        <p className="mt-1 text-neutral-700">
          {fmtInt(m.pop_total)} stanovnika, od toga {fmtInt(m.pop_65p)} starijih od 65 godina (popis
          2021., mreža 1 km).
          {m.demo ? ' Unaprijed izračunato.' : ''}
        </p>
        {ex.status === 'ready' ? (
          <p className="ot-noprint mt-3">
            <a
              className="ot-btn ot-btn--ghost"
              href={`/api/v1/municipalities/${encodeURIComponent(lau)}/brief`}
              target="_blank"
              rel="noopener noreferrer"
            >
              Otvori izvješće za ispis
            </a>
          </p>
        ) : null}
      </header>

      {ex.status === 'computing' ? (
        <div className="ot-card p-5" role="status" aria-live="polite">
          <p className="font-bold">Izračun je u tijeku…</p>
          <p className="text-neutral-700">
            Stranica se osvježava svakih 5 sekundi. Rezultat se sprema pa je sljedeći put trenutno
            dostupan.
          </p>
          <LoadingSkeleton lines={2} label="Izračun je u tijeku" />
        </div>
      ) : null}

      {ex.status === 'unavailable' ? (
        <EmptyState
          title="Izloženost još nije izračunata"
          body={
            ex.message ??
            'Za ovu općinu izračun još nije pokrenut ili za nju nema dovoljno klimatskih podataka (besplatna usluga Open-Meteo ograničava broj upita).'
          }
          action={
            <button
              type="button"
              className="ot-btn mt-3"
              onClick={() => compute.mutate()}
              disabled={compute.isPending}
            >
              {compute.isPending ? 'Pokrećem…' : 'Pokreni izračun'}
            </button>
          }
        />
      ) : null}
      {compute.isError ? (
        <ErrorState
          message={
            compute.error instanceof Error ? compute.error.message : 'Pokretanje nije uspjelo.'
          }
        />
      ) : null}

      {ready ? (
        <>
          <section
            aria-label="Ključni pokazatelji"
            className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4"
          >
            <Kpi label="Stanovnici" value={fmtInt(m.pop_total)} />
            <Kpi label="Stanovnici 65+" value={fmtInt(m.pop_65p)} />
            <Kpi
              label="65+ u područjima visoke vrućine"
              value={fmtInt(ex.kpis.heat_high_pop_65p)}
              tone="heat"
              note="razina visoka ili vrlo visoka"
            />
            <Kpi
              label="Izloženi poplavi"
              value="nije dostupno"
              tone="flood"
              note="Hrvatske vode objavljuju karte samo kao sliku; razinu ne računamo automatski."
            />
          </section>

          {cov ? (
            <p className="text-sm text-neutral-700">
              Klimatski podaci: {fmtInt(cov.heat_exact)} ćelija s vlastitom točkom,{' '}
              {fmtInt(cov.heat_approximate)} s najbližom točkom (do 25 km),{' '}
              {fmtInt(cov.heat_missing)} bez podataka; usporedna mreža Hrvatske ima{' '}
              {fmtInt(cov.grid_points)} točaka.
            </p>
          ) : null}

          <section className="ot-card p-5" aria-labelledby="bands-h">
            <h2 id="bands-h" className="ot-display text-xl">
              Vrućina po razinama
            </h2>
            <div className="mt-3 overflow-x-auto">
              <BandTable ex={ex} />
            </div>
          </section>

          <section
            className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_20rem]"
            aria-labelledby="prio-h"
          >
            <div>
              <h2 id="prio-h" className="ot-display mb-3 text-xl">
                Karta prioriteta
              </h2>
              {cells.isError ? (
                <ErrorState
                  message={
                    cells.error instanceof Error ? cells.error.message : 'Karta nije učitana.'
                  }
                  onRetry={() => void cells.refetch()}
                />
              ) : cells.data ? (
                <PriorityMap cells={cells.data} sites={cooling?.sites ?? []} onSelect={setPicked} />
              ) : (
                <LoadingSkeleton lines={4} label="Učitavam kartu prioriteta…" />
              )}
            </div>
            <aside className="grid content-start gap-4">
              <div className="ot-card p-4">
                <WeightSliders
                  weights={weights}
                  available={{ flood: false, heat: true, fire: false }}
                  onChange={setWeights}
                />
                <p className="mt-3 text-sm text-neutral-700">
                  Prioritet ćelije = Σ težina × razina opasnosti × (stanovnici 65+ + ½ ostalih).
                  Opasnosti bez podataka ne sudjeluju, a ostale težine se preračunaju na zbroj 1.
                </p>
              </div>
              <div className="ot-card p-4" aria-live="polite">
                <h3 className="font-bold">Odabrana ćelija</h3>
                {picked ? (
                  <p className="mt-1 text-sm">
                    {fmtInt(picked.pop_total)} stanovnika, {fmtInt(picked.pop_65p)} 65+. Toplinska
                    razina: {picked.heat_band ? BAND_LABEL[picked.heat_band] : 'bez podataka'}.
                    Prioritet {picked.priority.toFixed(1)}.
                  </p>
                ) : (
                  <p className="mt-1 text-sm text-neutral-700">
                    Kliknite ćeliju na karti ili pogledajte popis niže.
                  </p>
                )}
              </div>
            </aside>
          </section>

          {top.length > 0 ? (
            <section className="ot-card p-5" aria-labelledby="top-h">
              <h2 id="top-h" className="ot-display text-xl">
                Ćelije s najvišim prioritetom
              </h2>
              <div className="mt-3 overflow-x-auto">
                <table className="w-full border-collapse text-left">
                  <thead>
                    <tr className="border-b-2 border-neutral-700 text-sm">
                      <th scope="col" className="py-2 pr-3">
                        Ćelija (1 km)
                      </th>
                      <th scope="col" className="py-2 pr-3 text-right">
                        Stanovnika
                      </th>
                      <th scope="col" className="py-2 pr-3 text-right">
                        65+
                      </th>
                      <th scope="col" className="py-2 pr-3">
                        Vrućina
                      </th>
                      <th scope="col" className="py-2 text-right">
                        Prioritet
                      </th>
                    </tr>
                  </thead>
                  <tbody>
                    {top.map((c) => (
                      <tr key={c.grd_id} className="border-b border-neutral-300">
                        <td className="py-2 pr-3 text-sm">
                          {c.grd_id.replace('CRS3035RES1000m', '')}
                        </td>
                        <td className="ot-num py-2 pr-3 text-right">{fmtInt(c.pop_total)}</td>
                        <td className="ot-num py-2 pr-3 text-right">{fmtInt(c.pop_65p)}</td>
                        <td className="py-2 pr-3">{c.heat_band ? BAND_LABEL[c.heat_band] : '–'}</td>
                        <td className="ot-num py-2 text-right">{c.priority.toFixed(1)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          ) : null}

          <CoolingPanel
            key={`${lau}-${ex.kpis.heat_high_pop_65p ? 'hi' : 'lo'}`}
            lau={lau}
            onResult={setCooling}
            defaultBand={ex.kpis.heat_high_pop_65p ? 'visoka' : 'umjerena'}
          />
          {!ex.kpis.heat_high_pop_65p ? (
            <p className="-mt-4 text-sm text-neutral-700">
              U ovoj općini nijedna ćelija nije u razini „visoka” ili višoj, pa je za prijedlog
              uključen i pojas „umjerena”.
            </p>
          ) : null}
        </>
      ) : null}

      <p className="text-sm text-neutral-700">
        Izvori: Eurostat popis 2021. (mreža 1 km), GISCO granice općina, Open-Meteo (CC BY 4.0),
        OpenStreetMap suradnici.{' '}
        <Link className="underline" to="/metodologija">
          Metodologija
        </Link>
      </p>
    </div>
  );
}
