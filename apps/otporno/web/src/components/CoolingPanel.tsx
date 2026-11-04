import { ErrorState } from '@dt/ui';
import { useMutation } from '@tanstack/react-query';
import { useId, useState } from 'react';
import { api } from '../lib/api';
import { fmtInt } from '../lib/format';
import type { CoolingResult } from '../lib/types';

interface Props {
  lau: string;
  onResult: (r: CoolingResult | null) => void;
  /** Lowest band offered first: "umjerena" when no cell of the municipality is in a high band. */
  defaultBand?: 'visoka' | 'umjerena' | 'niska';
}

const KIND: Record<string, string> = {
  library: 'knjižnica',
  school: 'škola',
  community_centre: 'društveni dom',
  social_facility: 'socijalna ustanova',
  townhall: 'gradska/općinska vijećnica',
};

/** Proposes k public buildings (1-5) that bring most 65+ residents of hot cells within a 10-minute walk. */
export function CoolingPanel({ lau, onResult, defaultBand = 'visoka' }: Props) {
  const id = useId();
  const [k, setK] = useState(3);
  const [band, setBand] = useState<'visoka' | 'umjerena' | 'niska'>(defaultBand);
  const mutation = useMutation({
    mutationFn: () => api.cooling(lau, k, band),
    onSuccess: (r) => onResult(r),
    onError: () => onResult(null),
  });
  const r = mutation.data;

  return (
    <section aria-labelledby={`${id}-h`} className="ot-card p-5">
      <h2 id={`${id}-h`} className="ot-display text-xl">
        Predloži centre za rashlađivanje
      </h2>
      <p className="mt-1 text-neutral-700">
        Od javnih zgrada (knjižnice, škole, društveni domovi, socijalne ustanove, vijećnice) biramo
        one koje pokrivaju najviše stanovnika 65+ u područjima s visokom vrućinom, unutar 10 minuta
        hoda.
      </p>
      <form
        className="mt-4 grid gap-4 sm:grid-cols-[auto_auto_1fr] sm:items-end"
        onSubmit={(e) => {
          e.preventDefault();
          mutation.mutate();
        }}
      >
        <div>
          <label htmlFor={`${id}-k`} className="block text-sm font-bold">
            Broj centara
          </label>
          <select
            id={`${id}-k`}
            value={k}
            onChange={(e) => setK(Number(e.target.value))}
            className="min-h-[44px] rounded-lg border-2 border-neutral-700 bg-white px-3"
          >
            {[1, 2, 3, 4, 5].map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </div>
        <div>
          <label htmlFor={`${id}-b`} className="block text-sm font-bold">
            Uključi ćelije s vrućinom
          </label>
          <select
            id={`${id}-b`}
            value={band}
            onChange={(e) => setBand(e.target.value as typeof band)}
            className="min-h-[44px] rounded-lg border-2 border-neutral-700 bg-white px-3"
          >
            <option value="visoka">visoka i vrlo visoka</option>
            <option value="umjerena">umjerena i više</option>
            <option value="niska">sve ćelije</option>
          </select>
        </div>
        <div>
          <button type="submit" className="ot-btn ot-btn--accent" disabled={mutation.isPending}>
            {mutation.isPending ? 'Računam…' : 'Predloži lokacije'}
          </button>
        </div>
      </form>
      <div aria-live="polite" className="mt-4">
        {mutation.isError ? (
          <ErrorState
            message={
              mutation.error instanceof Error ? mutation.error.message : 'Izračun nije uspio.'
            }
            onRetry={() => mutation.mutate()}
          />
        ) : null}
        {r ? (
          <div>
            <p className="text-lg font-bold">
              Pokriveno je <span className="ot-num">{fmtInt(r.covered_after)}</span> od{' '}
              <span className="ot-num">{fmtInt(r.demand_total)}</span> stanovnika 65+ u promatranim
              ćelijama
              {r.covered_before > 0 ? ` (prije: ${fmtInt(r.covered_before)})` : ''}.
            </p>
            <ol className="mt-3 grid list-decimal gap-2 pl-6">
              {r.sites.map((s) => (
                <li key={s.id}>
                  <strong>{s.name ?? 'Javna zgrada bez naziva'}</strong> ({KIND[s.kind] ?? s.kind}):{' '}
                  <span className="ot-num">+{fmtInt(s.newly_covered_65p)}</span> stanovnika 65+
                </li>
              ))}
            </ol>
            <p className="mt-3 text-sm text-neutral-700">{r.note}</p>
          </div>
        ) : null}
      </div>
    </section>
  );
}
