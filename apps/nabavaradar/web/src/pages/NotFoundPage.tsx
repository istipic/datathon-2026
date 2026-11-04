import { EmptyState } from '@dt/ui';
import { Link } from 'react-router-dom';

export function NotFoundPage() {
  return (
    <div className="mx-auto max-w-3xl p-4">
      <EmptyState
        title="Stranica nije pronađena"
        body="Adresa ne postoji ili je uklonjena."
        action={
          <Link to="/" className="text-brand-700 underline">
            Natrag na početnu
          </Link>
        }
      />
    </div>
  );
}
