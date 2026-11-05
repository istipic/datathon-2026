import { EmptyState, ErrorState, LoadingSkeleton } from '@dt/ui';
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';
import { AccessCard } from '../components/AccessCard';
import { AddressSearch, resultLabel } from '../components/AddressSearch';
import { PersonaControl } from '../components/PersonaControl';
import { ApiError, api } from '../lib/api';
import { isPersona } from '../lib/labels';
import type { GeocodeItem, PersonaId } from '../lib/types';

function signed(n: number | null, unit = ''): string {
  if (n === null) return '–';
  const rounded = Math.round(n * 10) / 10;
  return `${rounded > 0 ? '+' : ''}${String(rounded).replace('.', ',')}${unit}`;
}

/** Two addresses side by side with per-category differences. */
export function ComparePage() {
  const [params, setParams] = useSearchParams();
  const a = params.get('a');
  const b = params.get('b');
  const personaParam = params.get('persona');
  const persona: PersonaId = isPersona(personaParam) ? personaParam : 'opce';

  const query = useQuery({
    queryKey: ['compare', a, b, persona],
    queryFn: () => api.compare(a as string, b as string, persona),
    enabled: Boolean(a && b),
    retry: false,
  });

  function update(changes: Record<string, string>) {
    const copy = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes)) copy.set(k, v);
    setParams(copy, { replace: true });
  }
  const pick = (key: 'a' | 'b') => (item: GeocodeItem) =>
    update({
      [key]: `${item.lat.toFixed(6)},${item.lon.toFixed(6)}`,
      [`${key}q`]: resultLabel(item),
    });

  return (
    <div className="na-wrap">
      <h1 className="mb-4 text-2xl font-semibold text-neutral-900">Usporedi dvije adrese</h1>
      <div className="mb-6 grid gap-4 na-card p-5 md:grid-cols-2">
        <AddressSearch
          label="Adresa A"
          initialValue={params.get('aq') ?? ''}
          onSelect={pick('a')}
        />
        <AddressSearch
          label="Adresa B"
          initialValue={params.get('bq') ?? ''}
          onSelect={pick('b')}
        />
        <div className="md:col-span-2">
          <PersonaControl value={persona} onChange={(p) => update({ persona: p })} />
        </div>
      </div>

      {!a || !b ? (
        <EmptyState
          title="Odaberite obje adrese"
          body="Kad odaberete adresu A i adresu B, ovdje se prikazuje usporedba."
        />
      ) : query.isPending ? (
        <LoadingSkeleton lines={8} label="Uspoređujem adrese…" />
      ) : query.isError ? (
        <ErrorState
          message={
            query.error instanceof ApiError ? query.error.message : 'Usporedba nije uspjela.'
          }
          onRetry={() => void query.refetch()}
        />
      ) : (
        <>
          <section aria-labelledby="diff-title" className="mb-6 na-card p-5">
            <h2 id="diff-title" className="mb-2 text-lg font-semibold">
              Razlika (B u odnosu na A)
            </h2>
            <p className="mb-3">
              Blizu indeks:{' '}
              <strong className="dt-num">
                {query.data.a.index ?? '–'} → {query.data.b.index ?? '–'}
              </strong>{' '}
              ({signed(query.data.index_diff)} bodova)
            </p>
            <div className="dt-table-wrap">
              <table className="dt-table">
                <caption className="dt-sr-only">Razlika u minutama hoda po kategoriji</caption>
                <thead>
                  <tr>
                    <th scope="col">Kategorija</th>
                    <th scope="col">A</th>
                    <th scope="col">B</th>
                    <th scope="col">Razlika (min)</th>
                  </tr>
                </thead>
                <tbody>
                  {query.data.differences.map((d, i) => {
                    const ca = query.data.a.categories[i];
                    const cb = query.data.b.categories[i];
                    const better = d.minutes_diff !== null && d.minutes_diff < 0;
                    return (
                      <tr key={d.category}>
                        <th scope="row">{d.label}</th>
                        <td className="dt-num">{ca?.minutes ?? '–'}</td>
                        <td className="dt-num">{cb?.minutes ?? '–'}</td>
                        <td className="dt-num">
                          {signed(d.minutes_diff)}
                          {d.minutes_diff === null || d.minutes_diff === 0
                            ? ''
                            : better
                              ? ' ▼ bliže'
                              : ' ▲ dalje'}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </section>
          <div className="grid gap-6 lg:grid-cols-2">
            <AccessCard
              title={`A: ${params.get('aq') ?? a}`}
              result={query.data.a}
              persona={persona}
              compact
            />
            <AccessCard
              title={`B: ${params.get('bq') ?? b}`}
              result={query.data.b}
              persona={persona}
              compact
            />
          </div>
        </>
      )}
      <p className="mt-6">
        <Link className="underline" to="/">
          Natrag na početnu
        </Link>
      </p>
    </div>
  );
}
