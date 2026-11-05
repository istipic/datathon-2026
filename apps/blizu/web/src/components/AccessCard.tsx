import { ConfidenceBadge } from '@dt/ui';
import { useState } from 'react';
import { useSources } from '../lib/useSources';
import { gradeOfScore, useScoring } from '../lib/useScoring';
import { formatDateTimeHr } from '../lib/dates';
import { PERSONA_LABEL } from '../lib/labels';
import type { AccessResult, CategoryId, CategoryResult, PersonaId } from '../lib/types';
import { CategoryDetail, CategoryRow } from './CategoryRow';
import { GradeBadge } from './GradeBadge';
import { PersonaControl } from './PersonaControl';

interface Props {
  title: string;
  result: AccessResult;
  persona: PersonaId;
  onPersona?: (persona: PersonaId) => void;
  onSelectCategory?: (category: CategoryResult) => void;
  /** Controlled selection (the map scenes follow it); falls back to internal state. */
  selectedCategory?: CategoryId | null;
  busy?: boolean;
  compact?: boolean;
  /** Hide the title (the results panel shows the address in its own header). */
  hideTitle?: boolean;
}

/** Score card, nine category tiles, warnings and data note for one address. */
export function AccessCard({
  title,
  result,
  persona,
  onPersona,
  onSelectCategory,
  selectedCategory,
  busy,
  compact,
  hideTitle,
}: Props) {
  const { byId } = useSources();
  const scoring = useScoring();
  const [localSelected, setLocalSelected] = useState<CategoryId | null>(null);
  const selectedId = selectedCategory === undefined ? localSelected : selectedCategory;
  const selected = result.categories.find((c) => c.category === selectedId);
  const usedSources = [
    ...new Set(
      result.categories.map((c) => c.nearest?.source_id).filter((s): s is string => Boolean(s)),
    ),
  ];

  return (
    <article
      aria-labelledby="card-title"
      aria-busy={busy ? 'true' : 'false'}
      className="blizu-card grid gap-4"
    >
      <h1
        id="card-title"
        className={hideTitle ? 'dt-sr-only' : 'text-xl'}
        style={{ margin: 0, overflowWrap: 'anywhere' }}
      >
        {title}
      </h1>

      <section className="na-tile-surface flex items-center gap-4 p-4" aria-label="Ukupna ocjena">
        <GradeBadge grade={result.grade} size={compact ? 76 : 84} />
        <div className="min-w-0">
          <p className="na-overline">Dostupnost usluga</p>
          <p
            className="dt-num mt-1 text-3xl font-bold leading-none tracking-tight"
            data-testid="index"
          >
            {result.index ?? '–'}
            <span className="na-muted text-base font-medium"> / 100</span>
          </p>
          <p className="na-muted mt-1 text-xs">Blizu indeks · {PERSONA_LABEL[persona]}</p>
          {result.confidence ? (
            <div className="mt-2">
              <ConfidenceBadge level={result.confidence.label} />
            </div>
          ) : null}
        </div>
      </section>

      {onPersona ? <PersonaControl value={persona} onChange={onPersona} compact /> : null}

      {result.warnings.length > 0 ? (
        <div
          role="status"
          aria-live="polite"
          className="rounded-xl border border-warning-border/40 bg-warning-bg p-3 text-sm text-warning-fg"
        >
          <p className="mb-1 font-semibold">Napomene</p>
          <ul className="list-disc pl-5">
            {result.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <ul
        className="m-0 grid list-none grid-cols-3 gap-2 p-0"
        aria-label="Kategorije usluga"
        data-testid="category-grid"
      >
        {result.categories.map((c) => (
          <CategoryRow
            key={c.category}
            result={c}
            grade={gradeOfScore(c.score, scoring.data?.grades)}
            selected={c.category === selectedId}
            onSelect={(r) => {
              setLocalSelected(r.category);
              onSelectCategory?.(r);
            }}
          />
        ))}
      </ul>

      {selected ? (
        <CategoryDetail
          result={selected}
          source={selected.nearest ? byId.get(selected.nearest.source_id) : undefined}
        />
      ) : null}

      <p className="na-muted text-xs leading-relaxed" data-testid="data-note">
        Vrijeme hoda računa se po pješačkoj mreži OpenStreetMapa (© OpenStreetMap contributors), a
        adresa je udaljena {Math.round(result.snapped_distance_m)} m od najbliže staze. Izračunato:{' '}
        {formatDateTimeHr(result.computed_at)}.{' '}
        {usedSources.length > 0 ? (
          <>
            Izvori:{' '}
            {usedSources
              .map((id) => {
                const s = byId.get(id);
                return s
                  ? `${s.publisher} (dohvaćeno ${formatDateTimeHr(s.retrieved_at) ?? 'nepoznato'})`
                  : id;
              })
              .join('; ')}
            .
          </>
        ) : null}{' '}
        <a href="/metodologija" className="underline">
          Metodologija
        </a>
      </p>
    </article>
  );
}
