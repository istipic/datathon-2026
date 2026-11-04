import { useId, useState } from 'react';
import { ApiError, api } from '../lib/api';

/** Consent shown next to the checkbox; the API stores the same text with the subscription. */
export const CONSENT_TEXT =
  'Pristajem da Birokratko na ovu e-adresu jednom tjedno (ponedjeljkom u 7:00) šalje pregled do 10 novih ' +
  'natječaja koji odgovaraju mojoj pretrazi. Pohranjuje se samo e-adresa. Pretplatu mogu otkazati ' +
  'poveznicom u svakoj poruci.';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

export interface SubscribeBoxProps {
  oib?: string;
  query?: string;
}

/** Weekly digest sign-up (double opt-in: a confirmation e-mail is sent first). */
export function SubscribeBox({ oib, query }: SubscribeBoxProps) {
  const id = useId();
  const [email, setEmail] = useState('');
  const [consent, setConsent] = useState(false);
  const [state, setState] = useState<{ kind: 'idle' | 'busy' | 'ok' | 'error'; text: string }>({
    kind: 'idle',
    text: '',
  });
  const validEmail = EMAIL_RE.test(email);

  return (
    <section aria-labelledby={`${id}-h`} className="nr-card nr-no-print">
      <h2 id={`${id}-h`} className="text-lg font-semibold">
        Tjedni pregled novih natječaja
      </h2>
      <form
        className="mt-3"
        noValidate
        onSubmit={async (e) => {
          e.preventDefault();
          if (!validEmail || !consent) return;
          setState({ kind: 'busy', text: 'Šaljem…' });
          try {
            const res = await api.subscribe({ email, oib, query, consent });
            setState({ kind: 'ok', text: res.detail });
          } catch (err) {
            setState({
              kind: 'error',
              text: err instanceof ApiError ? err.message : 'Pretplata nije uspjela.',
            });
          }
        }}
      >
        <label htmlFor={`${id}-e`} className="block font-semibold">
          E-adresa
        </label>
        <input
          id={`${id}-e`}
          type="email"
          className="nr-input mt-1"
          style={{ maxWidth: '24rem' }}
          autoComplete="email"
          value={email}
          aria-invalid={email !== '' && !validEmail}
          onChange={(e) => setEmail(e.target.value)}
        />
        <div className="mt-3 flex items-start gap-2">
          <input
            id={`${id}-c`}
            type="checkbox"
            checked={consent}
            onChange={(e) => setConsent(e.target.checked)}
            className="mt-1 h-5 w-5"
          />
          <label htmlFor={`${id}-c`} className="text-sm">
            {CONSENT_TEXT}
          </label>
        </div>
        <button
          type="submit"
          className="nr-btn mt-3"
          disabled={!validEmail || !consent || state.kind === 'busy'}
        >
          Pretplati me
        </button>
        <p role="status" aria-live="polite" className="mt-2 text-sm">
          {state.text}
        </p>
      </form>
    </section>
  );
}
