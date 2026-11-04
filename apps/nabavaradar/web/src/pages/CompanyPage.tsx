import { EmptyState, ErrorState, FreshnessChip, LoadingSkeleton } from '@dt/ui';
import { useQuery } from '@tanstack/react-query';
import { useId, useMemo, useState } from 'react';
import { Link, useParams, useSearchParams } from 'react-router-dom';
import { useAlertDialog } from '../components/AlertDialog';
import { TenderCard } from '../components/TenderCard';
import { ApiError, api } from '../lib/api';
import { download, toCsv } from '../lib/export';
import { formatDate, formatDateTime } from '../lib/format';
import { useCounties, useStatus } from '../lib/hooks';
import { isValidOib } from '../lib/oib';
import {
  DISLIKED_KEY,
  HIDDEN_KEY,
  MAX_DISLIKED,
  MAX_HIDDEN,
  SAVED_KEY,
  addCapped,
  toggleSaved,
  useStored,
  type SavedTender,
} from '../lib/storage';
import type { CompanyProfile, MatchItem, Queued } from '../lib/types';

const DEADLINE_OPTIONS = [
  { value: 0, label: 'Bilo koji' },
  { value: 7, label: 'najmanje 7 dana' },
  { value: 15, label: 'najmanje 15 dana' },
  { value: 30, label: 'najmanje 30 dana' },
];

export type SortKey = 'fit' | 'deadline' | 'value';
const SORTS: { value: SortKey; label: string }[] = [
  { value: 'fit', label: 'Prilagodba (najveća prva)' },
  { value: 'deadline', label: 'Rok (najbliži prvi)' },
  { value: 'value', label: 'Vrijednost (najveća prva)' },
];

const isQueued = (c: CompanyProfile | Queued | undefined): c is Queued =>
  c !== undefined && 'retry_after' in c;

function daysSince(iso: string | null): number | null {
  if (!iso) return null;
  const t = new Date(iso).getTime();
  return Number.isNaN(t) ? null : Math.floor((Date.now() - t) / 86_400_000);
}

/** Client-side sort and text search over the ranked list. Sorting by fit keeps the API order. */
export function arrange(items: MatchItem[], sort: SortKey, search: string): MatchItem[] {
  const needle = search.trim().toLowerCase();
  const kept = needle
    ? items.filter((i) =>
        [i.title, i.buyer, i.county, i.pub_no, i.cpv_division_label]
          .filter(Boolean)
          .join(' ')
          .toLowerCase()
          .includes(needle),
      )
    : items;
  if (sort === 'fit') return kept;
  const copy = [...kept];
  if (sort === 'deadline') {
    copy.sort((a, b) => (a.days_left ?? Infinity) - (b.days_left ?? Infinity));
  } else {
    copy.sort((a, b) => (b.value_eur ?? -1) - (a.value_eur ?? -1));
  }
  return copy;
}

export function CompanyPage() {
  const { oib = '' } = useParams();
  const valid = isValidOib(oib);
  const ids = useId();
  const { open } = useAlertDialog();

  const company = useQuery({
    queryKey: ['company', oib],
    enabled: valid,
    queryFn: ({ signal }) => api.company(oib, signal),
    refetchInterval: (q) =>
      isQueued(q.state.data) ? Math.max(3, q.state.data.retry_after) * 1000 : false,
    retry: (count, err) => !(err instanceof ApiError && err.status < 500) && count < 1,
  });
  const profile = company.data && !isQueued(company.data) ? company.data : null;

  // filters, sort and search live in the URL so the page can be shared
  const [params, setParams] = useSearchParams();
  const county = params.get('zupanija') ?? '';
  const days = Number(params.get('rok') ?? 0) || 0;
  const valueMin = params.get('od') ?? '';
  const valueMax = params.get('do') ?? '';
  const sort = (
    SORTS.some((s) => s.value === params.get('poredak')) ? params.get('poredak') : 'fit'
  ) as SortKey;
  const search = params.get('trazi') ?? '';
  const submittedDescription = params.get('opis') ?? '';
  const setParam = (key: string, value: string) =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        if (value) next.set(key, value);
        else next.delete(key);
        return next;
      },
      { replace: true },
    );
  const [description, setDescription] = useState(submittedDescription);
  const [copied, setCopied] = useState(false);

  const counties = useCounties();
  const status = useStatus();
  const [saved, setSaved] = useStored<SavedTender[]>(SAVED_KEY, []);
  const [hidden, setHidden] = useStored<string[]>(HIDDEN_KEY, []);
  const [disliked, setDisliked] = useStored<string[]>(DISLIKED_KEY, []);

  const apiParams = useMemo(
    () => ({
      oib,
      q: submittedDescription || undefined,
      county: county ? Number(county) : undefined,
      deadline_min_days: days || undefined,
      value_min: valueMin ? Number(valueMin) : undefined,
      value_max: valueMax ? Number(valueMax) : undefined,
      hide: hidden.length ? hidden.join(',') : undefined,
      dislike: disliked.length ? disliked.join(',') : undefined,
      limit: 60,
    }),
    [oib, submittedDescription, county, days, valueMin, valueMax, hidden, disliked],
  );
  const match = useQuery({
    queryKey: ['match', apiParams],
    enabled: !!profile,
    queryFn: ({ signal }) => api.match(apiParams, signal),
  });
  const shown = useMemo(() => arrange(match.data ?? [], sort, search), [match.data, sort, search]);
  const filtered = Boolean(county || days || valueMin || valueMax);
  const resetFilters = () =>
    setParams(
      (prev) => {
        const next = new URLSearchParams(prev);
        for (const k of ['zupanija', 'rok', 'od', 'do']) next.delete(k);
        return next;
      },
      { replace: true },
    );

  const hide = (item: MatchItem) => {
    setHidden((l) => addCapped(l, item.pub_no, MAX_HIDDEN));
    if (item.cpv_group) setDisliked((l) => addCapped(l, item.cpv_group as string, MAX_DISLIKED));
  };

  if (!valid) {
    return (
      <div className="nb-wrap py-10">
        <ErrorState message="Neispravan OIB: mora imati 11 znamenki i ispravnu kontrolnu znamenku." />
        <p className="mt-4">
          <Link to="/" className="underline">
            Natrag na početnu
          </Link>
        </p>
      </div>
    );
  }

  const dataAge = daysSince(profile?.data_as_of ?? null);
  const ted =
    typeof status.data?.ted_competition_retrieved_at === 'string'
      ? status.data.ted_competition_retrieved_at
      : null;

  return (
    <div className="nb-wrap py-10">
      {company.isLoading ? <LoadingSkeleton lines={3} label="Učitavam podatke o tvrtki…" /> : null}
      {isQueued(company.data) ? (
        <div className="nr-card" role="status" aria-live="polite">
          <p className="font-bold">Upit prema Sudskom registru je u redu čekanja.</p>
          <p className="mt-1 text-sm">
            Registar dopušta 6 upita u minuti. Automatski ponovno provjeravam za oko{' '}
            {company.data.retry_after} s.
          </p>
        </div>
      ) : null}
      {company.error ? (
        company.error instanceof ApiError && company.error.status === 404 ? (
          <EmptyState
            title="Tvrtka nije pronađena"
            body={company.error.message}
            action={
              <Link to="/" className="underline">
                Pokušajte drugi OIB
              </Link>
            }
          />
        ) : (
          <ErrorState
            message={(company.error as Error).message}
            onRetry={() => void company.refetch()}
          />
        )
      ) : null}

      {profile ? (
        <>
          <header>
            <p className="text-sm num">OIB {profile.oib}</p>
            <h1 className="nb-h2">{profile.name}</h1>
            <p className="mt-1">
              {profile.county
                ? `${profile.county.name} · ${profile.county.nuts3}`
                : 'Županija nije poznata'}
            </p>
            <div className="mt-3 flex flex-wrap gap-2" aria-label="NKD djelatnosti">
              {profile.activities.length === 0 ? (
                <span className="text-sm">
                  Tvrtka nema upisanu NKD djelatnost; opišite što nudite u polju ispod.
                </span>
              ) : (
                profile.activities.slice(0, 10).map((a) => (
                  <span
                    key={`${a.code}-${a.version}`}
                    className={`nr-nkd ${a.is_main ? 'nr-nkd--main' : ''}`}
                    title={`${a.version}${a.is_main ? ' · glavna djelatnost' : ''}`}
                  >
                    <span className="num">{a.code}</span> {a.label}
                    {a.is_main ? <span className="dt-sr-only"> (glavna djelatnost)</span> : null}
                  </span>
                ))
              )}
            </div>
            <p className="mt-3 flex flex-wrap items-center gap-2 text-sm">
              <span>
                Podaci o tvrtki: Sudski registar
                {profile.source.environment === 'test' ? ' (testno okruženje)' : ''}, snimka od{' '}
                <strong className="num">{formatDate(profile.data_as_of)}</strong>
              </span>
              <FreshnessChip days={dataAge} />
              {ted ? <span>· natječaji (TED) dohvaćeni {formatDateTime(ted)}</span> : null}
            </p>
            <div className="mt-4 flex flex-wrap gap-3">
              <button
                type="button"
                className="nb-btn nb-btn--yellow nb-btn--sm"
                onClick={() => open({ oib: profile.oib, query: submittedDescription || undefined })}
              >
                Pošalji mi relevantne natječaje
              </button>
            </div>
          </header>

          <form
            className="nr-filters nr-card mt-6"
            aria-label="Filteri"
            onSubmit={(e) => {
              e.preventDefault();
              setParam('opis', description.trim());
            }}
          >
            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <div>
                <label htmlFor={`${ids}-c`} className="block text-sm font-bold">
                  Županija naručitelja
                </label>
                <select
                  id={`${ids}-c`}
                  className="nr-input"
                  value={county}
                  onChange={(e) => setParam('zupanija', e.target.value)}
                >
                  <option value="">Sve županije</option>
                  {counties.data?.map((c) => (
                    <option key={c.code} value={c.code}>
                      {c.name}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor={`${ids}-d`} className="block text-sm font-bold">
                  Rok do predaje
                </label>
                <select
                  id={`${ids}-d`}
                  className="nr-input"
                  value={days}
                  onChange={(e) => setParam('rok', Number(e.target.value) ? e.target.value : '')}
                >
                  {DEADLINE_OPTIONS.map((o) => (
                    <option key={o.value} value={o.value}>
                      {o.label}
                    </option>
                  ))}
                </select>
              </div>
              <div>
                <label htmlFor={`${ids}-vmin`} className="block text-sm font-bold">
                  Vrijednost od (EUR)
                </label>
                <input
                  id={`${ids}-vmin`}
                  className="nr-input num"
                  inputMode="numeric"
                  value={valueMin}
                  onChange={(e) => setParam('od', e.target.value.replace(/\D/g, ''))}
                />
              </div>
              <div>
                <label htmlFor={`${ids}-vmax`} className="block text-sm font-bold">
                  Vrijednost do (EUR)
                </label>
                <input
                  id={`${ids}-vmax`}
                  className="nr-input num"
                  inputMode="numeric"
                  value={valueMax}
                  onChange={(e) => setParam('do', e.target.value.replace(/\D/g, ''))}
                />
              </div>
            </div>
            <div className="mt-3">
              <label htmlFor={`${ids}-q`} className="block text-sm font-bold">
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
                <button type="submit" className="nr-btn nr-btn--ghost">
                  Primijeni opis
                </button>
                {filtered ? (
                  <button type="button" className="nr-btn nr-btn--ghost" onClick={resetFilters}>
                    Očisti filtere
                  </button>
                ) : null}
              </div>
            </div>
          </form>

          <section aria-labelledby={`${ids}-list`} className="mt-8">
            <div className="flex flex-wrap items-end justify-between gap-4">
              <h2 id={`${ids}-list`} className="nb-h2" style={{ fontSize: '2rem' }}>
                Otvoreni natječaji po prilagodbi
                {match.data ? <span className="num"> ({shown.length}</span> : null}
                {match.data && shown.length !== match.data.length ? (
                  <span className="num"> od {match.data.length}</span>
                ) : null}
                {match.data ? <span className="num">)</span> : null}
              </h2>
              <div className="nr-no-print flex flex-wrap items-end gap-3">
                <div>
                  <label htmlFor={`${ids}-s`} className="block text-sm font-bold">
                    Poredak
                  </label>
                  <select
                    id={`${ids}-s`}
                    className="nr-input"
                    value={sort}
                    onChange={(e) =>
                      setParam('poredak', e.target.value === 'fit' ? '' : e.target.value)
                    }
                  >
                    {SORTS.map((s) => (
                      <option key={s.value} value={s.value}>
                        {s.label}
                      </option>
                    ))}
                  </select>
                </div>
                <div>
                  <label htmlFor={`${ids}-f`} className="block text-sm font-bold">
                    Traži u rezultatima
                  </label>
                  <input
                    id={`${ids}-f`}
                    type="search"
                    className="nr-input"
                    value={search}
                    onChange={(e) => setParam('trazi', e.target.value)}
                  />
                </div>
                <button
                  type="button"
                  className="nb-btn nb-btn--light nb-btn--sm"
                  disabled={shown.length === 0}
                  onClick={() => download(`natjecaji-${oib}.csv`, toCsv(shown), 'text/csv')}
                >
                  Izvezi CSV
                </button>
                <button
                  type="button"
                  className="nb-btn nb-btn--light nb-btn--sm"
                  onClick={async () => {
                    try {
                      await navigator.clipboard.writeText(window.location.href);
                      setCopied(true);
                      setTimeout(() => setCopied(false), 2500);
                    } catch {
                      window.prompt('Kopirajte poveznicu:', window.location.href);
                    }
                  }}
                >
                  Kopiraj poveznicu
                </button>
              </div>
            </div>
            <p role="status" aria-live="polite" className="mt-1 text-sm">
              {copied ? 'Poveznica je kopirana.' : ''}
            </p>
            {hidden.length > 0 ? (
              <p className="mt-2 text-sm">
                Sakriveno ste {hidden.length} {hidden.length === 1 ? 'natječaj' : 'natječaja'} („Ne
                zanima me”).{' '}
                <button
                  type="button"
                  className="underline"
                  onClick={() => {
                    setHidden([]);
                    setDisliked([]);
                  }}
                >
                  Prikaži ih ponovno
                </button>
              </p>
            ) : null}
            {match.isLoading ? <LoadingSkeleton lines={5} label="Tražim natječaje…" /> : null}
            {match.error ? (
              <ErrorState
                message={(match.error as Error).message}
                onRetry={() => void match.refetch()}
              />
            ) : null}
            {match.data && shown.length === 0 ? (
              <EmptyState
                title="Nema otvorenih natječaja za ove uvjete"
                body={
                  filtered || submittedDescription || search
                    ? 'Pokušajte proširiti pretragu: uklonite filtere županije, roka ili vrijednosti.'
                    : 'Trenutno nema otvorenih natječaja koji odgovaraju djelatnostima ove tvrtke. Dodajte opis onoga što nudite ili provjerite ponovno sutra.'
                }
                action={
                  filtered ? (
                    <button type="button" className="nr-btn" onClick={resetFilters}>
                      Očisti filtere
                    </button>
                  ) : undefined
                }
              />
            ) : null}
            {shown.length > 0 ? (
              <ol className="mt-4 grid gap-5" aria-label="Rangirani natječaji">
                {shown.map((item) => (
                  <TenderCard
                    key={item.pub_no}
                    item={item}
                    saved={saved.some((s) => s.pub_no === item.pub_no)}
                    onToggleSave={(it) => setSaved((l) => toggleSaved(l, it))}
                    onHide={hide}
                  />
                ))}
              </ol>
            ) : null}
          </section>
        </>
      ) : null}
    </div>
  );
}
