import { useNavigate, Link } from 'react-router-dom';
import { OibForm } from '../components/OibForm';
import { useStatus } from '../lib/hooks';

export function HomePage() {
  const navigate = useNavigate();
  const status = useStatus();
  return (
    <>
      <section className="nr-hero" aria-labelledby="hero-h">
        <div className="mx-auto max-w-5xl px-4 py-12">
          <h1
            id="hero-h"
            className="text-2xl font-semibold"
            style={{ fontSize: 'var(--text-3xl)', lineHeight: 1.15 }}
          >
            Natječaji koji odgovaraju tvojoj djelatnosti
          </h1>
          <p className="mt-3 max-w-2xl text-lg">
            Unesite OIB tvrtke: rangiramo otvorene javne natječaje prema upisanim djelatnostima i
            objašnjavamo zašto je svaki na popisu.
          </p>
          <div
            className="mt-6 rounded-lg bg-white p-4 text-neutral-900"
            style={{ maxWidth: '36rem' }}
          >
            <OibForm onSubmit={(oib) => navigate(`/tvrtka/${oib}`)} />
          </div>
          <p className="mt-4">
            <Link to="/narucitelj">Javni naručitelj? Provjerite tržište</Link>
          </p>
        </div>
      </section>

      <section className="mx-auto max-w-5xl p-4" aria-labelledby="how-h">
        <h2 id="how-h" className="text-xl font-semibold">
          Kako radi
        </h2>
        <ol className="mt-3 grid gap-4 md:grid-cols-3">
          <li className="nr-card">
            <strong>1. Profil iz registra.</strong> NKD djelatnosti tvrtke dohvaćamo iz Sudskog
            registra (glavna djelatnost prva).
          </li>
          <li className="nr-card">
            <strong>2. Ocjena prilagodbe.</strong> Sličnost opisa, CPV područje, lokacija i
            preostalo vrijeme daju ocjenu od 0 do 100 %.
          </li>
          <li className="nr-card">
            <strong>3. Konkurencija.</strong> Uz svaki natječaj prikazujemo koliko je ponuda
            prosječno stizalo na slične nabave (uvijek s brojem dodjela n).
          </li>
        </ol>
        {status.data ? (
          <p className="mt-4 text-sm text-neutral-700">
            U bazi je{' '}
            <span className="num font-semibold">
              {status.data.companies.toLocaleString('hr-HR')}
            </span>{' '}
            aktivnih tvrtki iz Sudskog registra
            {status.data.environment === 'test' ? ' (testno okruženje portala)' : ''}. Pogledajte{' '}
            <Link to="/metodologija" className="text-brand-700 underline">
              metodologiju i rezultate validacije
            </Link>
            .
          </p>
        ) : null}
      </section>
    </>
  );
}
