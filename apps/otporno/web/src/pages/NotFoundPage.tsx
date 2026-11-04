import { EmptyState } from '@dt/ui';
import { Link } from 'react-router-dom';

export function NotFoundPage() {
  return (
    <EmptyState
      title="Stranica nije pronađena"
      body="Adresa koju tražite ne postoji."
      action={
        <Link to="/" className="ot-btn mt-3">
          Natrag na početnu
        </Link>
      }
    />
  );
}
