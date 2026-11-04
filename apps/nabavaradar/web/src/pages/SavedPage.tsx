import { EmptyState } from '@dt/ui';
import { Link } from 'react-router-dom';
import { buildIcs, download } from '../lib/export';
import { formatDate, formatEur } from '../lib/format';
import { SAVED_KEY, useStored, type SavedTender } from '../lib/storage';

/** `/spremljeno`: tenders marked "Prati". Kept only in this browser (localStorage), no account. */
export function SavedPage() {
  const [saved, setSaved] = useStored<SavedTender[]>(SAVED_KEY, []);
  return (
    <div className="nb-wrap py-10">
      <h1 className="nb-h2">Spremljeni natječaji</h1>
      <p className="mt-2">
        Popis se čuva samo u ovom pregledniku; nije povezan ni s kakvim računom.
      </p>
      {saved.length === 0 ? (
        <div className="mt-6">
          <EmptyState
            title="Još nema spremljenih natječaja"
            body="Na kartici natječaja kliknite „Prati” da ga dodate ovdje."
            action={
              <Link to="/" className="nb-btn nb-btn--sm mt-3">
                Pronađi natječaje
              </Link>
            }
          />
        </div>
      ) : (
        <ol className="mt-6 grid list-none gap-4 p-0" aria-label="Spremljeni natječaji">
          {saved.map((s) => (
            <li key={s.pub_no} className="nr-card" data-testid="saved-card">
              <h2 className="text-xl">
                <Link to={`/natjecaj/${s.pub_no}`} className="underline decoration-2">
                  {s.title ?? `Obavijest ${s.pub_no}`}
                </Link>
              </h2>
              <p className="nr-meta mt-1">
                <span>{s.buyer ?? 'Naručitelj nije naveden'}</span>
                {s.county ? <span>{s.county}</span> : null}
                <span className="num">Vrijednost: {formatEur(s.value_eur)}</span>
                <span className="num">Prilagodba pri spremanju: {Math.round(s.fit * 100)} %</span>
                <span className="num">Rok: {s.deadline ? formatDate(s.deadline) : '–'}</span>
              </p>
              <div className="mt-3 flex flex-wrap gap-2">
                {s.deadline ? (
                  <button
                    type="button"
                    className="nb-btn nb-btn--light nb-btn--sm"
                    onClick={() => {
                      const ics = buildIcs(s);
                      if (ics) download(`rok-${s.pub_no}.ics`, ics, 'text/calendar');
                    }}
                  >
                    Dodaj rok u kalendar
                  </button>
                ) : null}
                <button
                  type="button"
                  className="nb-btn nb-btn--light nb-btn--sm"
                  onClick={() => setSaved((l) => l.filter((x) => x.pub_no !== s.pub_no))}
                >
                  Ukloni
                </button>
              </div>
            </li>
          ))}
        </ol>
      )}
    </div>
  );
}
