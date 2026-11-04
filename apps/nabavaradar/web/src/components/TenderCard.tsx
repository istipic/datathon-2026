import { Link } from 'react-router-dom';
import { buildIcs, download } from '../lib/export';
import { explain } from '../lib/explain';
import { formatDate, formatEur, urgency } from '../lib/format';
import type { MatchItem } from '../lib/types';
import { CompetitionChip } from './CompetitionChip';
import { ComponentBars, FitBar } from './FitBars';

/** "Rok za 3 dana": text and glyph always carry the meaning, the yellow is only a highlight. */
export function DeadlineBadge({ daysLeft }: { daysLeft: number | null }) {
  const level = urgency(daysLeft);
  const glyph = level === 'urgent' ? '⚠' : level === 'soon' ? '⏳' : '◷';
  const highlight = level === 'urgent' || level === 'soon' ? 'nb-pill nb-pill--alert' : 'nb-pill';
  return (
    <span className={highlight} data-urgency={level}>
      <span aria-hidden="true">{glyph}</span>
      {daysLeft === null
        ? 'Rok nije naveden'
        : `Rok za ${Math.max(0, Math.floor(daysLeft))} ${Math.floor(daysLeft) === 1 ? 'dan' : 'dana'}`}
    </span>
  );
}

export interface TenderCardProps {
  item: MatchItem;
  saved?: boolean;
  onToggleSave?: (item: MatchItem) => void;
  onHide?: (item: MatchItem) => void;
  /** Mockup / read-only use: no actions row. */
  compact?: boolean;
  /** Heading level of the title (h3 inside a list under an h2, h2 right below the page h1). */
  headingLevel?: 'h2' | 'h3';
}

/** One ranked tender: fit, title, buyer, deadline, value, competition, expandable "Zašto?" and actions. */
export function TenderCard({
  item,
  saved = false,
  onToggleSave,
  onHide,
  compact,
  headingLevel: Heading = 'h3',
}: TenderCardProps) {
  const others = item.group?.others ?? [];
  return (
    <li className="nr-card" data-testid="tender-card" data-pub-no={item.pub_no}>
      <FitBar fit={item.fit} />
      <Heading className="mt-3 text-xl">
        <Link to={`/natjecaj/${item.pub_no}`} className="underline decoration-2 underline-offset-2">
          {item.title ?? `Obavijest ${item.pub_no}`}
        </Link>
      </Heading>
      <div className="nr-meta mt-1">
        <span>{item.buyer ?? 'Naručitelj nije naveden'}</span>
        {item.county ? <span>{item.county}</span> : null}
        <span className="num">Vrijednost: {formatEur(item.value_eur)}</span>
        <span className="num">{item.pub_no}</span>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <DeadlineBadge daysLeft={item.days_left} />
        {item.deadline ? (
          <span className="nb-pill num">
            do {formatDate(item.deadline)}
            {item.deadline_kind === 'request' ? ' (zahtjevi za sudjelovanje)' : ''}
          </span>
        ) : null}
        <CompetitionChip competition={item.competition} />
        {item.group && item.group.size > 1 ? (
          <span className="nb-pill" data-testid="group-badge">
            +{item.group.size - 1} {item.group.size - 1 === 1 ? 'objava' : 'objave'} istog postupka
          </span>
        ) : null}
      </div>
      <details className="nr-why">
        <summary>Zašto?</summary>
        <ComponentBars components={item.components} />
        <ul className="mt-3 list-disc pl-5 text-sm">
          {explain(item).map((e) => (
            <li key={e.key}>
              <strong>{e.key}:</strong> {e.text}
            </li>
          ))}
        </ul>
        <p className="mt-3 text-sm">
          {item.url_html ? (
            <a href={item.url_html} target="_blank" rel="noopener noreferrer" className="underline">
              Otvori obavijest na TED-u
            </a>
          ) : null}
        </p>
      </details>
      {others.length > 0 ? (
        <details className="nr-why">
          <summary>Ostale objave istog postupka ({others.length})</summary>
          <ul className="mt-2 grid gap-1 text-sm">
            {others.map((o) => (
              <li key={o.pub_no}>
                <Link to={`/natjecaj/${o.pub_no}`} className="underline">
                  <span className="num">{o.pub_no}</span>
                </Link>{' '}
                · objavljeno <span className="num">{formatDate(o.pub_date)}</span> · prilagodba{' '}
                <span className="num">{Math.round(o.fit * 100)} %</span>
              </li>
            ))}
          </ul>
        </details>
      ) : null}
      {compact ? null : (
        <div className="nr-no-print mt-4 flex flex-wrap gap-2">
          {onToggleSave ? (
            <button
              type="button"
              className="nb-btn nb-btn--light nb-btn--sm"
              aria-pressed={saved}
              onClick={() => onToggleSave(item)}
            >
              <span aria-hidden="true">{saved ? '★' : '☆'}</span> {saved ? 'Pratim' : 'Prati'}
            </button>
          ) : null}
          {item.deadline ? (
            <button
              type="button"
              className="nb-btn nb-btn--light nb-btn--sm"
              onClick={() => {
                const ics = buildIcs(item);
                if (ics) download(`rok-${item.pub_no}.ics`, ics, 'text/calendar');
              }}
            >
              Dodaj rok u kalendar
            </button>
          ) : null}
          {onHide ? (
            <button
              type="button"
              className="nb-btn nb-btn--light nb-btn--sm"
              onClick={() => onHide(item)}
              title="Sakrij ovaj natječaj i smanji rang sličnih"
            >
              Ne zanima me
            </button>
          ) : null}
        </div>
      )}
    </li>
  );
}
