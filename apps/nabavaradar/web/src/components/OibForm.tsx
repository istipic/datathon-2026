import { useId, useState } from 'react';
import { oibStatus } from '../lib/oib';

export interface OibFormProps {
  onSubmit: (oib: string) => void;
  initial?: string;
  /** light text on a dark hero background */
  onDark?: boolean;
}

/** OIB input with inline checksum validation; submit is possible only for a valid OIB. */
export function OibForm({ onSubmit, initial = '', onDark = false }: OibFormProps) {
  const [value, setValue] = useState(initial);
  const id = useId();
  const hintId = `${id}-hint`;
  const { status, message } = oibStatus(value);
  const valid = status === 'valid';

  return (
    <form
      noValidate
      onSubmit={(e) => {
        e.preventDefault();
        if (valid) onSubmit(value.trim());
      }}
    >
      <label htmlFor={id} className="block font-semibold">
        OIB vaše tvrtke
      </label>
      <div className="mt-2 flex flex-wrap gap-3">
        <input
          id={id}
          className="nr-input num"
          style={{ maxWidth: '18rem' }}
          inputMode="numeric"
          autoComplete="off"
          maxLength={11}
          placeholder="11 znamenki"
          value={value}
          aria-invalid={status === 'invalid'}
          aria-describedby={hintId}
          onChange={(e) => setValue(e.target.value.replace(/\s/g, ''))}
        />
        <button type="submit" className="nr-btn" style={onDark ? { background: 'rgb(var(--white))', color: 'rgb(var(--brand-700))', borderColor: 'rgb(var(--white))' } : undefined} disabled={!valid}>
          Pronađi natječaje
        </button>
      </div>
      <p id={hintId} role="status" aria-live="polite" className="mt-2 min-h-[1.5rem] text-sm">
        {status === 'invalid' ? '✕ ' : status === 'valid' ? '✓ ' : ''}
        {message || 'Unesite OIB: kontrolna znamenka provjerava se odmah, bez slanja podataka.'}
      </p>
    </form>
  );
}
