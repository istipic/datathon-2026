import { ErrorState, LoadingSkeleton } from '@dt/ui';
import { useQuery } from '@tanstack/react-query';
import { ApiError, api } from '../lib/api';
import { formatDate, formatPercent } from '../lib/format';

export function MethodologyPage() {
  const v = useQuery({
    queryKey: ['validation'],
    queryFn: ({ signal }) => api.validation(signal),
    retry: (n, err) => !(err instanceof ApiError && err.status === 404) && n < 1,
  });
  return (
    <div className="mx-auto max-w-4xl p-4">
      <h1 className="text-2xl font-semibold">Metodologija</h1>

      <h2 className="mt-6 text-xl font-semibold">Ocjena prilagodbe</h2>
      <p className="mt-2">
        Za svaki otvoreni natječaj računamo{' '}
        <strong className="num">prilagodbu = 0,55·S + 0,25·C + 0,10·G + 0,10·T</strong> (svaka
        sastavnica je od 0 do 1).
      </p>
      <ul className="mt-2 list-disc pl-5">
        <li>
          <strong>S – sličnost opisa (55 %).</strong> Najveća sličnost (kosinus višejezičnih
          embeddinga <span className="num">multilingual-e5-small</span>) između bilo koje od do 10
          djelatnosti tvrtke i teksta natječaja (naslov, prvih 1500 znakova opisa, nazivi CPV
          kodova). Skalira se na 0–1 između 5. i 95. percentila svih takvih sličnosti.
        </li>
        <li>
          <strong>C – CPV područje (25 %).</strong> 1,0 ako je CPV odjeljak natječaja među 3, a 0,5
          ako je među 10 odjeljaka koji su najbliži djelatnostima tvrtke (povezivanje NKD→CPV iz
          sličnosti naziva djelatnosti i tekstova prošlih obavijesti).
        </li>
        <li>
          <strong>G – lokacija (10 %).</strong> 1,0 ista županija (NUTS3), 0,5 ista regija (NUTS2)
          ili nepoznato, 0,2 drugdje.
        </li>
        <li>
          <strong>T – vrijeme (10 %).</strong> 1,0 ako do roka ima 15 ili više dana, linearno do 0
          na 3 dana; istekli natječaji se izostavljaju; natječaj bez roka dobiva 0,5.
        </li>
      </ul>

      <h2 className="mt-6 text-xl font-semibold">Konkurencija</h2>
      <p className="mt-2">
        Iz obavijesti o dodjeli (36 mjeseci) po CPV skupini (3 znamenke) i NUTS2 regiji: broj
        dodjela n, medijan broja zaprimljenih ponuda i udio dodjela s jednom ponudom. Oznaka „Niska
        konkurencija“ postavlja se kad je udio jedne ponude najmanje 40 % na najmanje 10 dodjela; n
        se prikazuje uvijek.
      </p>

      <h2 className="mt-6 text-xl font-semibold">Tržišno sondiranje</h2>
      <p className="mt-2">
        Sposobni dobavljači su aktivne tvrtke s barem jednom djelatnošću čija je sličnost CPV
        odjeljku najmanje τ, brojane po županijama. Prag τ odabran je na validacijskom skupu
        maksimizacijom mjere F1. Preporuke su deterministička pravila s navedenim izvorima.
      </p>

      <h2 className="mt-6 text-xl font-semibold">Validacija (uživo)</h2>
      {v.isLoading ? <LoadingSkeleton lines={3} label="Učitavam rezultate validacije…" /> : null}
      {v.error instanceof ApiError && v.error.status === 404 ? (
        <p className="mt-2">Validacija još nije provedena.</p>
      ) : v.error ? (
        <ErrorState message={(v.error as Error).message} onRetry={() => void v.refetch()} />
      ) : null}
      {v.data ? (
        <>
          <p className="mt-2">
            Provjerili smo bi li se stvarni natječaj pobjednika našao među prvih 10 / 20 natječaja
            tog mjeseca. Razdoblje:{' '}
            <span className="num">
              {v.data.window.first_month} – {v.data.window.last_month}
            </span>
            , n = <span className="num">{v.data.n}</span> parova pobjednik–natječaj.{' '}
            {v.data.mode_note}
          </p>
          <div className="dt-table-wrap mt-3">
            <table className="nr-table">
              <caption className="dt-sr-only">Recall stvarnih pobjednika</caption>
              <thead>
                <tr>
                  <th scope="col">Metoda</th>
                  <th scope="col" className="num">
                    recall@10
                  </th>
                  <th scope="col" className="num">
                    recall@20
                  </th>
                </tr>
              </thead>
              <tbody>
                <tr>
                  <th scope="row">NabavaRadar (S/C/G/T)</th>
                  <td className="num">{formatPercent(v.data.fit['recall@10'], 1)}</td>
                  <td className="num">{formatPercent(v.data.fit['recall@20'], 1)}</td>
                </tr>
                <tr>
                  <th scope="row">Osnovna: Postgres full-text</th>
                  <td className="num">{formatPercent(v.data.fts_baseline['recall@10'], 1)}</td>
                  <td className="num">{formatPercent(v.data.fts_baseline['recall@20'], 1)}</td>
                </tr>
                <tr>
                  <th scope="row">Slučajan poredak</th>
                  <td className="num">{formatPercent(v.data.random_baseline['recall@10'], 1)}</td>
                  <td className="num">{formatPercent(v.data.random_baseline['recall@20'], 1)}</td>
                </tr>
              </tbody>
            </table>
          </div>
          <p className="mt-2 text-sm text-neutral-700">
            Izračunato {formatDate(v.data.computed_at)}. Tvrtke bez NKD djelatnosti računaju se kao
            promašaj ({v.data.n_without_activities} od {v.data.n}).
            {v.data.tau.tau !== null ? (
              <>
                {' '}
                Prag τ = <span className="num">{v.data.tau.tau}</span> (F1 ={' '}
                <span className="num">{v.data.tau.f1}</span>).
              </>
            ) : null}
          </p>
        </>
      ) : null}

      <h2 className="mt-6 text-xl font-semibold">Ograničenja</h2>
      <ul className="mt-2 list-disc pl-5">
        <li>
          Podaci o tvrtkama potječu iz snimke Sudskog registra navedene na stranici{' '}
          <em>Izvori podataka</em>; mogu biti stariji od stvarnog stanja.
        </li>
        <li>
          Prikazuju se samo djelatnosti s NKD šifrom; slobodni tekst predmeta poslovanja se ne
          pohranjuje.
        </li>
        <li>
          Statistika konkurencije potječe iz obavijesti o dodjeli koje sadrže broj ponuda; starije
          obavijesti ga nemaju.
        </li>
        <li>
          Trgovci pojedinci, tvrtke u stečaju i likvidaciji te fizičke osobe se ne pohranjuju niti
          prikazuju.
        </li>
        <li>
          Detaljan izvještaj: <code>apps/nabavaradar/docs/validation.md</code> (generira ga naredba{' '}
          <code>nabavaradar eval</code>).
        </li>
      </ul>
    </div>
  );
}
