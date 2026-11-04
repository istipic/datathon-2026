import { EmptyState, ErrorState, LoadingSkeleton } from '@dt/ui';
import { useQuery } from '@tanstack/react-query';
import { useEffect, useId, useState } from 'react';
import { Link } from 'react-router-dom';
import { api } from '../lib/api';
import { fmtInt } from '../lib/format';

/** Municipality / city finder (any of the 556): results link to the planner view. */
export function MunicipalitySearch() {
  const id = useId();
  const [text, setText] = useState('');
  const [debounced, setDebounced] = useState('');
  useEffect(() => {
    const t = setTimeout(() => setDebounced(text.trim().length >= 2 ? text.trim() : ''), 300);
    return () => clearTimeout(t);
  }, [text]);
  const q = useQuery({
    queryKey: ['municipalities', debounced],
    queryFn: ({ signal }) => api.municipalities(debounced, signal),
    enabled: debounced.length >= 2,
    retry: false,
  });
  return (
    <div>
      <label htmlFor={`${id}-q`} className="mb-1 block text-sm font-bold">
        Naziv općine ili grada
      </label>
      <input
        id={`${id}-q`}
        type="search"
        value={text}
        onChange={(e) => setText(e.target.value)}
        placeholder="npr. Karlovac"
        maxLength={80}
        autoComplete="off"
        className="w-full min-h-[52px] rounded-lg border-2 border-neutral-700 bg-white px-4 py-2 text-lg"
      />
      <div aria-live="polite" className="mt-3">
        {q.isFetching ? <LoadingSkeleton lines={2} label="Tražim…" /> : null}
        {q.isError ? (
          <ErrorState
            message={q.error instanceof Error ? q.error.message : 'Pretraga nije uspjela.'}
            onRetry={() => void q.refetch()}
          />
        ) : null}
        {q.isSuccess && q.data.results.length === 0 ? (
          <EmptyState
            title="Nema rezultata"
            body="Provjerite pravopis naziva (npr. „Karlovac”, „Zagreb”, „Split”)."
          />
        ) : null}
        {q.isSuccess && q.data.results.length > 0 ? (
          <ul className="ot-card m-0 list-none divide-y divide-neutral-200 overflow-hidden p-0">
            {q.data.results.map((m) => (
              <li key={m.lau_id}>
                <Link
                  to={`/opcina/${m.lau_id}`}
                  className="flex min-h-[48px] flex-wrap items-center justify-between gap-2 px-4 py-3 hover:bg-neutral-100"
                >
                  <span className="font-bold">{m.name}</span>
                  <span className="text-sm text-neutral-700">
                    {fmtInt(m.pop_total)} stanovnika
                    {m.demo
                      ? ' · unaprijed izračunato'
                      : m.status === 'ready'
                        ? ' · izračunato'
                        : ''}
                  </span>
                </Link>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </div>
  );
}
