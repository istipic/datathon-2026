import { EmptyState } from '@dt/ui';
import { Link } from 'react-router-dom';

export function NotFoundPage() {
  return (
    <div className="nb-wrap py-10">
      <EmptyState
        title="Stranica nije pronađena"
        body="Adresa ne postoji ili je uklonjena."
        action={
          <Link to="/" className="underline">
            Natrag na početnu
          </Link>
        }
      />
    </div>
  );
}
