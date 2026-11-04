import { useNavigate, Link } from 'react-router-dom';
import { AddressSearch } from '../components/AddressSearch';
import { FlameIcon, SunIcon, WaveIcon } from '../components/icons';

const EXAMPLES = [
  { label: 'Karlovac, Trg bana Josipa Jelačića', lat: 45.4931, lon: 15.5557 },
  { label: 'Zagreb, Trg bana Jelačića', lat: 45.8131, lon: 15.9772 },
  { label: 'Dubrovnik, Stradun', lat: 42.6412, lon: 18.1105 },
];

export function HomePage() {
  const navigate = useNavigate();
  return (
    <div className="grid gap-8">
      <section className="ot-hero" aria-labelledby="home-h">
        <p className="ot-eyebrow">Putovnica rizika kućanstva</p>
        <h1
          id="home-h"
          className="ot-display mt-2 text-2xl sm:text-3xl"
          style={{ lineHeight: 1.1 }}
        >
          Koliko je vaša adresa izložena poplavi i vrućini, i što možete učiniti?
        </h1>
        <p className="mt-3 max-w-2xl text-lg">
          Upišite adresu bilo gdje u Hrvatskoj. Dobit ćete razinu rizika s izvorima i konkretne
          korake iz javnih uputa nadležnih službi.
        </p>
        <div className="mt-6 max-w-2xl">
          <AddressSearch
            onSelect={(item) =>
              navigate(
                `/putovnica?lat=${item.lat.toFixed(5)}&lon=${item.lon.toFixed(5)}&q=${encodeURIComponent(item.title)}`,
              )
            }
          />
        </div>
        <p className="mt-4 text-sm">
          Primjeri:{' '}
          {EXAMPLES.map((e, i) => (
            <span key={e.label}>
              {i > 0 ? ' · ' : ''}
              <Link
                to={`/putovnica?lat=${e.lat}&lon=${e.lon}&q=${encodeURIComponent(e.label)}`}
                className="font-bold text-white underline"
              >
                {e.label}
              </Link>
            </span>
          ))}
        </p>
      </section>

      <section aria-labelledby="home-what" className="grid gap-4 md:grid-cols-3">
        <h2 id="home-what" className="dt-sr-only">
          Što pokazujemo
        </h2>
        <article className="ot-ticket ot-ticket--flood">
          <WaveIcon />
          <h3 className="ot-display mt-2 text-lg">Poplava</h3>
          <p className="mt-1 text-neutral-700">
            Karte opasnosti od poplava Hrvatskih voda (2019.) za tri scenarija, prikazane uz vašu
            adresu.
          </p>
        </article>
        <article className="ot-ticket ot-ticket--heat">
          <SunIcon />
          <h3 className="ot-display mt-2 text-lg">Vrućina</h3>
          <p className="mt-1 text-neutral-700">
            Broj vrućih dana i tropskih noći danas (1991.–2020.) i u 2031.–2050., iz tri klimatska
            modela.
          </p>
        </article>
        <article className="ot-ticket ot-ticket--fire">
          <FlameIcon />
          <h3 className="ot-display mt-2 text-lg">Požar</h3>
          <p className="mt-1 text-neutral-700">
            Procjena opasnosti od požara otvorenog prostora u pripremi.
          </p>
        </article>
      </section>

      <section className="ot-card p-6" aria-labelledby="home-planner">
        <p className="ot-eyebrow">Za općine i gradove</p>
        <h2 id="home-planner" className="ot-display mt-1 text-xl">
          Tko je u vašoj općini najizloženiji?
        </h2>
        <p className="mt-2 max-w-3xl text-neutral-700">
          Za bilo koju od 556 općina i gradova prikazujemo koliko je stanovnika i osoba starijih od
          65 godina u područjima s visokim rizikom, kartu prioriteta i prijedlog lokacija centara za
          rashlađivanje.
        </p>
        <div className="mt-4 flex flex-wrap gap-3">
          <Link to="/opcina/HR_01791" className="ot-btn">
            Grad Karlovac
          </Link>
          <Link to="/opcina/HR_01333" className="ot-btn">
            Grad Zagreb
          </Link>
          <Link to="/opcina" className="ot-btn ot-btn--ghost">
            Druga općina ili grad
          </Link>
        </div>
      </section>
    </div>
  );
}
