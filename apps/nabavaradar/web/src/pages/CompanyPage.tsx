import { EmptyState, ErrorState, FreshnessChip, LoadingSkeleton } from '@dt/ui';
import { useQuery } from '@tanstack/react-query';
import { useId, useMemo, useState } from 'react';
import { Link, useParams } from 'react-router-dom';
import { SubscribeBox } from '../components/SubscribeBox';
import { TenderCard } from '../components/TenderCard';
import { ApiError, api } from '../lib/api';
import { formatDate, formatDateTime } from '../lib/format';
import { useCounties, useStatus } from '../lib/hooks';
import { isValidOib } from '../lib/oib';
import type { CompanyProfile, Queued } from '../lib/types';

const DEADLINE_OPTIONS = [
  { value: 0, label: 'Bilo koji' },
  { value: 7, label: 'najmanje 7 dana' },
  { value: 15, label: 'najmanje 15 dana' },
  { value: 30, label: 'najmanje 30 dana' },
];

const isQueued = (c: CompanyProfile | Queued | undefined): c is Queued =>
  c !== undefined && 'retry_after' in c;

function daysSince(iso: string | null): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  return Number.isNaN(t) ? null : Math.floor((Date.now() - t) / 86_400_000);
}

export function CompanyPage() {
  const { oib = '' } = useParams();
  const valid = isValidOib(oib);
  const ids = useId();

  const company = useQuery({
    queryKey: ['company', oib],
    enabled: valid,
    queryFn: ({ signal }) => api.company(oib, signal),
    refetchInterval: (q) => (isQueued(q.state.data) ? Math.max(3, q.state.data.retry_after) * 1000 : false),
    retry: (count, err) => !(err instanceof ApiError && err.status < 500) && count < 1,
  });
  const profile = company.data && !isQueued(company.data) ? company.data : null;

  const [county, setCounty] = useState('');
  const [days, setDays] = useState(0);
  const [valueMin, setValueMin] = useState('');
  const [valueMax, setValueMax] = useState('');
  const [description, setDescription] = useState('');
  const [submittedDescription, setSubmittedDescription] = useState('');
  const counties = useCounties();
  const status = useStatus();

  const params = useMemo(
    () => ({
      oib,
      q: submittedDescription || undefined,
      county: county ? Number(county) : undefined,
      deadline_min_days: days || undefined,
      value_min: valueMin ? Number(valueMin) : undefined,
      value_max: valueMax ? Number(valueMax) : undefined,
      limit: 30,
    }),
    [oib, submittedDescription, county, days, valueMin, valueMax],
  );
  const match = useQuery({
    queryKey: ['match', params],
    enabled: !!profile,
    queryFn: ({ signal }) => api.match(params, signal),
  });
  const filtered = Boolean(county || days || valueMin || valueMax);
  const resetFilters = () => {
    setCounty('');
    setDays(0);
    setValueMin('');
    setValueMax('');
  };

  if (!valid) {
    return (
      <div className="mx-auto max-w-5xl p-4">
        <ErrorState message="Neispravan OIB: mora imati 11 znamenki i ispravnu kontrolnu znamenku." />
        <p className="mt-4">
          <Link to="/" className="text-brand-700 underline">
            Natrag na početnu
          </Link>
        </p>
      </div>
    );
  }

  const dataAge = daysSince(profile?.data_as_of ?? null);
  const ted = typeof status.data?.ted_competition_retrieved_at === 'string' ? status.data.ted_competition_retrieved_at : null;

  return (
    <div className="mx-auto max-w-5xl p-4">
      {company.isLoading ? <LoadingSkeleton lines={3} label="Učitavam podatke o tvrtki…" /> : null}
      {isQueued(company.data) ? (
        <div className="nr-card" role="status" aria-live="polite">
          <p className="font-semibold">Upit prema Sudskom registru je u redu čekanja.</p>
          <p className="mt-1 text-sm">
            Registar dopušta 6 upita u minuti. Automatski ponovno provjeravam za oko {company.data.retry_after} s.
          </p>
        </div>
      ) : null}
      {company.error ? (
        company.error instanceof ApiError && company.error.status === 404 ? (
          <EmptyState
            title="Tvrtka nije pronađena"
            body={company.error.message}
            action={
              <Link to="/" className="text-brand-700 underline">
                Pokušajte drugi OIB
              </Link>
            }
          />
        ) : (
          <ErrorState message={(company.error as Error).message} onRetry={() => void company.refetch()} />
        )
      ) : null}

      {profile ? (
        <>
          <header>
            <p className="text-sm text-neutral-600 num">OIB {profile.oib}</p>
            <h1 className="text-2xl font-semibold">{profile.name}</h1>
            <p className="mt-1 text-neutral-600">{profile.county ? `${profile.county.name} · ${profile.county.nuts3}` : 'Županija nije poznata'}</p>
            <div className="mt-3 flex flex-wrap gap-2" aria-label="NKD djelatnosti">
              {profile.activities.length === 0 ? (
                <span className="text-sm">
                  Tvrtka nema upisanu NKD djelatnost; opišite što nudite u polju ispod.
                </span>
              ) : (
                profile.activities.slice(0, 10).map((a) => (
                  <span key={`${a.code}-${a.version}`} className={`nr-nkd ${a.is_main ? 'nr-nkd--main' : ''}`} title={`${a.version}${a.is_main ? ' · glavna djelatnost' : ''}`}>
                    <span className="num">{a.code}</span> {a.label}
                    {a.is_main ? <span className="dt-sr-only"> (glavna djelatnost)</span> : null}
                  </span>
                ))
              )}
            </div>
            <p className="mt-3 flex flex-wrap items-center gap-2 text-sm text-neutral-700">
              <span>
                Podaci o tvrtki: Sudski registar{profile.source.environment === 'test' ? ' (testno okruženje)' : ''}, snimka od{' '}
                <strong className="num">{formatDate(profile.data_as_of)}</strong>
              </span>
              <FreshnessChip days={dataAge} />
              {ted ? <span>· natječaji (TED) dohvaćeni {formatDateTime(ted)}</span> : null}
            </p>
          </header>

          <form
            className="nr-filters nr-card mt-4"
            aria-label="Filteri"
            onSubmit={(e) => {
              e.preventDefault();
              setSubmittedDescription(description.trim());
            }}
          >
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <label htmlFor={`${ids}-c`} className="block text-sm font-semibold">Županija naručitelja</label>
                <select id={`${ids}-c`} className="nr-input" value={county} onChange={(e) => setCounty(e.target.value)}>
                  <option value="">Sve županije</option>
                  {counties.data?.map((c) => (
                    <option key={c.code} value={c.code}>{c.name}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor={`${ids}-d`} className="block text-sm font-semibold">Rok do predaje</label>
                <select id={`${ids}-d`} className="nr-input" value={days} onChange={(e) => setDays(Number(e.target.value))}>
                  {DEADLINE_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>{o.label}</option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor={`${ids}-vmin`} className="block text-sm font-semibold">Vrijednost od (EUR)</label>
                <input id={`${ids}-vmin`} className="nr-input num" inputMode="numeric" value={valueMin} onChange={(e) => setValueMin(e.target.value.replace(/\D/g, ''))} />
              </div>
              <div>
                <label htmlFor={`${ids}-vmax`} className="block text-sm font-semibold">Vrijednost do (EUR)</label>
                <input id={`${ids}-vmax`} className="nr-input num" inputMode="numeric" value={valueMax} onChange={(e) => setValueMax(e.target.value.replace(/\D/g, ''))} />
              </div>
            </div>
            <div className="mt-3">
              <label htmlFor={`${ids}-q`} className="block text-sm font-semibold">
                Što nudite? (neobavezno – dopunjuje djelatnosti iz registra)
              </label>
              <div className="mt-1 flex flex-wrap gap-3">
                <input
                  id={`${ids}-q`}
                  className="nr-input"
                  style={{ maxWidth: '36rem' }}
                  maxLength={2000}
                  value={description}
                  onChange={(e) => setDescription(e.target.value)}
                  placeholder="npr. servis dizalica i protupožarne opreme"
                />
                <button type="submit" className="nr-btn nr-btn--ghost">Primijeni opis</button>
                {filtered ? (
                  <button type="button" className="nr-btn nr-btn--ghost" onClick={resetFilters}>Očisti filtere</button>
                ) : null}
              </div>
            </div>
          </form>

          <section aria-labelledby={`${ids}-list`} className="mt-6">
            <h2 id={`${ids}-list`} className="text-xl font-semibold">
              Otvoreni natječaji po prilagodbi
              {match.data ? <span className="num text-neutral-600"> ({match.data.length})</span> : null}
            </h2>
            {match.isLoading ? <LoadingSkeleton lines={5} label="Tražim natječaje…" /> : null}
            {match.error ? <ErrorState message={(match.error as Error).message} onRetry={() => void match.refetch()} /> : null}
            {match.data && match.data.length === 0 ? (
              <EmptyState
                title="Nema otvorenih natječaja za ove uvjete"
                body={
                  filtered || submittedDescription
                    ? 'Pokušajte proširiti pretragu: uklonite filtere županije, roka ili vrijednosti.'
                    : 'Trenutno nema otvorenih natječaja koji odgovaraju djelatnostima ove tvrtke. Dodajte opis onoga što nudite ili provjerite ponovno sutra.'
                }
                action={filtered ? <button type="button" className="nr-btn" onClick={resetFilters}>Očisti filtere</button> : undefined}
              />
            ) : null}
            {match.data && match.data.length > 0 ? (
              <ol className="mt-3 grid gap-4" aria-label="Rangirani natječaji">
                {match.data.map((item) => (
                  <TenderCard key={item.pub_no} item={item} />
                ))}
              </ol>
            ) : null}
          </section>

          <div className="mt-8">
            <SubscribeBox oib={profile.oib} query={submittedDescription || undefined} />
          </div>
        </>
      ) : null}
    </div>
  );
}
