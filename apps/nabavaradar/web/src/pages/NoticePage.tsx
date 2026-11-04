import { EmptyState, ErrorState, LoadingSkeleton } from '@dt/ui';
import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { ApiError, api } from '../lib/api';
import {
  countdown,
  formatDate,
  formatDateTime,
  formatEur,
  formatNumber,
  formatPercent,
} from '../lib/format';

export function NoticePage() {
  const { pubNo = '' } = useParams();
  const q = useQuery({
    queryKey: ['notice', pubNo],
    queryFn: ({ signal }) => api.notice(pubNo, signal),
    retry: (n, err) => !(err instanceof ApiError && err.status < 500) && n < 1,
  });
  if (q.isLoading)
    return (
      <div className="mx-auto max-w-5xl p-4">
        <LoadingSkeleton lines={4} label="Učitavam obavijest…" />
      </div>
    );
  if (q.error) {
    return (
      <div className="mx-auto max-w-5xl p-4">
        {q.error instanceof ApiError && q.error.status === 404 ? (
          <EmptyState title="Obavijest nije pronađena" body={q.error.message} />
        ) : (
          <ErrorState message={(q.error as Error).message} onRetry={() => void q.refetch()} />
        )}
      </div>
    );
  }
  const n = q.data;
  if (!n) return null;
  const c = n.competition;
  const deadlineDays = n.deadline
    ? (new Date(n.deadline).getTime() - Date.now()) / 86_400_000
    : null;
  return (
    <div className="mx-auto max-w-5xl p-4">
      <p className="text-sm">
        <Link to="/" className="text-brand-700 underline">
          ← Početna
        </Link>
      </p>
      <h1 className="mt-2 text-2xl font-semibold">{n.title ?? `Obavijest ${n.pub_no}`}</h1>
      <p className="mt-1 text-neutral-600">
        {n.buyer ?? 'Naručitelj nije naveden'} · <span className="num">{n.pub_no}</span> ·{' '}
        {n.type === 'competition' ? 'Poziv na nadmetanje' : 'Obavijest o dodjeli ugovora'}
      </p>

      <dl className="nr-card mt-4 grid gap-x-6 gap-y-2 sm:grid-cols-2">
        <div>
          <dt className="text-sm text-neutral-600">Objavljeno</dt>
          <dd className="num">{formatDate(n.pub_date)}</dd>
        </div>
        {n.type === 'competition' ? (
          <div>
            <dt className="text-sm text-neutral-600">
              {n.deadline_kind === 'request' ? 'Rok za zahtjeve za sudjelovanje' : 'Rok za ponude'}
            </dt>
            <dd>
              <span className="num">{n.deadline ? formatDateTime(n.deadline) : '–'}</span> (
              {countdown(deadlineDays)})
            </dd>
          </div>
        ) : null}
        <div>
          <dt className="text-sm text-neutral-600">Procijenjena vrijednost</dt>
          <dd className="num">
            {formatEur(n.value_eur)}
            {n.currency && n.currency !== 'EUR' ? ` (${n.currency}, nije preračunato)` : ''}
          </dd>
        </div>
        <div>
          <dt className="text-sm text-neutral-600">Broj grupa (lotova)</dt>
          <dd className="num">{n.n_lots ?? '–'}</dd>
        </div>
        <div>
          <dt className="text-sm text-neutral-600">Lokacija naručitelja</dt>
          <dd className="num">{n.buyer_nuts ?? n.place_nuts ?? 'nepoznata'}</dd>
        </div>
        <div>
          <dt className="text-sm text-neutral-600">Glavni CPV</dt>
          <dd className="num">{n.cpv_main ?? '–'}</dd>
        </div>
      </dl>

      <p className="mt-4 flex flex-wrap gap-4">
        {n.url_html ? (
          <a
            href={n.url_html}
            target="_blank"
            rel="noopener noreferrer"
            className="text-brand-700 underline"
          >
            Otvori na TED-u (HTML)
          </a>
        ) : null}
        {n.url_pdf ? (
          <a
            href={n.url_pdf}
            target="_blank"
            rel="noopener noreferrer"
            className="text-brand-700 underline"
          >
            PDF
          </a>
        ) : null}
      </p>

      {n.description ? (
        <section className="mt-6" aria-labelledby="desc-h">
          <h2 id="desc-h" className="text-xl font-semibold">
            Opis
          </h2>
          <p className="mt-2 whitespace-pre-line">{n.description}</p>
        </section>
      ) : null}

      <section className="mt-6" aria-labelledby="comp-h">
        <h2 id="comp-h" className="text-xl font-semibold">
          Konkurencija u sličnim nabavama
        </h2>
        {c.n === 0 ? (
          <p className="mt-2">
            Nema dovoljno povijesnih dodjela za CPV skupinu {c.cpv_group ?? '–'}.
          </p>
        ) : (
          <div className="mt-2">
            <div className="dt-table-wrap">
              <table className="nr-table">
                <caption className="dt-sr-only">Konkurencija za CPV skupinu {c.cpv_group}</caption>
                <thead>
                  <tr>
                    <th scope="col">CPV skupina</th>
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
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <td className="num">{c.cpv_group}</td>
                    <td>{c.scope === 'HR' ? 'cijela Hrvatska' : `regija ${c.scope}`}</td>
                    <td className="num">{c.n}</td>
                    <td className="num">{formatNumber(c.median_submissions)}</td>
                    <td className="num">{formatPercent(c.single_bid_share)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="mt-2 text-sm">
              {c.flag ? '⚠ Niska konkurencija: ' : ''}
              Razdoblje {formatDate(c.window_start)} – {formatDate(c.window_end)}. Oznaka „niska
              konkurencija“ postavlja se kad je udio dodjela s jednom ponudom najmanje 40 % na
              najmanje 10 dodjela.
            </p>
          </div>
        )}
      </section>

      {n.awards.length > 0 ? (
        <section className="mt-6" aria-labelledby="aw-h">
          <h2 id="aw-h" className="text-xl font-semibold">
            Dodjele po grupama
          </h2>
          <div className="dt-table-wrap mt-2">
            <table className="nr-table">
              <caption className="dt-sr-only">Dodjele po grupama</caption>
              <thead>
                <tr>
                  <th scope="col">Grupa</th>
                  <th scope="col">Status</th>
                  <th scope="col">Pobjednik</th>
                  <th scope="col" className="num">
                    Ponuda zaprimljeno
                  </th>
                </tr>
              </thead>
              <tbody>
                {n.awards.map((a, i) => (
                  <tr key={`${a.lot_id}-${i}`}>
                    <td className="num">{a.lot_id}</td>
                    <td>
                      {a.lot_status === 'selec-w'
                        ? 'dodijeljeno'
                        : a.lot_status === 'clos-nw'
                          ? 'zatvoreno bez pobjednika'
                          : (a.lot_status ?? '–')}
                    </td>
                    <td>
                      {a.winner_oib ? (
                        <Link to={`/tvrtka/${a.winner_oib}`} className="text-brand-700 underline">
                          {a.winner}
                        </Link>
                      ) : (
                        '–'
                      )}
                    </td>
                    <td className="num">{a.received_submissions ?? '–'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-sm text-neutral-600">
            Pobjednici se imenuju samo kad su upisani u Sudski registar kao tvrtke.
          </p>
        </section>
      ) : null}
    </div>
  );
}
