import { ErrorState } from '@dt/ui';
import { useMutation } from '@tanstack/react-query';
import { Link, useSearchParams } from 'react-router-dom';

/** Target of the unsubscribe link in every digest e-mail; the click asks for confirmation first. */
export function UnsubscribePage() {
  const [params] = useSearchParams();
  const token = params.get('token') ?? '';
  const remove = useMutation({
    mutationFn: async () => {
      const res = await fetch(`/api/v1/subscriptions?token=${encodeURIComponent(token)}`, {
        method: 'DELETE',
      });
      const body = (await res.json()) as { detail?: string };
      if (!res.ok) throw new Error(body.detail ?? 'Odjava nije uspjela.');
      return body;
    },
  });
  return (
    <div className="mx-auto max-w-3xl p-4">
      <h1 className="text-2xl font-semibold">Odjava s tjednog pregleda</h1>
      {!token ? <ErrorState message="Poveznica nije potpuna (nedostaje token)." /> : null}
      {token && !remove.data ? (
        <>
          <p className="mt-3">Odjavom se briše vaša e-adresa iz NabavaRadara.</p>
          <button
            type="button"
            className="nr-btn mt-3"
            disabled={remove.isPending}
            onClick={() => remove.mutate()}
          >
            Otkaži pretplatu
          </button>
        </>
      ) : null}
      {remove.error ? <ErrorState message={(remove.error as Error).message} /> : null}
      {remove.data ? (
        <p className="mt-3" role="status">
          {remove.data.detail}
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
