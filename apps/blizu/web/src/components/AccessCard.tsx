import { ConfidenceBadge } from '@dt/ui';
import { useSources } from '../lib/useSources';
import { formatDateTimeHr } from '../lib/dates';
import { PERSONA_LABEL } from '../lib/labels';
import type { AccessResult, CategoryResult, PersonaId } from '../lib/types';
import { CategoryRow } from './CategoryRow';
import { GradeBadge } from './GradeBadge';
import { PersonaControl } from './PersonaControl';

interface Props {
  title: string;
  result: AccessResult;
  persona: PersonaId;
  onPersona?: (persona: PersonaId) => void;
  onSelectCategory?: (category: CategoryResult) => void;
  busy?: boolean;
  compact?: boolean;
}

/** Grade, index, confidence, warnings and the nine category rows for one address. */
export function AccessCard({
  title,
  result,
  persona,
  onPersona,
  onSelectCategory,
  busy,
  compact,
}: Props) {
  const { byId } = useSources();
  const usedSources = [
    ...new Set(
      result.categories.map((c) => c.nearest?.source_id).filter((s): s is string => Boolean(s)),
    ),
  ];

  return (
    <article
      aria-labelledby="card-title"
      aria-busy={busy ? 'true' : 'false'}
      className="blizu-card"
    >
      <h1 id="card-title" className="mb-4 text-xl font-semibold text-neutral-900">
        {title}
      </h1>
      <div className="flex flex-wrap items-center gap-5">
        <GradeBadge grade={result.grade} size={compact ? 88 : 112} />
        <div>
          <p className="text-neutral-600">Blizu indeks · {PERSONA_LABEL[persona]}</p>
          <p className="dt-num text-3xl font-semibold text-neutral-900" data-testid="index">
            {result.index ?? '–'}
            <span className="text-lg text-neutral-600"> / 100</span>
          </p>
          {result.confidence ? (
            <div className="mt-1">
              <ConfidenceBadge level={result.confidence.label} />
            </div>
          ) : null}
        </div>
      </div>

      {onPersona ? (
        <div className="mt-5">
          <PersonaControl value={persona} onChange={onPersona} />
        </div>
      ) : null}

      {result.warnings.length > 0 ? (
        <div
          role="status"
          aria-live="polite"
          className="mt-4 rounded-lg border border-warning-border bg-warning-bg p-3 text-sm text-warning-fg"
        >
          <p className="mb-1 font-semibold">Napomene</p>
          <ul className="list-disc pl-5">
            {result.warnings.map((w) => (
              <li key={w}>{w}</li>
            ))}
          </ul>
        </div>
      ) : null}

      <ul className="mt-4" aria-label="Kategorije usluga">
        {result.categories.map((c) => (
          <CategoryRow
            key={c.category}
            result={c}
            source={c.nearest ? byId.get(c.nearest.source_id) : undefined}
            onSelect={onSelectCategory ?? (() => undefined)}
          />
        ))}
      </ul>

      <p className="mt-4 text-sm text-neutral-600" data-testid="data-note">
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
