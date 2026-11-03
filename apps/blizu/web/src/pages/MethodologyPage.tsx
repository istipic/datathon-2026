import { ErrorState, LoadingSkeleton } from '@dt/ui';
import { useQuery } from '@tanstack/react-query';
import { api } from '../lib/api';
import { useSources } from '../lib/useSources';
import { formatDateTimeHr } from '../lib/dates';
import { CATEGORY_IDS, PERSONA_IDS } from '../lib/types';

/** Methodology: renders the versioned scoring.yaml served by the API. */
export function MethodologyPage() {
  const scoring = useQuery({
    queryKey: ['scoring'],
    queryFn: () => api.scoring(),
    staleTime: Infinity,
  });
  const { data: sources } = useSources();

  if (scoring.isPending) return <LoadingSkeleton lines={8} label="Učitavam metodologiju…" />;
  if (scoring.isError)
    return <ErrorState message={scoring.error.message} onRetry={() => void scoring.refetch()} />;
  const cfg = scoring.data;

  return (
    <article className="prose-blizu mx-auto max-w-4xl space-y-8">
      <header>
        <h1 className="text-3xl font-semibold">Metodologija</h1>
        <p className="mt-2 text-neutral-700">
          Verzija bodovanja <strong className="dt-num">{cfg.version}</strong>, ažurirano{' '}
          {cfg.updated}. Sve brojke u nastavku čitaju se izravno iz konfiguracijske datoteke{' '}
          <code>scoring.yaml</code> koju koristi i izračun.
        </p>
      </header>

      <section aria-labelledby="m-how">
        <h2 id="m-how" className="mb-2 text-xl font-semibold">
          Kako računamo
        </h2>
        <ol className="list-decimal space-y-2 pl-6">
          <li>
            <strong>Mreža hoda.</strong> Pješačka mreža Grada Zagreba iz OpenStreetMapa; za
            invalidska kolica izbacujemo bridove sa stepenicama (<code>highway=steps</code>) i
            oznakom <code>wheelchair=no</code>.
          </li>
          <li>
            <strong>Minute.</strong> <code>minute = udaljenost_m / brzina / 60</code>, pri čemu je
            brzina ovisna o personi (tablica ispod). Udaljenost je duljina najkraćeg puta po mreži
            od adrese do najbližeg objekta.
          </li>
          <li>
            <strong>Ocjena kategorije.</strong> <code>s(t) = 1</code> ako je <code>t ≤ g</code>,{' '}
            <code>0</code> ako je <code>t ≥ m</code>, inače <code>(m − t) / (m − g)</code>.
          </li>
          <li>
            <strong>Blizu indeks.</strong> <code>round(100 · Σ w·s)</code>, uz ponovno normiranje
            težina na kategorije za koje imamo podatke i koje su važne za personu (težina 0 se ne
            računa).
          </li>
          <li>
            <strong>Ocjena slovom.</strong>{' '}
            {Object.entries(cfg.grades)
              .map(([g, v]) => `${g} ≥ ${v}`)
              .join(', ')}
            , inače E.
          </li>
          <li>
            <strong>Pouzdanost.</strong> Faktor razine izvora (
            {Object.entries(cfg.confidence.tier_factor)
              .map(([t, f]) => `${t} ${f}`)
              .join(', ')}
            ) × faktor starosti podataka (
            {cfg.confidence.freshness
              .map((f) =>
                f.max_months === null ? `starije ${f.factor}` : `≤ ${f.max_months} mj. ${f.factor}`,
              )
              .join(', ')}
            ); ukupna je pouzdanost ponderirani prosjek. Oznake: visoka ≥{' '}
            {cfg.confidence.labels.visoka}, srednja ≥ {cfg.confidence.labels.srednja}, inače niska.
          </li>
        </ol>
      </section>

      <section aria-labelledby="m-personas">
        <h2 id="m-personas" className="mb-2 text-xl font-semibold">
          Persone
        </h2>
        <div className="dt-table-wrap">
          <table className="dt-table">
            <caption className="dt-sr-only">Persone, brzine hoda i graf</caption>
            <thead>
              <tr>
                <th scope="col">Persona</th>
                <th scope="col">Brzina (m/s)</th>
                <th scope="col">Graf</th>
              </tr>
            </thead>
            <tbody>
              {PERSONA_IDS.map((id) => (
                <tr key={id}>
                  <th scope="row">{cfg.personas[id].label}</th>
                  <td className="dt-num">
                    {cfg.personas[id].speed_mps.toFixed(2).replace('.', ',')}
                  </td>
                  <td>{cfg.personas[id].graph === 'full' ? 'puni' : 'za invalidska kolica'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="m-cats">
        <h2 id="m-cats" className="mb-2 text-xl font-semibold">
          Kategorije, pragovi i težine
        </h2>
        <p className="mb-2 text-sm text-neutral-700">
          g = dobro (minute), m = najviše (minute). Težine su po personi (0 = nije relevantno).
        </p>
        <div className="dt-table-wrap">
          <table className="dt-table" data-testid="weights-table">
            <caption className="dt-sr-only">Pragovi g i m te težine po personi</caption>
            <thead>
              <tr>
                <th scope="col">Kategorija</th>
                <th scope="col">g</th>
                <th scope="col">m</th>
                {PERSONA_IDS.map((p) => (
                  <th key={p} scope="col">
                    {cfg.personas[p].label}
                  </th>
                ))}
                <th scope="col">Skupina (planiranje)</th>
              </tr>
            </thead>
            <tbody>
              {CATEGORY_IDS.map((id) => {
                const c = cfg.categories[id];
                return (
                  <tr key={id}>
                    <th scope="row">{c.label}</th>
                    <td className="dt-num">{c.good_min}</td>
                    <td className="dt-num">{c.max_min}</td>
                    {PERSONA_IDS.map((p) => (
                      <td key={p} className="dt-num">
                        {c.weights[p].toFixed(2).replace('.', ',')}
                      </td>
                    ))}
                    <td>{cfg.group_labels[c.group]}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>

      <section aria-labelledby="m-plan">
        <h2 id="m-plan" className="mb-2 text-xl font-semibold">
          Planiranje
        </h2>
        <p>
          Nezadovoljena potreba po ćeliji od 1 km: <code>U = P · (1 − s(prosječne minute))</code>,
          gdje je P broj stanovnika ciljne skupine (65+ za liječnike i ljekarne, djeca do 15 za
          vrtiće i škole, inače ukupno). Prijedlog lokacija bira se pohlepnim algoritmom maksimalnog
          pokrivanja: kandidati su čvorovi mreže u naseljenim ćelijama (jedan na ≈ 300 m), a čvor je
          pokriven ako je nova ustanova unutar <em>g</em> minuta hoda po mreži za odabranu personu.
        </p>
      </section>

      <section aria-labelledby="m-limits">
        <h2 id="m-limits" className="mb-2 text-xl font-semibold">
          Ograničenja
        </h2>
        <ul className="list-disc space-y-2 pl-6">
          <li>
            <strong>Potpunost OpenStreetMapa.</strong> Ljekarne, liječnici, pošte, knjižnice,
            parkovi i trgovine dolaze iz OSM-a (razina „zajednica”, faktor 0,8) i ne moraju biti
            potpuni; pješačka mreža također ima praznina.
          </li>
          <li>
            <strong>Mreža od 1 km.</strong> Stanovništvo je poznato samo po ćelijama od 1 km² (Popis
            2021., Eurostat). Ne znamo gdje u ćeliji ljudi stvarno žive; prosjek minuta računa se po
            čvorovima mreže u ćeliji. Ćelije na granici Zagreba mogu sadržavati stanovnike izvan
            grada.
          </li>
          <li>
            <strong>Starost podataka.</strong> Popis vrtića je iz 2022. godine; školski izvor ne
            sadrži nazive pa se oni, gdje je moguće, preuzimaju iz OSM-a. Slobodna mjesta u vrtićima
            su stanje na dan 01.01.2025.
          </li>
          <li>
            <strong>Prijevoz.</strong> Postaja se broji ako ima ≥ 6 polazaka na sat u jutarnjem vrhu
            (07–09 h) referentne srijede iz ZET-ova voznog reda; ne mjeri se stvarna točnost ni
            stajalište izvan ZET-a.
          </li>
          <li>
            <strong>Kolica.</strong> Pristupnost se temelji samo na OSM oznakama stepenica i{' '}
            <code>wheelchair=no</code>; nagibi, rubnici i širina staza nisu uključeni.
          </li>
          <li>
            <strong>Hod, ne vožnja.</strong> Procjena vrijedi za hodanje po prosječnim brzinama;
            vrijeme čekanja i nagibi terena nisu uračunati.
          </li>
        </ul>
      </section>

      <section aria-labelledby="m-dates">
        <h2 id="m-dates" className="mb-2 text-xl font-semibold">
          Datumi podataka
        </h2>
        {sources ? (
          <ul className="list-disc space-y-1 pl-6">
            {sources.sources.map((s) => (
              <li key={s.id}>
                <strong>{s.title}</strong> ({s.publisher}): dohvaćeno{' '}
                {formatDateTimeHr(s.retrieved_at) ?? 'nije dohvaćeno'}
                {s.last_run?.source_last_modified
                  ? `, izvor zadnji put izmijenjen ${formatDateTimeHr(s.last_run.source_last_modified)}`
                  : ''}
                .
              </li>
            ))}
          </ul>
        ) : (
          <p className="text-neutral-600">Izvori se učitavaju…</p>
        )}
        <p className="mt-2">
          Potpun popis s licencijama:{' '}
          <a className="underline" href="/izvori">
            Izvori podataka
          </a>
          .
        </p>
      </section>
    </article>
  );
}
