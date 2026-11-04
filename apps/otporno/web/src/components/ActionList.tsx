import { useEffect, useState } from 'react';
import type { ActionItem } from '../lib/types';

interface Props {
  /** Groups are stable keys for the remembered ticks. */
  groups: { key: string; title: string; items: ActionItem[] }[];
  storageKey: string;
}

function loadTicks(key: string): Set<string> {
  try {
    const raw = window.localStorage.getItem(key);
    return new Set(raw ? (JSON.parse(raw) as string[]) : []);
  } catch {
    return new Set();
  }
}

/** "Što učiniti" checklist: every step names the public page it rests on. Ticks stay in this browser only. */
export function ActionList({ groups, storageKey }: Props) {
  const [ticks, setTicks] = useState<Set<string>>(() => new Set());
  useEffect(() => setTicks(loadTicks(storageKey)), [storageKey]);

  function toggle(id: string) {
    setTicks((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      try {
        window.localStorage.setItem(storageKey, JSON.stringify([...next]));
      } catch {
        /* storage unavailable: ticks are kept for this visit only */
      }
      return next;
    });
  }

  return (
    <div className="grid gap-6">
      {groups
        .filter((g) => g.items.length > 0)
        .map((g) => (
          <section key={g.key} aria-labelledby={`act-${g.key}`}>
            <h3 id={`act-${g.key}`} className="ot-display text-lg">
              {g.title}
            </h3>
            <ul className="mt-3 grid list-none gap-4 p-0">
              {g.items.map((a) => (
                <li key={a.id} className="ot-check">
                  <input
                    type="checkbox"
                    id={`chk-${a.id}`}
                    checked={ticks.has(a.id)}
                    onChange={() => toggle(a.id)}
                  />
                  <div>
                    <label htmlFor={`chk-${a.id}`} className="ot-check-text block text-base">
                      {a.text}
                    </label>
                    <p className="mt-1 text-sm text-neutral-700">
                      Izvor:{' '}
                      <a
                        className="underline"
                        href={a.source_url}
                        target="_blank"
                        rel="noopener noreferrer"
                      >
                        {a.source_title}
                      </a>
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          </section>
        ))}
    </div>
  );
}
