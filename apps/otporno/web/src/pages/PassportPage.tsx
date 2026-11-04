import { ConfidenceBadge, ErrorState, LoadingSkeleton, formatDateTime } from '@dt/ui';
import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { ActionList } from '../components/ActionList';
import { AddressSearch } from '../components/AddressSearch';
import { FloodMap } from '../components/FloodMap';
import { HeatBars } from '../components/HeatBars';
import { FlameIcon, SunIcon, WaveIcon } from '../components/icons';
import { RingGauge } from '../components/RingGauge';
import { ApiError, api } from '../lib/api';
import { fmtDec, pluralDays } from '../lib/format';
import type { Passport } from '../lib/types';

function parseCoord(v: string | null): number | null {
  if (v == null || v.trim() === '') return null;
  const n = Number(v);
  return Number.isFinite(n) ? n : null;
}

function FloodCard({ p }: { p: Passport }) {
  const f = p.flood;
  return (
    <article className="ot-ticket ot-ticket--flood" aria-labelledby="card-flood">
      <header
        className="flex items-center gap-2 text-flood-700"
        style={{ color: 'rgb(var(--flood-700))' }}
      >
        <WaveIcon />
        <h2 id="card-flood" className="ot-display text-xl">
          Poplava
        </h2>
      </header>
      <div className="mt-3 grid place-items-center">
        <RingGauge band={f.band} hazard="Poplava" unknownLabel="Razina nije određena" />
      </div>
      <p className="mt-3 font-bold">
        {f.message ?? 'Razina je određena iz karata Hrvatskih voda.'}
      </p>
      <p className="mt-2 text-sm text-neutral-700">
        Karte Hrvatskih voda ({f.map_year}.) objavljene su samo kao slika na karti, pa razinu za
        vašu točku ne računamo automatski. Pogledajte kartu niže i uključite sva tri scenarija.
      </p>
      <p className="mt-3">
        <a href="#karta-poplava" className="ot-btn ot-btn--ghost">
          Pogledaj kartu poplava
        </a>
      </p>
    </article>
  );
}

function HeatCard({ p }: { p: Passport }) {
  const h = p.heat;
  return (
    <article className="ot-ticket ot-ticket--heat" aria-labelledby="card-heat">
      <header className="flex items-center gap-2" style={{ color: 'rgb(var(--heat-700))' }}>
        <SunIcon />
        <h2 id="card-heat" className="ot-display text-xl">
          Vrućina
        </h2>
      </header>
      {h.status === 'ready' ? (
        <>
          <div className="mt-3 grid place-items-center">
            <RingGauge band={h.band} hazard="Vrućina" unknownLabel="Bez ocjene" />
          </div>
          {h.percentile != null ? (
            <p className="mt-2 text-center text-sm text-neutral-700">
              Oko {h.percentile} % točaka u usporednoj mreži Hrvatske ima jednak ili manji broj
              vrućih dana u 2031.–2050.
            </p>
          ) : (
            <p className="mt-2 text-sm font-bold">{h.message}</p>
          )}
          <div className="mt-4">
            <HeatBars heat={h} />
          </div>
          {h.future_tropical_nights != null && h.base_tropical_nights != null ? (
            <p className="mt-4">
              <strong>Tropske noći</strong> (najniža temperatura ≥ 20 °C):{' '}
              <span className="ot-num">
                {fmtDec(h.base_tropical_nights)} {pluralDays(h.base_tropical_nights)}
              </span>{' '}
              danas, <span className="ot-num">{fmtDec(h.future_tropical_nights)}</span> u
              2031.–2050.
            </p>
          ) : null}
          <div className="mt-4 flex flex-wrap items-center gap-2">
            {h.confidence ? <ConfidenceBadge level={h.confidence} /> : null}
          </div>
          {h.confidence_reasons && h.confidence_reasons.length > 0 ? (
            <ul className="mt-2 list-disc pl-5 text-sm text-neutral-700">
              {h.confidence_reasons.map((r) => (
                <li key={r}>{r}</li>
              ))}
            </ul>
          ) : null}
          {h.model_point?.approximate ? (
            <p className="mt-2 text-sm text-neutral-700">
              Korištena je najbliža modelska točka, udaljena oko {fmtDec(h.model_point.distance_km)}{' '}
              km.
            </p>
          ) : null}
          <p className="mt-3 text-sm text-neutral-700">
            Vrući dan: najviša temperatura ≥ 30 °C. {h.attribution}.
          </p>
        </>
      ) : (
        <p className="mt-4 font-bold">{h.message}</p>
      )}
    </article>
  );
}

function FireCard({ p }: { p: Passport }) {
  return (
    <article className="ot-ticket ot-ticket--fire" aria-labelledby="card-fire">
      <header className="flex items-center gap-2 text-neutral-700">
        <FlameIcon />
        <h2 id="card-fire" className="ot-display text-xl">
          Požar
        </h2>
      </header>
      <div className="mt-3 grid place-items-center">
        <RingGauge band={null} hazard="Požar" unknownLabel="Još nije dostupno" />
      </div>
      <p className="mt-3 text-neutral-700">{p.fire.message}</p>
    </article>
  );
}

export function PassportPage() {
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const lat = parseCoord(params.get('lat'));
  const lon = parseCoord(params.get('lon'));
  const title = params.get('q');

  const query = useQuery({
    queryKey: ['passport', lat, lon],
    queryFn: ({ signal }) => api.passport(lat as number, lon as number, signal),
    enabled: lat != null && lon != null,
    retry: false,
    staleTime: 10 * 60_000,
  });

  const search = (
    <div className="ot-card ot-noprint p-4">
      <AddressSearch
        label="Provjerite drugu adresu"
        onSelect={(item) =>
          navigate(
            `/putovnica?lat=${item.lat.toFixed(5)}&lon=${item.lon.toFixed(5)}&q=${encodeURIComponent(item.title)}`,
          )
        }
      />
    </div>
  );

  if (lat == null || lon == null) {
    return (
      <div className="grid gap-4">
        <h1 className="ot-display text-2xl">Putovnica rizika</h1>
        <ErrorState message="Nedostaje adresa. Upišite adresu u polje niže." />
        {search}
      </div>
    );
  }
  if (query.isPending) {
    return (
      <div className="grid gap-4">
        <h1 className="ot-display text-2xl">{title ?? 'Putovnica rizika'}</h1>
        <LoadingSkeleton lines={6} label="Izrađujem putovnicu rizika…" />
      </div>
    );
  }
  if (query.isError) {
    const outside = query.error instanceof ApiError && query.error.status === 422;
    return (
      <div className="grid gap-4">
        <h1 className="ot-display text-2xl">{title ?? 'Putovnica rizika'}</h1>
        <ErrorState
          message={
            outside
              ? `${query.error.message} Otporko radi samo za adrese u Hrvatskoj.`
              : query.error.message
          }
          onRetry={outside ? undefined : () => void query.refetch()}
        />
        {search}
      </div>
    );
  }

  const p = query.data;
  const m = p.location.municipality;
  return (
    <div className="grid gap-8">
      <header>
        <p className="ot-eyebrow">Putovnica rizika</p>
        <h1 className="ot-display mt-1 text-2xl sm:text-3xl">
          {title ?? `${fmtDec(p.location.lat)}, ${fmtDec(p.location.lon)}`}
        </h1>
        <p className="mt-1 text-neutral-700">
          {m.name} · izrađeno {formatDateTime(p.computed_at)} ·{' '}
          <Link className="underline" to={`/opcina/${m.lau_id}`}>
            pogledajte cijelu općinu
          </Link>
        </p>
      </header>

      <section aria-label="Tri opasnosti" className="grid gap-5 lg:grid-cols-3">
        <FloodCard p={p} />
        <HeatCard p={p} />
        <FireCard p={p} />
      </section>

      <section aria-labelledby="sto-uciniti" className="ot-card p-6">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <h2 id="sto-uciniti" className="ot-display text-xl">
            Što učiniti
          </h2>
          <button
            type="button"
            className="ot-btn ot-btn--ghost ot-noprint"
            onClick={() => window.print()}
          >
            Ispiši popis
          </button>
        </div>
        <p className="mb-4 mt-1 text-neutral-700">
          Koraci su preuzeti iz javnih uputa nadležnih službi; uz svaki je naveden izvor. Označite
          što ste već napravili (pamti se samo u ovom pregledniku).
        </p>
        <ActionList
          storageKey={`otporko-ticks-${lat.toFixed(3)}-${lon.toFixed(3)}`}
          groups={[
            { key: 'flood', title: 'Poplava', items: p.actions.flood },
            { key: 'heat', title: 'Vrućina', items: p.actions.heat },
          ]}
        />
      </section>

      <section
        id="karta-poplava"
        aria-labelledby="karta-h"
        className="ot-card p-6"
        style={{ scrollMarginTop: '1rem' }}
      >
        <h2 id="karta-h" className="ot-display text-xl">
          Karta opasnosti od poplava
        </h2>
        <p className="mb-4 mt-1 text-neutral-700">
          Izvor: Hrvatske vode, Karte opasnosti od poplava, 2019.
        </p>
        <FloodMap lat={p.location.lat} lon={p.location.lon} flood={p.flood} />
      </section>

      <section aria-labelledby="izv-h" className="text-sm text-neutral-700">
        <h2 id="izv-h" className="font-bold text-neutral-900">
          Izvori i ograničenja
        </h2>
        <ul className="mt-1 list-disc pl-5">
          {p.sources.map((s) => (
            <li key={s.id}>
              {s.title}
              {s.note ? ` — ${s.note}` : ''}
            </li>
          ))}
          <li>
            Klimatski rezultati su modelske procjene za mrežu od oko 10 km, ne mjerenja na vašoj
            adresi.{' '}
            <Link className="underline" to="/metodologija">
              Metodologija
            </Link>
            .
          </li>
        </ul>
      </section>
      {search}
    </div>
  );
}
