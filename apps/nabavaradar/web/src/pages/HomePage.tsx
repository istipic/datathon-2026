import { useQuery } from '@tanstack/react-query';
import { Link, useNavigate } from 'react-router-dom';
import { useAlertDialog } from '../components/AlertDialog';
import { OibForm } from '../components/OibForm';
import { TenderCard } from '../components/TenderCard';
import { api } from '../lib/api';
import { formatDate, formatEur } from '../lib/format';
import { useStatus } from '../lib/hooks';

/** KONČAR - Elektroindustrija d.d.; its OIB is printed in the company's public issuer filings
 * (apps/nabavaradar/data/evidence/2026-11-04_e2e_company_oib_source.json). */
export const EXAMPLE_OIB = '45050126417';

function Check() {
  return (
    <span
      aria-hidden="true"
      className="grid h-7 w-7 place-items-center rounded-full border-2 border-black bg-white font-bold"
    >
      ✓
    </span>
  );
}
function Cross() {
  return (
    <span
      aria-hidden="true"
      className="grid h-7 w-7 place-items-center rounded-full border-2 border-dashed border-neutral-500 bg-white font-bold"
    >
      ✕
    </span>
  );
}

const FEATURES = [
  [
    '◎',
    'Rangirani natječaji',
    'Otvoreni natječaji poredani po prilagodbi vašim djelatnostima, uz objašnjenje „Zašto?” za svaki.',
  ],
  [
    '⚔',
    'Povijest konkurencije',
    'Koliko je ponuda prosječno stizalo na slične nabave, uvijek s brojem dodjela.',
  ],
  [
    '✉',
    'Upozorenja po pragu',
    'E-pošta čim natječaj dosegne vaš prag prilagodbe. Svaki natječaj samo jednom.',
  ],
  ['📅', 'Rok u kalendaru', 'Preuzmite .ics i dobijte podsjetnik dan prije isteka roka.'],
  [
    '🏛',
    'Tržište za naručitelje',
    'Procjena broja dobavljača po županijama i konkurencije prije objave nabave.',
  ],
  [
    '★',
    'Spremljeni natječaji',
    'Označite „Prati” i vratite se na popis; ostaje samo u vašem pregledniku.',
  ],
] as const;

export function HomePage() {
  const navigate = useNavigate();
  const { open } = useAlertDialog();
  const status = useStatus();
  const highlights = useQuery({
    queryKey: ['highlights'],
    staleTime: 5 * 60_000,
    queryFn: ({ signal }) => api.highlights(signal),
  });
  const example = useQuery({
    queryKey: ['example-match', EXAMPLE_OIB],
    staleTime: 5 * 60_000,
    retry: false,
    queryFn: ({ signal }) => api.match({ oib: EXAMPLE_OIB, limit: 1 }, signal),
  });
  const h = highlights.data;
  const items = [
    ...(h?.top_buyers ?? []).map((b) => `${b.name} · ${b.open_notices} otvorenih`),
    ...(h?.top_cpv_areas ?? []).map(
      (a) => `${a.division} ${a.label ?? 'CPV područje'} · ${a.open_notices}`,
    ),
  ];
  const sudreg =
    typeof status.data?.sudreg_data_as_of === 'string' ? status.data.sudreg_data_as_of : null;
  const ted =
    typeof status.data?.ted_competition_retrieved_at === 'string'
      ? status.data.ted_competition_retrieved_at
      : null;

  return (
    <>
      <section
        className="nb-yellow nb-dots nb-border-y"
        aria-labelledby="hero-h"
        style={{ borderTop: 0 }}
      >
        <div className="nb-wrap grid items-center gap-10 py-12 lg:grid-cols-2 lg:py-20">
          <div>
            {h ? (
              <p className="nb-pill" data-testid="hero-badge">
                <span aria-hidden="true">●</span>
                {h.open_notices} otvorenih natječaja
                {ted ? ` · TED dohvaćen ${formatDate(ted)}` : ''}
              </p>
            ) : null}
            <h1 id="hero-h" className="nb-h1 mt-5">
              Natječaji koji odgovaraju tvojoj <span className="nb-outline">djelatnosti</span>
            </h1>
            <p className="mt-5 max-w-xl text-lg">
              Unesite OIB tvrtke: rangiramo otvorene javne natječaje prema upisanim djelatnostima i
              objašnjavamo zašto je svaki na popisu.
            </p>
            <div className="nb-card mt-6" style={{ maxWidth: '34rem' }}>
              <OibForm onSubmit={(oib) => navigate(`/tvrtka/${oib}`)} />
            </div>
            <div className="mt-6 flex flex-wrap gap-4">
              <Link to="/narucitelj" className="nb-btn nb-btn--light">
                Javni naručitelj? Provjerite tržište
              </Link>
              <button type="button" className="nb-btn nb-btn--light" onClick={() => open()}>
                Pošalji mi relevantne natječaje
              </button>
            </div>
          </div>
          <div aria-label="Primjer stvarnog natječaja">
            <div className="nb-mock">
              <div className="nb-mock__bar">
                <span className="nb-dot" style={{ background: '#ff5f57' }} aria-hidden="true" />
                <span className="nb-dot" style={{ background: '#febc2e' }} aria-hidden="true" />
                <span className="nb-dot" style={{ background: '#28c840' }} aria-hidden="true" />
                <span className="ml-2">Primjer stvarnog natječaja (OIB {EXAMPLE_OIB})</span>
              </div>
              <div className="nb-sage p-4">
                {example.data && example.data[0] ? (
                  <ol className="m-0 list-none p-0" data-testid="hero-example">
                    <TenderCard item={example.data[0]} compact headingLevel="h2" />
                  </ol>
                ) : (
                  <p className="nr-card" role="status">
                    {example.isLoading
                      ? 'Učitavam primjer…'
                      : 'Primjer trenutno nije dostupan. Upišite OIB svoje tvrtke.'}
                  </p>
                )}
              </div>
            </div>
          </div>
        </div>
      </section>

      <section className="nb-marquee" aria-label="Otvoreni natječaji po naručiteljima i područjima">
        <ul className="dt-sr-only">
          {items.map((t) => (
            <li key={t}>{t}</li>
          ))}
        </ul>
        {items.length > 0 ? (
          <div className="nb-marquee__track" data-testid="marquee">
            {[0, 1].map((copy) =>
              items.map((t) => (
                <span key={`${copy}-${t}`} className="nb-marquee__item" aria-hidden="true">
                  {t}
                </span>
              )),
            )}
          </div>
        ) : null}
      </section>

      <section className="nb-section" aria-labelledby="pvs-h">
        <div className="nb-wrap">
          <h2 id="pvs-h" className="nb-h2">
            Zašto ručno prolaziti stotine obavijesti?
          </h2>
          <div className="mt-8 grid gap-8 md:grid-cols-2">
            <div className="nb-problem">
              <p className="nb-label text-xl">Bez Birokratka</p>
              <ul className="nb-list">
                {[
                  `Stotine otvorenih obavijesti${h ? ` (trenutno ${h.open_notices})` : ''} na TED-u, na engleskom i bez ranga.`,
                  'CPV šifre nabave ne odgovaraju NKD djelatnostima iz registra.',
                  'Rokovi se propuste jer nitko ne javlja kad se natječaj pojavi.',
                ].map((t) => (
                  <li key={t}>
                    <Cross />
                    <span>{t}</span>
                  </li>
                ))}
              </ul>
            </div>
            <div className="nb-solution">
              <p className="nb-label text-xl">S Birokratkom</p>
              <ul className="nb-list">
                {[
                  'Natječaji rangirani po prilagodbi vašim djelatnostima, s objašnjenjem.',
                  'NKD djelatnosti povezane s CPV područjima iz stvarnih dodjela.',
                  'E-pošta kad natječaj dosegne vaš prag, s rokom i poveznicom za kalendar.',
                ].map((t) => (
                  <li key={t}>
                    <Check />
                    <span>{t}</span>
                  </li>
                ))}
              </ul>
            </div>
          </div>
        </div>
      </section>

      <section className="nb-yellow nb-border-y nb-section" aria-labelledby="feat-h">
        <div className="nb-wrap">
          <h2 id="feat-h" className="nb-h2">
            Što možete s Birokratkom
          </h2>
          <ul className="mt-8 grid list-none gap-6 p-0 sm:grid-cols-2 lg:grid-cols-3">
            {FEATURES.map(([icon, title, body]) => (
              <li key={title} className="nb-card">
                <div className="nb-icon-box" aria-hidden="true">
                  {icon}
                </div>
                <h3 className="mt-4 text-2xl">{title}</h3>
                <p className="mt-2">{body}</p>
              </li>
            ))}
          </ul>
        </div>
      </section>

      <section className="nb-charcoal nb-on-dark nb-section" aria-labelledby="how-h">
        <div className="nb-wrap">
          <h2 id="how-h" className="nb-h2">
            Kako radi
          </h2>
          <ol className="nb-steps mt-10 list-none p-0">
            <span className="nb-steps__line" aria-hidden="true" />
            {[
              [
                '1',
                'Upiši OIB',
                'Djelatnosti dohvaćamo iz Sudskog registra, glavna je prva.',
                'rgb(183 198 194)',
              ],
              [
                '2',
                'Pogledaj rangirane natječaje i zašto',
                'Sličnost opisa, CPV područje, lokacija i rok daju ocjenu 0 do 100 %.',
                'rgb(255 225 124)',
              ],
              [
                '3',
                'Uključi upozorenja',
                'Odredi prag i filtere; javimo se kad natječaj dosegne prag.',
                '#fff',
              ],
            ].map(([n, title, body, ring]) => (
              <li key={n} className="grid justify-items-center gap-3 text-center">
                <span
                  className="nb-step__circle"
                  style={{ boxShadow: `0 0 0 4px ${ring}`, border: `4px solid ${ring}` }}
                  aria-hidden="true"
                >
                  {n}
                </span>
                <h3 className="text-2xl">
                  <span className="dt-sr-only">Korak {n}: </span>
                  {title}
                </h3>
                <p className="max-w-xs">{body}</p>
              </li>
            ))}
          </ol>
        </div>
      </section>

      <section className="nb-section" aria-labelledby="who-h">
        <div className="nb-wrap">
          <h2 id="who-h" className="nb-h2">
            Za koga je Birokratko
          </h2>
          <div className="mt-8 grid gap-6 md:grid-cols-3">
            <article className="nb-card nb-sage">
              <span className="nb-pill">Tvrtke</span>
              <p className="mt-4">
                Dobijte popis otvorenih natječaja za svoje djelatnosti i obavijest kad se pojavi
                novi iznad vašeg praga.
              </p>
            </article>
            <article className="nb-card nb-card--yellow">
              <span className="nb-pill">Javni naručitelji</span>
              <p className="mt-4">
                Prije objave nabave procijenite koliko je sposobnih dobavljača u županiji i kakva je
                bila konkurencija u sličnim nabavama.
              </p>
            </article>
            <article className="nb-card nb-card--dark">
              <span className="nb-pill">Savjetnici za nabavu</span>
              <p className="mt-4">
                Pratite natječaje za više klijenata: za svakog OIB postavite zasebna upozorenja i
                izvezite popis u CSV.
              </p>
            </article>
          </div>
        </div>
      </section>

      <section className="nb-sage nb-border-y nb-section" aria-labelledby="faq-h">
        <div className="nb-wrap">
          <h2 id="faq-h" className="nb-h2">
            Česta pitanja
          </h2>
          <div className="mt-8 grid gap-6 md:grid-cols-3">
            <article className="nb-faq">
              <h3 className="text-xl">Odakle dolaze podaci?</h3>
              <p className="mt-2">
                Natječaji su iz TED-a (Tenders Electronic Daily)
                {ted ? `, dohvaćeno ${formatDate(ted)}` : '.'} Djelatnosti tvrtki su iz Sudskog
                registra, a trenutno je to testno okruženje portala
                {sudreg ? ` sa snimkom od ${formatDate(sudreg)}` : '.'}
                {h
                  ? ` Ukupna procijenjena vrijednost otvorenih natječaja: ${formatEur(h.total_value_eur)}.`
                  : ''}
              </p>
            </article>
            <article className="nb-faq">
              <h3 className="text-xl">Kako računamo prilagodbu?</h3>
              <p className="mt-2">
                Prilagodba je zbroj četiriju sastavnica: sličnost opisa nabave i vaše djelatnosti
                (najveća težina), podudaranje CPV područja, lokacija naručitelja i preostalo
                vrijeme. Glavna djelatnost vrijedi punom težinom, sporedne nešto manje. Objave istog
                postupka spajamo u jednu karticu. Uz svaki natječaj otvorite „Zašto?” za razradu.
              </p>
            </article>
            <article className="nb-faq">
              <h3 className="text-xl">Kako se odjaviti?</h3>
              <p className="mt-2">
                Svaka poruka ima poveznicu za odjavu jednim klikom i poveznicu za promjenu praga,
                filtera i učestalosti ili za pauziranje. Odjavom se briše vaša e-adresa.
              </p>
            </article>
          </div>
        </div>
      </section>

      <section className="nb-yellow nb-dots nb-section" aria-labelledby="cta-h">
        <div className="nb-wrap text-center">
          <h2 id="cta-h" className="nb-h2 mx-auto max-w-3xl">
            Nemojte propustiti sljedeći natječaj za svoju tvrtku
          </h2>
          <p className="mx-auto mt-4 max-w-xl text-lg">
            Odredite prag prilagodbe i javit ćemo vam se e-poštom, samo kad se isplati.
          </p>
          <button type="button" className="nb-btn mt-8" onClick={() => open()}>
            Pošalji mi relevantne natječaje
          </button>
        </div>
      </section>
    </>
  );
}
