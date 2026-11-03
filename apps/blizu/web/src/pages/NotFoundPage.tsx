import { EmptyState } from '@dt/ui';
import { Link } from 'react-router-dom';

export function NotFoundPage() {
  return (
    <EmptyState
      title="Stranica nije pronađena"
      body="Adresa koju tražite ne postoji."
      action={
        <Link className="dt-button" to="/">
          Natrag na početnu
        </Link>
      }
    />
  );
}
