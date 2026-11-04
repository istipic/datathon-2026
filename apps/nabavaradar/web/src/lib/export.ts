import type { MatchItem } from './types';

// ------------------------------------------------------------------------------ calendar (.ics)

const pad = (n: number) => String(n).padStart(2, '0');

/** UTC timestamp in iCalendar form: 20261120T080000Z. */
export function icsStamp(d: Date): string {
  return `${d.getUTCFullYear()}${pad(d.getUTCMonth() + 1)}${pad(d.getUTCDate())}T${pad(d.getUTCHours())}${pad(d.getUTCMinutes())}${pad(d.getUTCSeconds())}Z`;
}

/** Escape text values (RFC 5545 section 3.3.11). */
export const icsEscape = (s: string) =>
  s.replace(/\\/g, '\\\\').replace(/;/g, '\\;').replace(/,/g, '\\,').replace(/\r?\n/g, '\\n');

/** Fold content lines to 75 octets, continuation lines start with a space (RFC 5545 section 3.1). */
export function icsFold(line: string): string {
  const enc = new TextEncoder();
  if (enc.encode(line).length <= 75) return line;
  const out: string[] = [];
  let cur = '';
  for (const ch of line) {
    const limit = out.length === 0 ? 75 : 74;
    if (enc.encode(cur + ch).length > limit) {
      out.push(cur);
      cur = ch;
    } else {
      cur += ch;
    }
  }
  out.push(cur);
  return out.join('\r\n ');
}

export interface DeadlineEvent {
  pub_no: string;
  title: string | null;
  buyer: string | null;
  deadline: string | null;
  url_html: string | null;
}

/** An all-notice "rok za ponude" calendar entry (30 minutes, reminder one day before), or null. */
export function buildIcs(ev: DeadlineEvent, now = new Date()): string | null {
  if (!ev.deadline) return null;
  const end = new Date(ev.deadline);
  if (Number.isNaN(end.getTime())) return null;
  const start = new Date(end.getTime() - 30 * 60_000);
  const lines = [
    'BEGIN:VCALENDAR',
    'VERSION:2.0',
    'PRODID:-//Birokratko//rok za ponude//HR',
    'CALSCALE:GREGORIAN',
    'METHOD:PUBLISH',
    'BEGIN:VEVENT',
    `UID:${ev.pub_no}@birokratko`,
    `DTSTAMP:${icsStamp(now)}`,
    `DTSTART:${icsStamp(start)}`,
    `DTEND:${icsStamp(end)}`,
    `SUMMARY:${icsEscape(`Rok za ponude: ${ev.title ?? ev.pub_no}`)}`,
    `DESCRIPTION:${icsEscape(`${ev.buyer ?? 'Naručitelj nije naveden'}. Obavijest ${ev.pub_no}.`)}`,
    ...(ev.url_html ? [`URL:${ev.url_html}`] : []),
    'BEGIN:VALARM',
    'ACTION:DISPLAY',
    'DESCRIPTION:Sutra istječe rok za ponude',
    'TRIGGER:-P1D',
    'END:VALARM',
    'END:VEVENT',
    'END:VCALENDAR',
  ];
  return `${lines.map(icsFold).join('\r\n')}\r\n`;
}

// ------------------------------------------------------------------------------ CSV

const BOM = '\uFEFF';

/** One CSV field: quoted when it contains a separator, quote or newline; formula starters are neutralised. */
export function csvField(value: string | number | null | undefined): string {
  if (value === null || value === undefined) return '';
  let s = String(value);
  if (/^[=+\-@\t\r]/.test(s) && typeof value === 'string') s = `'${s}`; // spreadsheet formula injection
  return /[";\r\n]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s;
}

export const CSV_HEADER = [
  'Prilagodba (%)',
  'Naslov',
  'Naručitelj',
  'Županija',
  'Rok',
  'Vrijednost (EUR)',
  'Obavijest',
  'Poveznica',
];

/** The result list as CSV: semicolon separated (Croatian Excel), UTF-8 with BOM so č ć š ž đ show correctly. */
export function toCsv(items: MatchItem[]): string {
  const rows = items.map((i) =>
    [
      Math.round(i.fit * 100),
      i.title,
      i.buyer,
      i.county,
      i.deadline ? i.deadline.slice(0, 10) : '',
      i.value_eur,
      i.pub_no,
      i.url_html,
    ]
      .map(csvField)
      .join(';'),
  );
  return `${BOM}${[CSV_HEADER.map(csvField).join(';'), ...rows].join('\r\n')}\r\n`;
}

/** Offer ``content`` as a download (no network, nothing leaves the browser). */
export function download(filename: string, content: string, mime: string): void {
  const blob = new Blob([content], { type: `${mime};charset=utf-8` });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
