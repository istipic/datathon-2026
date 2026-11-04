import { ErrorState, LoadingSkeleton } from '@dt/ui';
import { useQuery } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';

/** Target of the link in the confirmation e-mail (double opt-in). */
export function ConfirmPage() {
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';
  const q = useQuery({
    queryKey: ['confirm', token],
    enabled: token.length > 0,
    retry: false,
    queryFn: async () => {
      const res = await fetch(`/api/v1/subscriptions/confirm?token=${encodeURIComponent(token)}`);
      const body = (await res.json()) as { detail?: string };
      if (!res.ok) throw new Error(body.detail ?? 'Potvrda nije uspjela.');
      return body;
    },
  });
  return (
    <div className="mx-auto max-w-3xl p-4">
      <h1 className="text-2xl font-semibold">Potvrda pretplate</h1>
      {!token ? <ErrorState message="Poveznica nije potpuna (nedostaje token)." /> : null}
      {q.isLoading ? <LoadingSkeleton lines={2} label="Potvrđujem pretplatu…" /> : null}
      {q.error ? <ErrorState message={(q.error as Error).message} /> : null}
      {q.data ? (
        <p className="mt-3" role="status">
          {q.data.detail ?? 'Pretplata je potvrđena.'}
        </p>
      ) : null}
      <p className="mt-4">
        <Link to="/" className="text-brand-700 underline">
          Početna
        </Link>
      </p>
    </div>
  );
}
