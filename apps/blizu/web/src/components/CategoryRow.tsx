import { FreshnessChip, SourceBadge, type SourceSummary } from '@dt/ui';
import { useState } from 'react';
import { TIER_LABEL, formatMinutes } from '../lib/labels';
import type { CategoryResult, Grade } from '../lib/types';
import { CategoryIcon } from './CategoryIcon';

interface TileProps {
  result: CategoryResult;
  onSelect: (result: CategoryResult) => void;
  /** Letter of the category score on the API's A–E scale (omitted until `/scoring` arrives). */
  grade?: Grade | null;
  selected?: boolean;
}

export function minutesText(r: CategoryResult): string {
  if (!r.has_data) return 'nema podataka';
  if (r.minutes === null) return '> 50 min';
  return formatMinutes(r.minutes);
}

/** One category as a tile: icon, label, big tabular minutes and a grade chip; tapping shows it on the map. */
export function CategoryRow({ result, onSelect, grade, selected }: TileProps) {
  const irrelevant = result.weight === 0;
  const text = minutesText(result);
  const numeric = result.has_data && result.minutes !== null;
  return (
    <li className="min-w-0" data-category={result.category}>
      <button
        type="button"
        className={irrelevant ? 'na-tile na-tile--muted w-full' : 'na-tile w-full'}
        onClick={() => onSelect(result)}
        disabled={!result.nearest}
        aria-pressed={selected ?? false}
      >
        <span className="na-muted">
          <CategoryIcon category={result.category} size={20} />
        </span>
        <span className="na-tile__label">{result.label}</span>
        <span className="na-tile__value dt-num" data-testid={`minutes-${result.category}`}>
          {numeric ? (
            <>
              {Math.round(result.minutes ?? 0)} <span className="na-tile__unit">min</span>
            </>
          ) : (
            <span className="text-sm font-medium">{text}</span>
          )}
        </span>
        {grade && numeric ? (
          <span className="na-tile__grade na-grade" data-grade={grade} aria-hidden="true">
            {grade}
          </span>
        ) : null}
        {result.nearest ? (
          <span className="dt-sr-only">{result.nearest.name}. Prikaži na karti.</span>
        ) : (
          <span className="dt-sr-only">Nema objekta u dometu od 4 km hoda</span>
        )}
        <span className="dt-sr-only">
          Ocjena {Math.round(result.score * 100)} %
          {irrelevant ? ' · ne ulazi u indeks za ovu osobu' : ''}
        </span>
      </button>
    </li>
  );
}

interface DetailProps {
  result: CategoryResult;
  source: SourceSummary | undefined;
}

/** Details of the selected category: nearest facility, score, weight and the source on demand. */
export function CategoryDetail({ result, source }: DetailProps) {
  const [open, setOpen] = useState(false);
  const irrelevant = result.weight === 0;
  const percent = Math.round(result.score * 100);
  return (
    <div
      className="na-tile-surface p-3 text-sm"
      data-testid={`detail-${result.category}`}
      aria-live="polite"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="font-semibold">
            {result.label}
            <span className="na-muted dt-num"> · {minutesText(result)}</span>
          </p>
          <p className="na-muted mt-0.5">
            {result.nearest ? result.nearest.name : 'Nema objekta u dometu od 4 km hoda'}
            {result.nearest?.address ? ` · ${result.nearest.address}` : ''}
          </p>
          <p className="na-muted mt-1 text-xs">
            Ocjena {percent} %{irrelevant ? ' · ne ulazi u indeks za ovu osobu' : ''}
            {!irrelevant ? (
              <span className="dt-num"> · težina {Math.round(result.weight * 100)} %</span>
            ) : null}
          </p>
        </div>
        <button
          type="button"
          className="na-chip blizu-row-source-toggle"
          aria-expanded={open}
          onClick={() => setOpen((v) => !v)}
          aria-label={`Izvor podataka: ${result.label}`}
        >
          Izvor
        </button>
      </div>
      <div
        className={open ? 'mt-2 border-t border-white/10 pt-2' : 'hidden'}
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
                <span className="na-muted">Razina: {TIER_LABEL[result.tier] ?? result.tier}</span>
              ) : null}
            </div>
          </>
        ) : (
          <span className="na-muted">Izvor nije poznat.</span>
        )}
      </div>
    </div>
  );
}
