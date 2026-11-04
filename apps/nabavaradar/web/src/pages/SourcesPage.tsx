import { DataSourcesPage } from '@dt/ui';
import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';
import { formatDateTime, formatPercent } from '../lib/format';

/** "Izvori podataka" and "Provjera kvalitete": how well the ranking finds real winners (from the API). */
export function SourcesPage() {
  const v = useQuery({
    queryKey: ['validation'],
    staleTime: 5 * 60_000,
    retry: false,
    queryFn: ({ signal }) => api.validation(signal),
  });
  const d = v.data;
  return (
    <div className="nb-wrap py-10">
      <DataSourcesPage title="Izvori podataka" />
      <section className="mt-10" aria-labelledby="q-h">
        <h2 id="q-h" className="nb-h2">
          Provjera kvalitete
        </h2>
        {d ? (
          <>
            <p className="mt-3 max-w-3xl">
              Za tvrtke koje su stvarno dobile ugovor provjeravamo bi li se njihov natječaj našao
              među prvih 10 odnosno 20 natječaja tog mjeseca. Ispitano je{' '}
              <span className="num">{d.n.toLocaleString('hr-HR')}</span> parova pobjednik–natječaj,
              razdoblje {d.window.first_month}–{d.window.last_month}. Izračun:{' '}
              {formatDateTime(d.computed_at)}.
            </p>
            <div className="mt-4 overflow-x-auto">
              <table className="nr-table" data-testid="validation-table">
                <caption className="dt-sr-only">Udio pogođenih stvarnih natječaja</caption>
                <thead>
                  <tr>
                    <th scope="col">Metoda</th>
                    <th scope="col" className="num">
                      u prvih 10
                    </th>
                    <th scope="col" className="num">
                      u prvih 20
                    </th>
                  </tr>
                </thead>
                <tbody>
                  <tr>
                    <th scope="row">Birokratko (S/C/G/T)</th>
                    <td className="num">{formatPercent(d.fit['recall@10'], 1)}</td>
                    <td className="num">{formatPercent(d.fit['recall@20'], 1)}</td>
                  </tr>
                  <tr>
                    <th scope="row">Osnovna: pretraživanje teksta</th>
                    <td className="num">{formatPercent(d.fts_baseline['recall@10'], 1)}</td>
                    <td className="num">{formatPercent(d.fts_baseline['recall@20'], 1)}</td>
                  </tr>
                  <tr>
                    <th scope="row">Slučajan poredak</th>
                    <td className="num">{formatPercent(d.random_baseline['recall@10'], 1)}</td>
                    <td className="num">{formatPercent(d.random_baseline['recall@20'], 1)}</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <p className="mt-3 text-sm">
              Ograničenja: dio pobjednika nema upisanu NKD djelatnost pa se računa kao promašaj, a
              podaci o tvrtkama su iz testnog okruženja Sudskog registra. Rezultat pokazuje
              mogućnost rangiranja, ne da je tvrtka trebala pobijediti.
            </p>
          </>
        ) : (
          <p className="mt-3">
            {v.isLoading ? 'Učitavam…' : 'Rezultati provjere trenutno nisu dostupni.'}
          </p>
        )}
      </section>
    </div>
  );
}
