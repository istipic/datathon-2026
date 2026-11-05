import { useRef, type KeyboardEvent } from 'react';
import { PERSONAS } from '../lib/labels';
import type { PersonaId } from '../lib/types';
import { Icon, type IconName } from './ui';

interface Props {
  value: PersonaId;
  onChange: (persona: PersonaId) => void;
  /** Accessible name of the group. */
  label?: string;
  disabled?: boolean;
  /** Compact single-row variant (results panel, planner). */
  compact?: boolean;
}

const ICON: Record<PersonaId, IconName> = {
  opce: 'person',
  starija: 'elder',
  roditelj: 'parent',
  kolica: 'wheelchair',
};
/** Short uppercase labels of the segmented tiles (the full names stay in the accessible name). */
const SHORT: Record<PersonaId, string> = {
  opce: 'Opće',
  starija: 'Stariji',
  roditelj: 'Roditelj',
  kolica: 'Kolica',
};

/** Segmented control (radio group) with arrow-key navigation; the selected tile is solid white. */
export function PersonaControl({
  value,
  onChange,
  label = 'Za koga računamo',
  disabled,
  compact,
}: Props) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>, index: number) {
    const last = PERSONAS.length - 1;
    let next: number;
    if (event.key === 'ArrowRight' || event.key === 'ArrowDown')
      next = index === last ? 0 : index + 1;
    else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp')
      next = index === 0 ? last : index - 1;
    else if (event.key === 'Home') next = 0;
    else if (event.key === 'End') next = last;
    else return;
    event.preventDefault();
    const persona = PERSONAS[next];
    if (persona) {
      onChange(persona.id);
      refs.current[next]?.focus();
    }
  }

  return (
    <div role="radiogroup" aria-label={label} className={compact ? 'na-seg na-seg--sm' : 'na-seg'}>
      {PERSONAS.map((p, i) => {
        const checked = p.id === value;
        return (
          <button
            key={p.id}
            ref={(el) => {
              refs.current[i] = el;
            }}
            type="button"
            role="radio"
            aria-checked={checked}
            aria-label={p.label}
            tabIndex={checked ? 0 : -1}
            disabled={disabled}
            title={`${p.label}: ${p.hint}`}
            onClick={() => onChange(p.id)}
            onKeyDown={(e) => onKeyDown(e, i)}
            className="na-seg__item"
          >
            <Icon name={ICON[p.id]} size={compact ? 16 : 20} />
            <span aria-hidden="true">{SHORT[p.id]}</span>
          </button>
        );
      })}
    </div>
  );
}
