import { EmptyState } from '@dt/ui';
import { Link } from 'react-router-dom';

export function NotFoundPage() {
  return (
    <div className="na-wrap" style={{ maxWidth: '42rem' }}>
      <EmptyState
        title="Stranica nije pronađena"
        body="Adresa koju tražite ne postoji."
        action={
          <Link className="na-btn" to="/">
            Natrag na početnu
          </Link>
        }
      />
    </div>
  );
}
