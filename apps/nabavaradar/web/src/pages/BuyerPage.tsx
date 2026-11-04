import { EmptyState, ErrorState, LoadingSkeleton } from '@dt/ui';
import { useMutation, useQuery } from '@tanstack/react-query';
import { useId, useMemo, useState } from 'react';
import { CountyMap } from '../components/CountyMap';
import { api } from '../lib/api';
import { formatDate, formatDateTime, formatNumber, formatPercent } from '../lib/format';
import { useCounties, useCountiesGeo } from '../lib/hooks';
import type { SoundingResult } from '../lib/types';

const MAX_TEXT = 2000;
const CPV_RE = /^(\d{8}(-\d)?|\d{2,8})$/;

function Results({ r }: { r: SoundingResult }) {
  const geo = useCountiesGeo();
  const values = useMemo(
    () => Object.fromEntries(r.suppliers_by_county.map((c) => [c.nuts3, c.count])),
    [r],
  );
  const comp = r.competition;
  const sorted = [...r.suppliers_by_county].sort((a, b) => b.count - a.count);
  return (
    <div className="mt-6 grid gap-6">
      <section aria-labelledby="cpv-h">
        <h2 id="cpv-h" className="text-2xl">
          Predloženi CPV kodovi
        </h2>
        <ul className="mt-2 grid gap-2">
          {r.cpv_suggestions.map((s) => (
            <li key={s.code} className="nr-card" style={{ padding: '8px 12px' }}>
              <span className="num font-semibold">{s.code}</span> {s.label}
              {s.similarity !== null ? (
                <span className="num text-neutral-700"> · sličnost {s.similarity.toFixed(2)}</span>
              ) : null}
            </li>
          ))}
        </ul>
        <p className="mt-2 text-sm text-neutral-700">
          Tržište se računa za CPV odjeljak <strong className="num">{r.division.code}</strong>
          {r.division.label ? ` „${r.division.label}“` : ''}.
        </p>
      </section>

      <section aria-labelledby="sup-h">
        <h2 id="sup-h" className="text-2xl">
          Sposobni dobavljači po županijama
        </h2>
        <p className="mt-1">
          Ukupno <strong className="num">{r.suppliers.total.toLocaleString('hr-HR')}</strong>{' '}
          aktivnih tvrtki (od{' '}
          <span className="num">{r.suppliers.companies_in_register.toLocaleString('hr-HR')}</span> u
          bazi) ima djelatnost čija je sličnost tom CPV području najmanje τ ={' '}
          <span className="num">{r.suppliers.tau}</span>
          {r.suppliers.tau_calibrated
            ? ' (prag odabran validacijom).'
            : ' (zadani prag: validacija još nije provedena).'}
          {r.suppliers.in_county !== null ? (
            <>
              {' '}
              U odabranoj županiji: <strong className="num">{r.suppliers.in_county}</strong>.
            </>
          ) : null}
        </p>
        <div className="mt-3 grid gap-4 lg:grid-cols-2">
          {geo.data ? (
            <CountyMap
              geo={geo.data}
              values={values}
              unit="dobavljača"
              label={`Karta sposobnih dobavljača po županijama, ukupno ${r.suppliers.total}`}
            />
          ) : geo.error ? (
            <ErrorState message="Karta županija nije dostupna." />
          ) : (
            <LoadingSkeleton lines={4} label="Učitavam kartu…" />
          )}
          <div className="dt-table-wrap">
            <table className="nr-table">
              <caption className="dt-sr-only">Broj sposobnih dobavljača po županijama</caption>
              <thead>
                <tr>
                  <th scope="col">Županija</th>
                  <th scope="col" className="num">
                    Dobavljača
                  </th>
                </tr>
              </thead>
              <tbody>
                {sorted.map((c) => (
                  <tr key={c.county_code}>
                    <td>{c.county}</td>
                    <td className="num">{c.count.toLocaleString('hr-HR')}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      <section aria-labelledby="comp-h">
        <h2 id="comp-h" className="text-2xl">
          Povijesna konkurencija
        </h2>
        {comp.n === 0 ? (
          <p className="mt-2">
            Za CPV skupinu {comp.cpv_group ?? '–'} nema dovoljno povijesnih dodjela (n = 0).
          </p>
        ) : (
          <div className="dt-table-wrap mt-2">
            <table className="nr-table">
              <caption className="dt-sr-only">Konkurencija za CPV skupinu {comp.cpv_group}</caption>
              <thead>
                <tr>
                  <th scope="col">Područje</th>
                  <th scope="col" className="num">
                    Dodjela (n)
                  </th>
                  <th scope="col" className="num">
                    Medijan ponuda
                  </th>
                  <th scope="col" className="num">
                    Samo jedna ponuda
                  </th>
                  <th scope="col">Oznaka</th>
                </tr>
              </thead>
              <tbody>
                {[comp, comp.scope !== 'HR' ? comp.national : null].filter(Boolean).map((c) => (
                  <tr key={String(c?.scope)}>
                    <td>{c?.scope === 'HR' ? 'cijela Hrvatska' : `regija ${c?.scope}`}</td>
                    <td className="num">{c?.n}</td>
                    <td className="num">{formatNumber(c?.median_submissions)}</td>
                    <td className="num">{formatPercent(c?.single_bid_share)}</td>
                    <td>{c?.flag ? '⚠ Niska konkurencija' : '–'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-2 text-sm text-neutral-700">
          CPV skupina <span className="num">{comp.cpv_group ?? '–'}</span>, dodjele{' '}
          {formatDate(comp.window_start)} – {formatDate(comp.window_end)}.
        </p>
      </section>

      <section aria-labelledby="adv-h">
        <h2 id="adv-h" className="text-2xl">
          Preporuke
        </h2>
        {r.advice.length === 0 ? (
          <p className="mt-2">
            Na temelju dostupnih podataka nema posebnih preporuka (nije zadovoljeno nijedno
            pravilo).
          </p>
        ) : (
          <ul className="mt-2 grid gap-3">
            {r.advice.map((a) => (
              <li key={a.rule} className="nr-card">
                <p>{a.text}</p>
                <p className="mt-2 text-sm">
                  Izvor:{' '}
                  <a
                    href={a.source_url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="underline"
                  >
                    {a.source_label}
                  </a>
                </p>
              </li>
            ))}
          </ul>
        )}
        <p className="mt-2 text-sm text-neutral-700">
          Preporuke su pravila temeljena na podacima, ne pravni savjet. Zakonski tekst se mijenja:
          provjerite važeću verziju.
        </p>
      </section>

      <p className="text-sm text-neutral-700">
        Izračunato {formatDateTime(r.generated_at)}. Registar: snimka{' '}
        {formatDate(r.data.sudreg_data_as_of)}, dohvaćeno{' '}
        {formatDateTime(r.data.sudreg_retrieved_at)}; TED dodjele dohvaćene{' '}
        {formatDateTime(r.data.ted_result_retrieved_at)}.
      </p>
    </div>
  );
}

export function BuyerPage() {
  const ids = useId();
  const [text, setText] = useState('');
  const [cpv, setCpv] = useState('');
  const [picker, setPicker] = useState('');
  const [county, setCounty] = useState('');
  const [formError, setFormError] = useState('');
  const counties = useCounties();
  const hits = useQuery({
    queryKey: ['cpv', picker],
    enabled: picker.trim().length >= 2,
    queryFn: ({ signal }) => api.cpvSearch(picker.trim(), signal),
  });
  const run = useMutation({
    mutationFn: (body: { text?: string; cpv?: string; county?: number }) => api.sounding(body),
  });

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const t = text.trim();
    const c = cpv.trim();
    if (!t && !c) return setFormError('Opišite nabavu ili odaberite CPV kod.');
    if (t && c) return setFormError('Navedite ili opis ili CPV kod, ne oboje.');
    if (c && !CPV_RE.test(c))
      return setFormError('CPV kod: 8 znamenki (npr. 45000000-7) ili prefiks od 2 do 8 znamenki.');
    setFormError('');
    run.mutate({
      text: t || undefined,
      cpv: c || undefined,
      county: county ? Number(county) : undefined,
    });
  };

  return (
    <div className="nb-wrap py-10">
      <h1 className="nb-h2">Provjera tržišta za javne naručitelje</h1>
      <p className="mt-2 max-w-3xl">
        Prije objave nabave procijenite koliko je sposobnih dobavljača u županiji i kakva je bila
        konkurencija u sličnim nabavama.
      </p>
      <form className="nr-card mt-4" onSubmit={submit} noValidate aria-label="Opis nabave">
        <label htmlFor={`${ids}-t`} className="block font-semibold">
          Opis predmeta nabave
        </label>
        <textarea
          id={`${ids}-t`}
          className="nr-input mt-1"
          rows={3}
          maxLength={MAX_TEXT}
          value={text}
          onChange={(e) => {
            setText(e.target.value);
            if (e.target.value) setCpv('');
          }}
          placeholder="npr. održavanje sustava videonadzora u školama"
        />
        <p className="text-sm text-neutral-700 num">
          {text.length} / {MAX_TEXT}
        </p>

        <fieldset className="mt-3">
          <legend className="font-semibold">ili odaberite CPV kod</legend>
          <label htmlFor={`${ids}-p`} className="dt-sr-only">
            Pretraži CPV po nazivu ili šifri
          </label>
          <input
            id={`${ids}-p`}
            className="nr-input mt-1"
            style={{ maxWidth: '28rem' }}
            value={picker}
            onChange={(e) => setPicker(e.target.value)}
            placeholder="pretraži po nazivu ili šifri, npr. 45 ili cestogradnja"
          />
          {hits.data && hits.data.length > 0 ? (
            <ul
              className="mt-2 max-h-56 overflow-auto rounded border border-neutral-300 bg-white"
              aria-label="Rezultati pretrage CPV-a"
            >
              {hits.data.map((h) => (
                <li key={h.code}>
                  <button
                    type="button"
                    className="w-full px-3 py-2 text-left hover:bg-neutral-100"
                    onClick={() => {
                      setCpv(`${h.code}${h.check_digit ? `-${h.check_digit}` : ''}`);
                      setText('');
                      setPicker('');
                    }}
                  >
                    <span className="num font-semibold">{h.code}</span> {h.label}
                  </button>
                </li>
              ))}
            </ul>
          ) : null}
          {cpv ? (
            <p className="mt-2 text-sm">
              Odabrano: <strong className="num">{cpv}</strong>{' '}
              <button type="button" className="underline" onClick={() => setCpv('')}>
                ukloni
              </button>
            </p>
          ) : null}
        </fieldset>

        <div className="mt-3">
          <label htmlFor={`${ids}-c`} className="block font-semibold">
            Županija naručitelja
          </label>
          <select
            id={`${ids}-c`}
            className="nr-input"
            style={{ maxWidth: '22rem' }}
            value={county}
            onChange={(e) => setCounty(e.target.value)}
          >
            <option value="">Nije odabrana</option>
            {counties.data?.map((c) => (
              <option key={c.code} value={c.code}>
                {c.name}
              </option>
            ))}
          </select>
        </div>
        <button type="submit" className="nr-btn mt-4" disabled={run.isPending}>
          Provjeri tržište
        </button>
        <p
          role="alert"
          className="mt-2 text-sm font-semibold"
          style={{ color: 'rgb(var(--danger-fg))' }}
        >
          {formError}
        </p>
      </form>

      {run.isPending ? <LoadingSkeleton lines={5} label="Računam tržište…" /> : null}
      {run.error ? (
        <div className="mt-4">
          <ErrorState message={(run.error as Error).message} onRetry={() => run.reset()} />
        </div>
      ) : null}
      {run.data ? <Results r={run.data} /> : null}
      {!run.data && !run.isPending && !run.error ? (
        <div className="mt-6">
          <EmptyState
            title="Još nema rezultata"
            body="Unesite opis nabave ili odaberite CPV kod pa pokrenite provjeru."
          />
        </div>
      ) : null}
    </div>
  );
}
