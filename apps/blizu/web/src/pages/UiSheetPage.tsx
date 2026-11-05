import { ErrorState, EmptyState } from '@dt/ui';
import { useState } from 'react';
import { GradeBadge } from '../components/GradeBadge';
import { PersonaControl } from '../components/PersonaControl';
import { Button, Chip, Icon, LogoMark, type IconName } from '../components/ui';
import type { Grade, PersonaId } from '../lib/types';

const SWATCHES: [string, string][] = [
  ['--bg', '#07090D'],
  ['--surface-1', '#0D1117'],
  ['--surface-2', '#141A23'],
  ['--text', '#F3F5F8'],
  ['--text-muted', '#9AA4B2'],
  ['--accent', '#22D3EE'],
  ['--accent-2', '#A78BFA'],
  ['grade A', '#34D399'],
  ['grade B', '#A3E635'],
  ['grade C', '#FACC15'],
  ['grade D', '#FB923C'],
  ['grade E', '#F87171'],
];
const ICONS: IconName[] = ['arrow', 'search', 'pin', 'locate', 'layers', 'cube', 'play', 'replay'];

/** Dev-only component sheet (route /__ui): every state of every Night Atlas component on one page. */
export function UiSheetPage() {
  const [persona, setPersona] = useState<PersonaId>('starija');
  const [pressed, setPressed] = useState(true);
  return (
    <div className="na-wrap" style={{ display: 'grid', gap: '2rem' }}>
      <header className="flex items-center gap-3">
        <LogoMark size={40} />
        <div>
          <p className="na-overline">Night Atlas · sustav komponenti</p>
          <h1 className="na-display" style={{ fontSize: '2.25rem', margin: 0 }}>
            Što ti je <span className="na-gradient-text">blizu?</span>
          </h1>
        </div>
      </header>

      <section
        aria-label="Boje"
        className="grid gap-3"
        style={{ gridTemplateColumns: 'repeat(6, 1fr)' }}
      >
        {SWATCHES.map(([name, hex]) => (
          <div key={name} className="na-tile-surface p-2 text-xs">
            <div
              style={{
                height: 40,
                borderRadius: 8,
                background: hex,
                border: '1px solid var(--na-line)',
              }}
            />
            <p className="mt-2 font-semibold">{name}</p>
            <p className="na-muted dt-num">{hex}</p>
          </div>
        ))}
      </section>

      <section className="grid gap-4" style={{ gridTemplateColumns: '1fr 1fr' }}>
        <div className="na-glass grid gap-3 p-5">
          <p className="na-overline">Gumbi</p>
          <div className="flex flex-wrap gap-3">
            <Button arrow>Provjeri dostupnost</Button>
            <Button variant="ghost">Ghost</Button>
            <Button variant="accent">Vidi analizu</Button>
            <Button disabled>Onemogućeno</Button>
            <Button loading>Računam…</Button>
            <Button size="sm" variant="ghost">
              Mali
            </Button>
          </div>
          <p className="na-overline mt-2">Čipovi</p>
          <div className="flex flex-wrap gap-2">
            <Chip>Zagreb</Chip>
            <Chip warn>
              <Icon name="alert" size={14} /> Napomena
            </Chip>
            <button
              type="button"
              className="na-chip"
              aria-pressed={pressed}
              onClick={() => setPressed((v) => !v)}
            >
              5 min
            </button>
            <button
              type="button"
              className="na-chip"
              aria-pressed={!pressed}
              onClick={() => setPressed((v) => !v)}
            >
              10 min
            </button>
          </div>
          <p className="na-overline mt-2">Ikone</p>
          <div className="flex flex-wrap gap-3">
            {ICONS.map((i) => (
              <span key={i} className="na-iconbtn" title={i}>
                <Icon name={i} />
              </span>
            ))}
          </div>
        </div>

        <div className="na-glass grid gap-3 p-5">
          <p className="na-overline">Persona</p>
          <PersonaControl value={persona} onChange={setPersona} />
          <p className="na-overline mt-2">Polje za adresu</p>
          <span className="relative block">
            <input className="na-input" placeholder="npr. Ilica 50" aria-label="Primjer polja" />
            <span
              className="na-muted"
              style={{ position: 'absolute', left: 14, top: '50%', transform: 'translateY(-50%)' }}
            >
              <Icon name="search" />
            </span>
          </span>
          <p className="na-overline mt-2">Ocjene</p>
          <div className="flex items-center gap-4">
            {(['A', 'B', 'C', 'D', 'E'] as Grade[]).map((g) => (
              <GradeBadge key={g} grade={g} size={56} />
            ))}
          </div>
        </div>
      </section>

      <section className="grid gap-4" style={{ gridTemplateColumns: 'repeat(4, 1fr)' }}>
        {(['A', 'B', 'C', 'D'] as Grade[]).map((g, i) => (
          <button key={g} type="button" className="na-tile" aria-pressed={i === 0}>
            <span className="na-muted">
              <Icon name="pin" />
            </span>
            <span className="na-tile__label">Ljekarna</span>
            <span className="na-tile__value dt-num">
              {[3, 7, 12, 22][i]} <span className="na-tile__unit">min</span>
            </span>
            <span className="na-tile__grade na-grade" data-grade={g}>
              {g}
            </span>
          </button>
        ))}
      </section>

      <section className="grid gap-4" style={{ gridTemplateColumns: '1fr 1fr 1fr' }}>
        <div className="na-tile-surface p-4">
          <p className="na-overline">Skeleton</p>
          <div className="na-skel mt-3" style={{ height: 16 }} />
          <div className="na-skel mt-2" style={{ height: 16, width: '70%' }} />
          <div className="na-skel mt-2" style={{ height: 64 }} />
        </div>
        <EmptyState title="Nema rezultata" body="Primjer praznog stanja." />
        <ErrorState
          message="Primjer greške s mogućnošću ponovnog pokušaja."
          onRetry={() => undefined}
        />
      </section>

      <section
        aria-label="Kontrole karte"
        className="na-tile-surface p-4"
        style={{ position: 'relative', height: 220 }}
      >
        <p className="na-overline">Plutajuće kontrole karte</p>
        <div className="na-mapctl" style={{ position: 'absolute' }}>
          {(['plus', 'minus', 'locate', 'layers', 'cube'] as IconName[]).map((i) => (
            <button key={i} type="button" className="na-tip" data-tip={i} aria-label={i}>
              <Icon name={i} />
            </button>
          ))}
        </div>
        <div className="na-pillbar" style={{ left: 16, bottom: 16 }}>
          <button type="button" className="na-chip" aria-pressed="true">
            Doseg pješice
          </button>
          <button type="button" className="na-chip" aria-pressed="false">
            Put do…
          </button>
          <button type="button" className="na-chip" aria-pressed="false">
            3D
          </button>
        </div>
      </section>
    </div>
  );
}
