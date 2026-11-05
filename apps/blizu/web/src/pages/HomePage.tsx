import { useState } from 'react';
import { Link, useNavigate, useSearchParams } from 'react-router-dom';
import { AddressSearch, resultLabel } from '../components/AddressSearch';
import { PersonaControl } from '../components/PersonaControl';
import { Button } from '../components/ui';
import { formatDateTimeHr } from '../lib/dates';
import { EXAMPLES } from '../lib/examples';
import { isPersona } from '../lib/labels';
import { useSources } from '../lib/useSources';
import type { GeocodeItem, PersonaId } from '../lib/types';

export function cardUrl(lat: number, lon: number, persona: PersonaId, label?: string): string {
  const params = new URLSearchParams({
    lat: lat.toFixed(6),
    lon: lon.toFixed(6),
    persona,
  });
  if (label) params.set('q', label);
  return `/kartica?${params.toString()}`;
}

export function HomePage() {
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const initial = params.get('persona');
  const [persona, setPersona] = useState<PersonaId>(isPersona(initial) ? initial : 'opce');
  const [chosen, setChosen] = useState<GeocodeItem | null>(null);
  const { data: sources } = useSources();

  function go(item: GeocodeItem) {
    navigate(cardUrl(item.lat, item.lon, persona, resultLabel(item)));
  }

  return (
    <div className="na-wrap">
      <section className="na-hero" aria-labelledby="hero-title">
        <p className="na-overline">Zagreb · pješice · otvoreni podaci</p>
        <h1 id="hero-title" className="na-display" style={{ margin: 0 }}>
          Što ti je <span className="na-gradient-text">blizu?</span>
        </h1>
        <p className="na-hero__sub">
          Upiši adresu u Zagrebu i vidi koliko minuta pješice je do liječnika, ljekarne, vrtića,
          škole, prijevoza, parka i trgovine, posebno za starije, roditelje i kolica.
        </p>

        <form
          className="na-glass na-hero__card"
          onSubmit={(e) => {
            e.preventDefault();
            if (chosen) go(chosen);
          }}
        >
          <AddressSearch onSelect={setChosen} autoFocus />
          <PersonaControl value={persona} onChange={setPersona} />
          <Button type="submit" arrow disabled={!chosen} className="w-full">
            Provjeri dostupnost
          </Button>
          {chosen ? null : (
            <p className="na-muted text-center text-xs" style={{ margin: 0 }}>
              Odaberi adresu s popisa prijedloga ili isprobaj primjer ispod.
            </p>
          )}
        </form>

        {EXAMPLES.length > 0 ? (
          <section aria-labelledby="examples-title" className="grid justify-items-center gap-2">
            <h2 id="examples-title" className="na-overline" style={{ margin: 0 }}>
              Isprobaj na primjeru
            </h2>
            <ul className="m-0 flex list-none flex-wrap justify-center gap-2 p-0">
              {EXAMPLES.map((example) => (
                <li key={example.query}>
                  <button
                    type="button"
                    className="na-chip"
                    style={{ minHeight: 40, cursor: 'pointer' }}
                    onClick={() =>
                      navigate(cardUrl(example.lat, example.lon, persona, example.label))
                    }
                  >
                    {example.label}
                  </button>
                </li>
              ))}
            </ul>
          </section>
        ) : null}
      </section>

      <section className="na-explainers" aria-label="O Blizu">
        <article className="na-card na-explainer">
          <p className="na-overline">Što mjerimo</p>
          <h2>Minute hoda, ne zračne linije</h2>
          <p>
            Za devet usluga računamo vrijeme hoda po stvarnoj pješačkoj mreži OpenStreetMapa, s
            brzinom hoda prilagođenom osobi. Kolica koriste graf bez stepenica.
          </p>
        </article>
        <article className="na-card na-explainer">
          <p className="na-overline">Odakle podaci</p>
          <h2>Otvoreni izvori s datumima</h2>
          {sources && sources.sources.length > 0 ? (
            <ul className="na-muted m-0 grid list-none gap-1 p-0 text-sm">
              {sources.sources.slice(0, 4).map((s) => (
                <li key={s.id}>
                  {s.publisher}
                  <span className="dt-num">
                    {' '}
                    · {formatDateTimeHr(s.retrieved_at) ?? 'datum nepoznat'}
                  </span>
                </li>
              ))}
            </ul>
          ) : (
            <p>Popis izvora i datuma dohvaćanja nalazi se na stranici „Otvoreni podaci”.</p>
          )}
          <p style={{ marginTop: '0.75rem' }}>
            <Link to="/izvori">Svi izvori podataka</Link>
          </p>
        </article>
        <article className="na-card na-explainer">
          <p className="na-overline">Za gradske planere</p>
          <h2>Gdje bi nova ustanova pomogla najviše?</h2>
          <p>Karta nezadovoljene potrebe po ćelijama od 1 km² i prijedlog 1–5 novih lokacija.</p>
          <p style={{ marginTop: '0.75rem' }}>
            <Link to="/planiranje">Otvori planerski način</Link>
          </p>
        </article>
      </section>
    </div>
  );
}
