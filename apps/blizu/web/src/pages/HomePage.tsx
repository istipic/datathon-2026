import { useState } from 'react';
import { useNavigate, useSearchParams } from 'react-router-dom';
import { AddressSearch, resultLabel } from '../components/AddressSearch';
import { PersonaControl } from '../components/PersonaControl';
import { EXAMPLES } from '../lib/examples';
import { isPersona } from '../lib/labels';
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

  function go(item: GeocodeItem) {
    navigate(cardUrl(item.lat, item.lon, persona, resultLabel(item)));
  }

  return (
    <div className="mx-auto max-w-3xl py-6">
      <h1 className="text-3xl font-semibold text-neutral-900 md:text-5xl">Što ti je blizu?</h1>
      <p className="mt-3 text-lg text-neutral-700">
        Upiši bilo koju adresu u Zagrebu i saznaj koliko minuta pješice je do liječnika, ljekarne,
        vrtića, škole, javnog prijevoza, parka i trgovine. Računamo posebno za starije osobe,
        roditelje s djecom i osobe u invalidskim kolicima.
      </p>

      <div className="mt-8 rounded-xl border border-neutral-300 bg-white p-5 shadow-sm">
        <AddressSearch onSelect={go} autoFocus />
        <div className="mt-5">
          <PersonaControl value={persona} onChange={setPersona} />
        </div>
      </div>

      {EXAMPLES.length > 0 ? (
        <section className="mt-6" aria-labelledby="examples-title">
          <h2 id="examples-title" className="mb-2 text-base font-semibold text-neutral-700">
            Isprobaj na primjeru
          </h2>
          <ul className="flex flex-wrap gap-2">
            {EXAMPLES.map((example) => (
              <li key={example.query}>
                <button
                  type="button"
                  className="min-h-[44px] rounded-full border border-brand-700 bg-white px-4 py-2 text-brand-700 hover:bg-neutral-100"
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

      <p className="mt-8 text-sm text-neutral-600">
        Za gradske planere:{' '}
        <a href="/planiranje" className="underline">
          karta nezadovoljene potrebe i prijedlog novih lokacija
        </a>
        .
      </p>
    </div>
  );
}
