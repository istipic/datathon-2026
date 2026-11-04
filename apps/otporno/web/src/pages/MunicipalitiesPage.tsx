import { Link } from 'react-router-dom';
import { MunicipalitySearch } from '../components/MunicipalitySearch';

export function MunicipalitiesPage() {
  return (
    <div className="grid max-w-3xl gap-5">
      <header>
        <p className="ot-eyebrow">Za općine i gradove</p>
        <h1 className="ot-display mt-1 text-2xl sm:text-3xl">Pregled izloženosti stanovništva</h1>
        <p className="mt-2 text-neutral-700">
          Odaberite općinu ili grad. Grad Karlovac i Grad Zagreb izračunati su unaprijed; za ostale
          se izračun pokreće na zahtjev i sprema.
        </p>
      </header>
      <div className="flex flex-wrap gap-3">
        <Link to="/opcina/HR_01791" className="ot-btn">
          Grad Karlovac
        </Link>
        <Link to="/opcina/HR_01333" className="ot-btn">
          Grad Zagreb
        </Link>
      </div>
      <div className="ot-card p-5">
        <MunicipalitySearch />
      </div>
    </div>
  );
}
