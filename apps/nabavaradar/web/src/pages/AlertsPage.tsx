import { useSearchParams } from 'react-router-dom';
import { AlertForm } from '../components/AlertForm';

/** `/upozorenja`: the same sign-up as the dialog, as a page (also the target for shared links). */
export function AlertsPage() {
  const [params] = useSearchParams();
  const oib = params.get('oib') ?? undefined;
  return (
    <div className="nb-wrap py-10">
      <h1 className="nb-h2">Pošalji mi relevantne natječaje</h1>
      <p className="mt-3 max-w-2xl text-lg">
        Odredite prag prilagodbe i filtere. Kad se pojavi natječaj koji prijeđe prag, javimo se
        e-poštom. Svaki natječaj šaljemo samo jednom, a pretplata vrijedi tek nakon potvrde.
      </p>
      <div className="nb-card mt-6" style={{ maxWidth: '46rem' }}>
        <AlertForm oib={oib} />
      </div>
    </div>
  );
}
