import { Link } from 'react-router-dom';
import { explain } from '../lib/explain';
import { countdown, formatDate, formatEur, urgency } from '../lib/format';
import type { MatchItem } from '../lib/types';
import { CompetitionChip } from './CompetitionChip';
import { ComponentBars, FitBar } from './FitBars';

const URGENCY_CHIP = {
  ok: ['dt-chip--neutral', '◷'],
  soon: ['dt-chip--warning', '⏳'],
  urgent: ['dt-chip--danger', '⚠'],
  unknown: ['dt-chip--neutral', '◷'],
} as const;

/** One ranked tender: fit, title, buyer, deadline, value, competition, expandable "Zašto?". */
export function TenderCard({ item }: { item: MatchItem }) {
  const [chip, glyph] = URGENCY_CHIP[urgency(item.days_left)];
  return (
    <li className="nr-card" data-testid="tender-card">
      <FitBar fit={item.fit} />
      <h3 className="mt-3 text-lg font-semibold">
        <Link to={`/natjecaj/${item.pub_no}`} className="text-brand-700 underline">
          {item.title ?? `Obavijest ${item.pub_no}`}
        </Link>
      </h3>
      <div className="nr-meta mt-1">
        <span>{item.buyer ?? 'Naručitelj nije naveden'}</span>
        {item.county ? <span>{item.county}</span> : null}
        <span className="num">Vrijednost: {formatEur(item.value_eur)}</span>
        <span className="num">{item.pub_no}</span>
      </div>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <span className={`dt-chip ${chip}`}>
          {glyph} {countdown(item.days_left)}
          {item.deadline ? <span className="num"> · do {formatDate(item.deadline)}</span> : null}
        </span>
        <CompetitionChip competition={item.competition} />
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
            <a
              href={item.url_html}
              target="_blank"
              rel="noopener noreferrer"
              className="text-brand-700 underline"
            >
              Otvori obavijest na TED-u
            </a>
          ) : null}
        </p>
      </details>
    </li>
  );
}
