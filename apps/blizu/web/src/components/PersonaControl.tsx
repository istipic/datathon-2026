import { useRef, type KeyboardEvent } from 'react';
import { PERSONAS } from '../lib/labels';
import type { PersonaId } from '../lib/types';

interface Props {
  value: PersonaId;
  onChange: (persona: PersonaId) => void;
  /** Accessible name of the group. */
  label?: string;
  disabled?: boolean;
}

/** Segmented control (radio group) with arrow-key navigation. */
export function PersonaControl({ value, onChange, label = 'Za koga računamo', disabled }: Props) {
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
    <div role="radiogroup" aria-label={label} className="flex flex-wrap gap-2">
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
            tabIndex={checked ? 0 : -1}
            disabled={disabled}
            title={p.hint}
            onClick={() => onChange(p.id)}
            onKeyDown={(e) => onKeyDown(e, i)}
            className={[
              'min-h-[44px] rounded-full border px-4 py-2 text-base font-medium transition-colors',
              checked
                ? 'border-brand-700 bg-brand-700 text-white'
                : 'border-neutral-400 bg-white text-neutral-900 hover:bg-neutral-100',
            ].join(' ')}
          >
            {checked ? <span aria-hidden="true">✓ </span> : null}
            {p.label}
          </button>
        );
      })}
    </div>
  );
}
