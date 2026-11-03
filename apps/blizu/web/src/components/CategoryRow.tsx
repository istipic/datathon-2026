import { FreshnessChip, SourceBadge, type SourceSummary } from '@dt/ui';
import { useState } from 'react';
import { TIER_LABEL, formatMinutes } from '../lib/labels';
import type { CategoryResult } from '../lib/types';
import { CategoryIcon } from './CategoryIcon';

interface Props {
  result: CategoryResult;
  source: SourceSummary | undefined;
  onSelect: (result: CategoryResult) => void;
}

function minutesText(r: CategoryResult): string {
  if (!r.has_data) return 'nema podataka';
  if (r.minutes === null) return '> 50 min';
  return formatMinutes(r.minutes);
}

/** One category: icon, label, walking minutes (mono), score bar, nearest facility, source on demand. */
export function CategoryRow({ result, source, onSelect }: Props) {
  const [open, setOpen] = useState(false);
  const irrelevant = result.weight === 0;
  const percent = Math.round(result.score * 100);

  return (
    <li className="group relative border-b border-neutral-200 py-3" data-category={result.category}>
      <div className="flex items-start gap-3">
        <span className="mt-1 text-brand-700">
          <CategoryIcon category={result.category} />
        </span>
        <button
          type="button"
          className="min-h-[44px] flex-1 text-left"
          onClick={() => onSelect(result)}
          disabled={!result.nearest}
          aria-label={
            result.nearest
              ? `${result.label}: ${minutesText(result)}, ${result.nearest.name}. Prikaži na karti.`
              : `${result.label}: ${minutesText(result)}`
          }
        >
          <span className="flex items-baseline justify-between gap-3">
            <span className="text-base font-medium text-neutral-900">{result.label}</span>
            <span
              className="dt-num text-lg font-medium text-neutral-900"
              data-testid={`minutes-${result.category}`}
            >
              {minutesText(result)}
            </span>
          </span>
          <span className="block text-sm text-neutral-600">
            {result.nearest ? result.nearest.name : 'Nema objekta u dometu od 4 km hoda'}
            {result.nearest?.address ? ` · ${result.nearest.address}` : ''}
          </span>
          <span
            className="mt-2 block h-2 w-full overflow-hidden rounded-full bg-neutral-200"
            aria-hidden="true"
          >
            <span
              className="block h-full rounded-full bg-brand-600"
              style={{ width: `${percent}%`, opacity: irrelevant ? 0.35 : 1 }}
            />
          </span>
          <span className="mt-1 flex justify-between text-xs text-neutral-600">
            <span>
              Ocjena {percent} %{irrelevant ? ' · ne ulazi u indeks za ovu osobu' : ''}
            </span>
            {!irrelevant ? (
              <span className="dt-num">težina {Math.round(result.weight * 100)} %</span>
            ) : null}
          </span>
        </button>
        <button
          type="button"
          className="min-h-[44px] min-w-[44px] rounded-md px-2 text-sm text-brand-700 underline"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
          aria-label={`Izvor podataka: ${result.label}`}
        >
          Izvor
        </button>
      </div>
      <div
        className={[
          'ml-9 mt-2 rounded-md border border-neutral-300 bg-neutral-50 p-3 text-sm',
          open ? 'block' : 'hidden group-hover:block group-focus-within:block',
        ].join(' ')}
        data-testid={`source-${result.category}`}
      >
        {source ? (
          <>
            <SourceBadge
              publisher={source.publisher}
              title={source.title}
              url={source.url}
              retrievedAt={source.retrieved_at}
            />
            <div className="mt-2 flex flex-wrap items-center gap-2">
              <FreshnessChip days={result.freshness_days} />
              {result.tier ? (
                <span className="text-neutral-600">
                  Razina: {TIER_LABEL[result.tier] ?? result.tier}
                </span>
              ) : null}
            </div>
          </>
        ) : (
          <span className="text-neutral-600">Izvor nije poznat.</span>
        )}
      </div>
    </li>
  );
}
