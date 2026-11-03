import { formatDateTime, toIso } from '../lib/format';

export interface SourceBadgeProps {
  publisher: string;
  title: string;
  url: string;
  /** When WE retrieved the data (ISO string or Date). Never omit it for externally loaded data. */
  retrievedAt: string | Date | null | undefined;
}

/** Attribution line: who published the data, a link to it, and when it was retrieved. */
export function SourceBadge({ publisher, title, url, retrievedAt }: SourceBadgeProps) {
  const formatted = formatDateTime(retrievedAt);
  return (
    <span className="dt-source">
      <span>
        Izvor: {publisher} –{' '}
        <a className="dt-link" href={url} target="_blank" rel="noopener noreferrer">
          {title}
        </a>
      </span>
      {formatted ? (
        <span>
          Dohvaćeno: <time dateTime={toIso(retrievedAt)}>{formatted}</time>
        </span>
      ) : (
        <span>Vrijeme dohvaćanja nije poznato</span>
      )}
    </span>
  );
}
