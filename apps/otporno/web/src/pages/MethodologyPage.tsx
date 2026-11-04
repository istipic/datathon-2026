import { Link } from 'react-router-dom';

export function MethodologyPage() {
  return (
    <article className="grid max-w-3xl gap-6">
      <header>
        <p className="ot-eyebrow">Metodologija</p>
        <h1 className="ot-display mt-1 text-2xl sm:text-3xl">Kako nastaje putovnica rizika</h1>
      </header>

      <section aria-labelledby="m-flood">
        <h2 id="m-flood" className="ot-display text-xl">
          Poplava: što možemo, a što ne
        </h2>
        <p className="mt-2">
          Hrvatske vode objavljuju karte opasnosti od poplava (2019.) za tri scenarija: veliku,
          srednju i malu vjerojatnost. Provjerili smo sve načine pristupa podacima, redom: vektorski
          podaci (WFS ili preuzimanje), upit o točki (GetFeatureInfo) i, kao posljednje, prikaz
          karte (WMS). Slojevi opasnosti nisu upitljivi, WFS je isključen i vektorsko preuzimanje ne
          postoji, pa koristimo <strong>samo prikaz karte</strong>.
        </p>
        <p className="mt-2">
          Zato razinu poplave za vašu točku <strong>ne izvodimo</strong>: nikada ne određujemo
          razred iz boje piksela. Karta je prikazana uz adresu, a pravila ponašanja iz javnih uputa
          prikazana su neovisno o razini. Karte su informativne; Hrvatske vode ne jamče za
          posljedice korištenja. Izvor: Hrvatske vode, 2019.
        </p>
      </section>

      <section aria-labelledby="m-heat">
        <h2 id="m-heat" className="ot-display text-xl">
          Vrućina
        </h2>
        <p className="mt-2">
          Iz klimatskih modela CMIP6 (CMCC_CM2_VHR4, EC_Earth3P_HR, MRI_AGCM3_2_S) preko Open-Meteo
          Climate API-ja uzimamo dnevne najviše i najniže temperature. <strong>Vrući dan</strong>{' '}
          ima najvišu temperaturu od 30 °C ili više, <strong>tropska noć</strong> najnižu od 20 °C
          ili više. Brojimo ih po godini za razdoblja 1991.–2020. („danas”) i 2031.–2050., pa
          uzimamo prosjek modela te najmanju i najveću vrijednost (raspon).
        </p>
        <p className="mt-2">
          Razina se određuje <strong>rangom</strong>: gdje se prosječan broj vrućih dana u
          2031.–2050. na vašoj točki nalazi među točkama nacionalne mreže od 0,25°. Pojasevi: niska
          (ispod 25. percentila), umjerena (25.–50.), visoka (50.–80.), vrlo visoka (80. i više).
          Točka za adresu zaokružuje se na 0,1° (oko 10 km), pa rezultat opisuje okolicu, ne zgradu.
          Bez ocjene prikazujemo samo mjerljive brojke, ne jedinstveni „ukupni” rizik.
        </p>
        <p className="mt-2">
          Usluga Open-Meteo u besplatnom je paketu ograničena po težini upita (u praksi oko deset
          punih upita dnevno), pa se nacionalna mreža puni postupno. Dok je mreža nepotpuna,
          ranžiranje je približno, a pouzdanost se snižava i to piše na kartici. Podaci:
          Open-Meteo.com, CC BY 4.0.
        </p>
      </section>

      <section aria-labelledby="m-conf">
        <h2 id="m-conf" className="ot-display text-xl">
          Pouzdanost
        </h2>
        <p className="mt-2">
          Visoka pouzdanost znači da su dostupna sva tri modela, modeli se slažu (raspon manji od
          polovice prosjeka), točka je vaša vlastita i usporedna mreža ima barem 100 točaka. Svaki
          razlog za nižu pouzdanost ispisan je na kartici.
        </p>
      </section>

      <section aria-labelledby="m-planner">
        <h2 id="m-planner" className="ot-display text-xl">
          Pregled općine
        </h2>
        <p className="mt-2">
          Stanovništvo dolazi iz mreže od 1 km popisa 2021. (Eurostat); ćelija pripada općini u
          kojoj joj je središte, pa rubne ćelije mogu uključivati i susjedne stanovnike. Prioritet
          ćelije je zbroj težina × razina opasnosti × (stanovnici 65+ + polovica ostalih). Zadane
          težine su poplava 50 %, vrućina 35 %, požar 15 %; opasnosti za koje nema podataka
          izuzimaju se i preostale težine preračunavaju na zbroj 1.
        </p>
        <p className="mt-2">
          Centri za rashlađivanje biraju se među javnim zgradama iz OpenStreetMapa (knjižnice,
          škole, društveni domovi, socijalne ustanove, vijećnice) pohlepnim algoritmom maksimalnog
          pokrivanja stanovnika 65+. Pokrivenost je zračna udaljenost od 415 m (10 minuta hoda pri
          0,9 m/s uz faktor zaobilaska 1,3). Postojeći centri nisu uključeni jer ne postoji javni
          registar.
        </p>
      </section>

      <section aria-labelledby="m-act">
        <h2 id="m-act" className="ot-display text-xl">
          Koraci „Što učiniti”
        </h2>
        <p className="mt-2">
          Svaki je korak kratko preformuliran iz javne upute (Ravnateljstvo civilne zaštite,
          Hrvatske vode, HZJZ i dr.) i uz njega stoji poveznica na izvor. Za općinske korake koji se
          oslanjaju na zakone, a ne na posebnu uputu, izvor je zakon.
        </p>
      </section>

      <p>
        <Link to="/izvori" className="underline">
          Popis svih izvora podataka
        </Link>
      </p>
    </article>
  );
}
