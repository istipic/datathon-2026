# ADR 0006: NabavaRadar – odluke o podacima

- Status: accepted
- Datum: 2026-11-04

## Kontekst

Specifikacija NabavaRadara pretpostavlja produkcijski Sudski registar, jedinstvene NKD šifre i TED obavijesti u
jednom obliku. Prave probe (dokazi u `apps/nabavaradar/data/evidence/`) pokazale su sljedeće činjenice i dovele
do odluka u nastavku. Nijedna nova ovisnost nije dodana (openpyxl, rapidfuzz, pgvector, sentence-transformers već
su u jezgri).

## Odluke

1. **Sudski registar: testno okruženje.** Dostavljeni produkcijski pristupni podaci vraćaju token, ali **HTTP 401 na
   svim podatkovnim pozivima** (račun nije potvrđen; dokaz `2026-11-04_sudreg_data_call_401.json`). Korisnik je
   dostavio vjerodajnice za `sudreg-data-test.gov.hr` i one rade. Zato su svi podaci o tvrtkama iz **testne snimke
   id 1 od 2024-06-16** (177 698 aktivnih subjekata, token vrijedi 3600 s a ne 21600 s). Aplikacija to pokazuje
   (oznaka „testno okruženje”, datum snimke, `FreshnessChip`), a `data_source.notes` bilježi okruženje. Prelazak na
   produkciju je samo promjena `SUDREG_*` varijabli.
2. **NKD ključ je (šifra, verzija).** Šifrarnik sadrži NKD 1994, 2002 i 2007 s istim šiframa za različite
   djelatnosti, a `predmeti_poslovanja` uglavnom upućuje na NKD 1994/2002. Tablica `nkd` ima PK `(code, version)`,
   a `company_activity` dodatni stupac `nkd_version` (odstupanje od „code PK” iz specifikacije). Više redaka s istom
   (šifra, verzija) (preimenovani unosi) svodi se na trenutni red, ali se svaki id mapira na isti ključ.
3. **Obuhvat tvrtki.** Pohranjuju se aktivni subjekti s valjanim OIB-om. **Ne pohranjuju se** trgovci pojedinci
   (naziv je obično ime fizičke osobe), subjekti u stečaju ili likvidaciji, stečajne i likvidacijske mase.
   Slobodan tekst `predmeti_poslovanja` se ne pohranjuje (samo NKD šifre). Rezultat: 170 796 tvrtki, 80,2 % ima barem
   jednu NKD djelatnost.
4. **Glavna djelatnost** je `subjekti.glavna_djelatnost` (NKD 2007, broj bez vodeće nule: `1072` → `10.72`); ako je
   nema, `pretezite_djelatnosti`. Ostale NKD djelatnosti dolaze iz `predmeti_poslovanja` i
   `evidencijske_djelatnosti`.
5. **Natječajne obavijesti: prozor povijesti.** Zadatak traži natječajne obavijesti zadnjih 120 dana i obavijesti o
   dodjeli zadnjih 36 mjeseci. Validacija zahtijeva natječaj iz kojeg je pobjednik izašao, pa se natječajne obavijesti
   učitavaju za isti prozor od 36 mjeseci (`COMPETITION_DAYS=1100` pri prvom učitavanju). Ponuda „otvorenih” natječaja
   i dalje se računa samo iz onih s rokom u budućnosti. Dnevno osvježavanje je inkrementalno (zadnjih 7 dana).
6. **Povezivanje rezultat → natječaj** ide preko `procedure-identifier` (isti UUID u obje obavijesti).
7. **Obavijesti o dodjeli prije otprilike 2024-02** su stari TED zapisi bez podataka o pobjednicima i broju ponuda
   (API ih ne vraća); statistika konkurencije i validacija zato počinju kad se podaci pojave.
8. **Poravnanje plošnih lista iz TED-a.** `result-lot-identifier` i `winner-selection-status` su po lotu (lot se može
   ponoviti), `winner-name` i `tender-lot-identifier` po ponudi, a `winner-identifier` je deduplicirano po
   organizaciji (preslikava se preko jedinstvenih naziva po redoslijedu). Broj ponuda po lotu čita se iz blokova
   `received-submissions-type-*` (blok počinje kad se kod ponovi). Što se ne može pouzdano poravnati, ostaje prazno.
9. **Rok.** Rok za ponude (`deadline-receipt-tender-*`), a za ograničene postupke rok za zahtjeve za sudjelovanje
   (`deadline-receipt-request-*`); API izlaže `deadline_kind`. Natječaj bez ikakvog roka drži se „otvorenim” samo
   120 dana od objave (neutralna komponenta T = 0,5).
10. **Imena pobjednika** (TED) pohranjuju se u `award` kako specifikacija traži, ali ih API prikazuje samo kad je
    pobjednik upisan u `company`; imena ponuditelja iz registara ugovora gradova/općina pohranjuju se samo za pravne
    osobe (OIB u `company` ili pravni oblik u nazivu).
11. **Prag τ** bira se maksimizacijom F1 između djelatnosti pobjednika i CPV odjeljka njihovih dodjela te se piše u
    `config/market.yaml` naredbom `nabavaradar eval`. Odabran je na istom skupu na kojem se izvještava (bez odvojenog
    testnog skupa); to je navedeno u `validation.md`.
12. **Pravni citati** u savjetima su doslovno iz izvornog teksta Zakona o javnoj nabavi (NN 120/2016), čl. 198., 204.
    i 228., koji je otvoren i pročitan (dokaz `2026-11-04_zjn_nn120-2016_clanci_198_204_228.json`). Zakon je kasnije
    mijenjan (npr. NN 114/22): korisnik mora provjeriti važeći pročišćeni tekst.

## Posljedice

- Brojevi o tvrtkama nisu „žive”: stari su više od dvije godine dok se ne prijeđe na produkcijski registar.
- Validacija mjeri sposobnost rangiranja stvarnih pobjednika, ne uspjeh na natječaju.
- Crosswalk NKD→CPV koristi tekstove obavijesti, među kojima su i ciljne obavijesti validacije (blago povoljno).
