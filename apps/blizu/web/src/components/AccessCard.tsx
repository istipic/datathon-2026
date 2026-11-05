import { ConfidenceBadge } from '@dt/ui';
import { useState } from 'react';
import { useSources } from '../lib/useSources';
import { gradeOfScore, useScoring } from '../lib/useScoring';
import { formatDateTimeHr } from '../lib/dates';
import { PERSONA_LABEL } from '../lib/labels';
import type { AccessResult, CategoryId, CategoryResult, PersonaId } from '../lib/types';
import { CategoryDetail, CategoryRow } from './CategoryRow';
import { GradeBadge } from './GradeBadge';
import { Icon } from './ui';
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
  const usedSources = [
    ...new Set(
      result.categories.map((c) => c.nearest?.source_id).filter((s): s is string => Boolean(s)),
    ),
  ];

  return (
    <article
      aria-labelledby="card-title"
      aria-busy={busy ? 'true' : 'false'}
      className="blizu-card na-place"
    >
      <h1
        id="card-title"
        className={hideTitle ? 'dt-sr-only' : 'na-place__title'}
        style={{ overflowWrap: 'anywhere' }}
      >
        {title}
      </h1>

      <section className="na-place__score" aria-label="Ukupna ocjena">
        <div className="min-w-0">
          <p className="na-place__index dt-num" data-testid="index">
            {result.index ?? '–'}
            <span className="na-place__of"> / 100</span>
          </p>
          <p className="na-place__caption">Dostupnost usluga pješice · {PERSONA_LABEL[persona]}</p>
          {result.confidence ? (
            <div className="mt-1">
              <ConfidenceBadge level={result.confidence.label} />
            </div>
          ) : null}
        </div>
        <GradeBadge grade={result.grade} size={compact ? 56 : 64} />
      </section>

      {onPersona ? <PersonaControl value={persona} onChange={onPersona} compact /> : null}

      {result.warnings.length > 0 ? (
        <div role="status" aria-live="polite" className="na-place__notes">
          <p className="na-place__notes-title">
            <Icon name="alert" size={16} /> Napomene
          </p>
          <ul>
            {result.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <section aria-labelledby="near-title" className="na-place__section">
        <h2 id="near-title" className="na-place__h">
          Najbliže usluge
        </h2>
        <ul className="na-rows" aria-label="Kategorije usluga" data-testid="category-grid">
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
            >
              {c.category === selectedId ? (
                <CategoryDetail
                  result={c}
                  source={c.nearest ? byId.get(c.nearest.source_id) : undefined}
                />
              ) : null}
            </CategoryRow>
          ))}
        </ul>
      </section>

      <p className="na-place__note" data-testid="data-note">
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
