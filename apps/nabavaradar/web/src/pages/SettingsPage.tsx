import { ErrorState, LoadingSkeleton } from '@dt/ui';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useEffect, useId, useState } from 'react';
import { Link, useSearchParams } from 'react-router-dom';
import { ApiError, api } from '../lib/api';
import { useCounties } from '../lib/hooks';
import type { Frequency } from '../lib/types';

/** `/pretplata/postavke?token=…`: change threshold, filters and frequency, or pause the alerts. */
export function SettingsPage() {
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';
  const id = useId();
  const qc = useQueryClient();
  const counties = useCounties();
  const q = useQuery({
    queryKey: ['alert-settings', token],
    enabled: token.length > 0,
    retry: false,
    queryFn: ({ signal }) => api.alertSettings(token, signal),
  });
  const [pct, setPct] = useState(75);
  const [minValue, setMinValue] = useState('');
  const [sel, setSel] = useState<number[]>([]);
  const [frequency, setFrequency] = useState<Frequency>('daily');
  useEffect(() => {
    const s = q.data;
    if (!s) return;
    setPct(Math.round(s.min_fit * 100));
    setMinValue(s.min_value_eur === null ? '' : String(Math.round(s.min_value_eur)));
    setSel(s.counties);
    setFrequency(s.frequency);
  }, [q.data]);

  const save = useMutation({
    mutationFn: (extra: { paused?: boolean }) =>
      api.updateAlertSettings(token, {
        min_fit: pct / 100,
        counties: sel,
        frequency,
        ...(minValue ? { min_value_eur: Number(minValue) } : { clear_min_value: true }),
        ...extra,
      }),
    onSuccess: (data) => qc.setQueryData(['alert-settings', token], data),
  });

  return (
    <div className="nb-wrap py-10">
      <h1 className="nb-h2">Postavke upozorenja</h1>
      {!token ? <ErrorState message="Poveznica nije potpuna (nedostaje token)." /> : null}
      {q.isLoading ? <LoadingSkeleton lines={3} label="Učitavam postavke…" /> : null}
      {q.error ? (
        <ErrorState
          message={q.error instanceof ApiError ? q.error.message : 'Postavke nisu dostupne.'}
        />
      ) : null}
      {q.data ? (
        <div className="nb-card mt-6" style={{ maxWidth: '44rem' }}>
          <p>
            Adresa: <strong>{q.data.email}</strong> ·{' '}
            {q.data.paused ? 'obavijesti su pauzirane' : 'obavijesti su uključene'} · isključeno
            natječaja: <span className="num">{q.data.excluded}</span>
          </p>
          <label htmlFor={`${id}-t`} className="mt-4 block font-bold">
            Prag prilagodbe: <span className="num">{pct} %</span>
          </label>
          <input
            id={`${id}-t`}
            type="range"
            min={50}
            max={95}
            value={pct}
            onChange={(e) => setPct(Number(e.target.value))}
          />
          <label htmlFor={`${id}-v`} className="mt-4 block font-bold">
            Najmanja procijenjena vrijednost (EUR)
          </label>
          <input
            id={`${id}-v`}
            className="nr-input num mt-1"
            style={{ maxWidth: '16rem' }}
            inputMode="numeric"
            value={minValue}
            onChange={(e) => setMinValue(e.target.value.replace(/\D/g, '').slice(0, 11))}
          />
          <fieldset className="mt-4 border-0 p-0">
            <legend className="font-bold">Županije naručitelja (prazno = sve)</legend>
            <div className="mt-2 flex flex-wrap gap-2">
              {counties.data?.map((c) => (
                <label key={c.code} className="nb-pill cursor-pointer">
                  <input
                    type="checkbox"
                    checked={sel.includes(c.code)}
                    onChange={() =>
                      setSel((l) =>
                        l.includes(c.code) ? l.filter((x) => x !== c.code) : [...l, c.code],
                      )
                    }
                  />
                  {c.name.replace(' županija', '')}
                </label>
              ))}
            </div>
          </fieldset>
          <fieldset className="mt-4 border-0 p-0">
            <legend className="font-bold">Učestalost</legend>
            <div className="mt-2 flex flex-wrap gap-3">
              {(
                [
                  ['daily', 'Odmah (jednom dnevno)'],
                  ['weekly', 'Tjedni pregled'],
                ] as const
              ).map(([v, label]) => (
                <label key={v} className="nb-pill cursor-pointer">
                  <input
                    type="radio"
                    name={`${id}-f`}
                    checked={frequency === v}
                    onChange={() => setFrequency(v)}
                  />
                  {label}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="mt-6 flex flex-wrap gap-3">
            <button
              type="button"
              className="nb-btn nb-btn--sm"
              onClick={() => save.mutate({})}
              disabled={save.isPending}
            >
              Spremi postavke
            </button>
            <button
              type="button"
              className="nb-btn nb-btn--light nb-btn--sm"
              onClick={() => save.mutate({ paused: !q.data?.paused })}
              disabled={save.isPending}
            >
              {q.data.paused ? 'Nastavi obavijesti' : 'Pauziraj obavijesti'}
            </button>
          </div>
          <p role="status" aria-live="polite" className="mt-3 font-bold">
            {save.isSuccess ? 'Spremljeno.' : ''}
            {save.error instanceof ApiError ? save.error.message : ''}
          </p>
        </div>
      ) : null}
      <p className="mt-6">
        <Link to="/" className="underline">
          Početna
        </Link>
      </p>
    </div>
  );
}
