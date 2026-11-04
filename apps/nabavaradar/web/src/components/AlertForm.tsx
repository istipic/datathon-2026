import { useQuery } from '@tanstack/react-query';
import { useEffect, useId, useState } from 'react';
import { ApiError, api } from '../lib/api';
import { useCounties } from '../lib/hooks';
import { isValidOib } from '../lib/oib';
import type { Frequency } from '../lib/types';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
export const DEFAULT_MIN_FIT_PCT = 75;

/** The consent sentence used until the API answers (the API sends the same text, built from the settings). */
export const consentFallback = (frequency: Frequency, pct: number) =>
  `Pristajem da Birokratko na ovu e-adresu ${
    frequency === 'daily'
      ? 'najviše jednom dnevno (u 7:00) šalje obavijest o natječajima'
      : 'jednom tjedno (ponedjeljkom u 7:00) šalje pregled natječaja'
  } čija prilagodba mojem profilu iznosi najmanje ${pct} %. Pohranjuju se samo e-adresa, OIB ili opis pretrage i postavke upozorenja. Pretplatu mogu promijeniti ili otkazati poveznicom u svakoj poruci.`;

export interface AlertFormProps {
  /** OIB of the company page the form was opened from. */
  oib?: string;
  /** Free-text description of what the company offers (company page). */
  query?: string;
  onDone?: () => void;
}

/** "Pošalji mi relevantne natječaje": e-mail, profile, threshold, filters and frequency (double opt-in). */
export function AlertForm({ oib: oibProp, query: queryProp, onDone }: AlertFormProps) {
  const id = useId();
  const [email, setEmail] = useState('');
  const [oib, setOib] = useState(oibProp ?? '');
  const [query, setQuery] = useState(queryProp ?? '');
  const [pct, setPct] = useState(DEFAULT_MIN_FIT_PCT);
  const [minValue, setMinValue] = useState('');
  const [counties, setCounties] = useState<number[]>([]);
  const [divisions, setDivisions] = useState<string[]>([]);
  const [frequency, setFrequency] = useState<Frequency>('daily');
  const [consent, setConsent] = useState(false);
  const [state, setState] = useState<{ kind: 'idle' | 'busy' | 'ok' | 'error'; text: string }>({
    kind: 'idle',
    text: '',
  });

  const countyList = useCounties();
  const highlights = useQuery({
    queryKey: ['highlights'],
    staleTime: 5 * 60_000,
    queryFn: ({ signal }) => api.highlights(signal),
  });

  const oibOk = oib === '' || isValidOib(oib);
  const hasProfile = (oib !== '' && isValidOib(oib)) || query.trim() !== '';
  const emailOk = EMAIL_RE.test(email);
  const minFit = pct / 100;

  // debounce what the live preview and the consent text depend on
  const [settled, setSettled] = useState({ pct, minValue, counties, divisions, oib, query });
  useEffect(() => {
    const t = setTimeout(() => setSettled({ pct, minValue, counties, divisions, oib, query }), 350);
    return () => clearTimeout(t);
  }, [pct, minValue, counties, divisions, oib, query]);

  const settledProfile =
    (settled.oib !== '' && isValidOib(settled.oib)) || settled.query.trim() !== '';
  const preview = useQuery({
    queryKey: ['alert-preview', settled],
    enabled: settledProfile,
    retry: false,
    queryFn: ({ signal }) =>
      api.alertPreview(
        {
          oib: isValidOib(settled.oib) ? settled.oib : undefined,
          q: settled.query.trim() || undefined,
          min_fit: settled.pct / 100,
          min_value_eur: settled.minValue ? Number(settled.minValue) : undefined,
          counties: settled.counties,
          cpv: settled.divisions,
        },
        signal,
      ),
  });
  const consentQuery = useQuery({
    queryKey: ['consent', frequency, settled.pct],
    retry: false,
    staleTime: Infinity,
    queryFn: ({ signal }) => api.consentText(frequency, settled.pct / 100, signal),
  });
  const consentText = consentQuery.data ?? consentFallback(frequency, pct);

  const toggle = <T,>(list: T[], v: T): T[] =>
    list.includes(v) ? list.filter((x) => x !== v) : [...list, v];

  return (
    <form
      noValidate
      aria-label="Obavijesti o relevantnim natječajima"
      onSubmit={async (e) => {
        e.preventDefault();
        if (!emailOk || !hasProfile || !oibOk || !consent) return;
        setState({ kind: 'busy', text: 'Šaljem…' });
        try {
          const res = await api.subscribe({
            email,
            oib: oib && isValidOib(oib) ? oib : undefined,
            query: query.trim() || undefined,
            consent,
            min_fit: minFit,
            min_value_eur: minValue ? Number(minValue) : null,
            counties,
            cpv_divisions: divisions,
            frequency,
          });
          setState({ kind: 'ok', text: res.detail });
          onDone?.();
        } catch (err) {
          setState({
            kind: 'error',
            text: err instanceof ApiError ? err.message : 'Pretplata nije uspjela.',
          });
        }
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label htmlFor={`${id}-e`} className="block font-bold">
            E-adresa
          </label>
          <input
            id={`${id}-e`}
            type="email"
            className="nr-input mt-1"
            autoComplete="email"
            value={email}
            aria-invalid={email !== '' && !emailOk}
            onChange={(e) => setEmail(e.target.value)}
          />
        </div>
        <div>
          <label htmlFor={`${id}-o`} className="block font-bold">
            OIB tvrtke
          </label>
          <input
            id={`${id}-o`}
            className="nr-input num mt-1"
            inputMode="numeric"
            maxLength={11}
            value={oib}
            aria-invalid={!oibOk}
            aria-describedby={`${id}-oh`}
            onChange={(e) => setOib(e.target.value.replace(/\D/g, ''))}
          />
          <p id={`${id}-oh`} className="mt-1 text-sm" role="status">
            {oibOk
              ? 'Ili opišite što nudite u polju ispod.'
              : 'Kontrolna znamenka OIB-a nije ispravna.'}
          </p>
        </div>
      </div>

      <div className="mt-4">
        <label htmlFor={`${id}-q`} className="block font-bold">
          Što nudite? <span className="font-medium">(neobavezno ako je upisan OIB)</span>
        </label>
        <input
          id={`${id}-q`}
          className="nr-input mt-1"
          maxLength={500}
          value={query}
          placeholder="npr. servis dizalica i protupožarne opreme"
          onChange={(e) => setQuery(e.target.value)}
        />
      </div>

      <div className="mt-5 nb-card">
        <label htmlFor={`${id}-t`} className="block font-bold">
          Javi mi kad prilagodba bude barem <span className="num">{pct} %</span>
        </label>
        <div className="mt-2 grid items-center gap-3 sm:grid-cols-[1fr_6rem]">
          <input
            id={`${id}-t`}
            type="range"
            min={50}
            max={95}
            step={1}
            value={pct}
            onChange={(e) => setPct(Number(e.target.value))}
            aria-valuetext={`${pct} posto`}
          />
          <input
            aria-label="Prag prilagodbe u postocima"
            className="nr-input num"
            type="number"
            min={50}
            max={95}
            value={pct}
            onChange={(e) => setPct(Math.min(95, Math.max(50, Number(e.target.value) || 50)))}
          />
        </div>
        <p className="mt-2 text-sm" role="status" aria-live="polite" data-testid="alert-preview">
          {!settledProfile
            ? 'Upišite OIB ili opis da vidite koliko bi natječaja danas stiglo.'
            : preview.isFetching
              ? 'Računam…'
              : preview.isError
                ? 'Pregled trenutno nije dostupan.'
                : preview.data
                  ? `S ovim postavkama danas bi dobili ${preview.data.count} ${preview.data.count === 1 ? 'natječaj' : 'natječaja'}.`
                  : ''}
        </p>
      </div>

      <details className="mt-4 nb-card">
        <summary className="cursor-pointer font-bold">
          Filteri (neobavezno)
          {counties.length + divisions.length + (minValue ? 1 : 0) > 0 ? (
            <span className="nb-pill ml-2">
              {counties.length + divisions.length + (minValue ? 1 : 0)}
            </span>
          ) : null}
        </summary>
        <fieldset className="mt-3 border-0 p-0">
          <legend className="font-bold">Županije naručitelja</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {countyList.data?.map((c) => (
              <label key={c.code} className="nb-pill cursor-pointer">
                <input
                  type="checkbox"
                  checked={counties.includes(c.code)}
                  onChange={() => setCounties((l) => toggle(l, c.code))}
                />
                {c.name.replace(' županija', '')}
              </label>
            ))}
          </div>
        </fieldset>
        <fieldset className="mt-4 border-0 p-0">
          <legend className="font-bold">CPV područja s otvorenim natječajima</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {highlights.data?.top_cpv_areas.map((a) => (
              <label key={a.division} className="nb-pill cursor-pointer">
                <input
                  type="checkbox"
                  checked={divisions.includes(a.division)}
                  onChange={() => setDivisions((l) => toggle(l, a.division))}
                />
                <span className="num">{a.division}</span> {a.label ?? ''}
              </label>
            ))}
          </div>
        </fieldset>
        <div className="mt-4 max-w-xs">
          <label htmlFor={`${id}-v`} className="block font-bold">
            Najmanja procijenjena vrijednost (EUR)
          </label>
          <input
            id={`${id}-v`}
            className="nr-input num mt-1"
            inputMode="numeric"
            value={minValue}
            onChange={(e) => setMinValue(e.target.value.replace(/\D/g, '').slice(0, 11))}
          />
        </div>
      </details>

      <fieldset className="mt-4 border-0 p-0">
        <legend className="font-bold">Učestalost</legend>
        <div className="mt-2 flex flex-wrap gap-3">
          {(
            [
              ['daily', 'Odmah (jednom dnevno, u 7:00)'],
              ['weekly', 'Tjedni pregled (ponedjeljkom u 7:00)'],
            ] as const
          ).map(([value, label]) => (
            <label key={value} className="nb-pill cursor-pointer">
              <input
                type="radio"
                name={`${id}-f`}
                checked={frequency === value}
                onChange={() => setFrequency(value)}
              />
              {label}
            </label>
          ))}
        </div>
      </fieldset>

      <div className="mt-4 flex items-start gap-2">
        <input
          id={`${id}-c`}
          type="checkbox"
          checked={consent}
          onChange={(e) => setConsent(e.target.checked)}
          className="mt-1 h-5 w-5"
        />
        <label htmlFor={`${id}-c`} className="text-sm" data-testid="consent-text">
          {consentText}
        </label>
      </div>
      <button
        type="submit"
        className="nb-btn mt-5"
        disabled={!emailOk || !hasProfile || !oibOk || !consent || state.kind === 'busy'}
      >
        Pošalji mi relevantne natječaje
      </button>
      <p role="status" aria-live="polite" className="mt-3 font-bold" data-state={state.kind}>
        {state.text}
      </p>
    </form>
  );
}
