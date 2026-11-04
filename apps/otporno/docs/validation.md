# Otporko: validacija

Stanje na 2026-11-04. Ovdje je samo ono što je stvarno provjereno ili što čeka ručni korak.

## Automatske provjere

| Provjera                                                                                                                                     | Gdje                                                 | Rezultat        |
| -------------------------------------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------- | --------------- |
| Brojanje vrućih dana / tropskih noći uspoređeno s neovisnim brojanjem na stvarnom odgovoru Open-Meteo (45,5 N 15,5 E, 3 modela, 1991.–2050.) | `tests/test_unit.py`                                 | prolazi         |
| Pojasevi (0,25 / 0,5 / 0,8), percentil, farthest-first uzorak                                                                                | `tests/test_unit.py`                                 | prolazi         |
| Razina poplave iz oznaka scenarija, prag ćelije 10 %, bez oznaka → nepoznato                                                                 | `tests/test_unit.py`                                 | prolazi         |
| Parsiranje WMS capabilities (snimka 2026-11-04): tri sloja, nijedan upitljiv → ljestvica c                                                   | `tests/test_unit.py`                                 | prolazi         |
| Formula prioriteta, preraspodjela težina, validacija zbroja 1 ± 0,01                                                                         | `tests/test_unit.py`                                 | prolazi         |
| Troškovni model kvote (939,2 za 6 serija × 21 915 dana) i klizni prozor                                                                      | `tests/test_unit.py`                                 | prolazi         |
| Pravila akcija: valjana datoteka, svako pravilo ima https izvor                                                                              | `tests/test_unit.py`                                 | prolazi         |
| Optimizator: `covered_after ≥ covered_before`, k = 1/3/5 monotono                                                                            | `tests/test_unit.py`, `tests/test_integration.py`    | prolazi         |
| `/passport` za dvije točke u Karlovcu: isti iskreni odgovor o poplavi (ljestvica c), vrućina s rasponom modela                               | `tests/test_integration.py`                          | prolazi         |
| `/passport` izvan Hrvatske i izvan općine → 422                                                                                              | `tests/test_integration.py`                          | prolazi         |
| Hladna putovnica < 2 s, spremljena < 300 ms (Open-Meteo zamijenjen snimljenim odgovorom)                                                     | `tests/test_integration.py`                          | prolazi         |
| Brojevi na `/opcina` (pojasevi, KPI) jednaki zbrojevima GeoJSON-a `/cells`                                                                   | `tests/test_integration.py`                          | prolazi         |
| Web: kartice, pravila s izvorima, 422, ponovni pokušaj, ispravak težina                                                                      | `apps/otporno/web` (vitest)                          | prolazi         |
| Playwright: adresa → putovnica; općina → optimizator radi                                                                                    | `apps/otporno/web/e2e/smoke.spec.ts`                 | prolazi         |
| Požar (CORINE): klasa u točki i vegetacija u krugu 500 m na snimljenim odgovorima EEA usluge; `/passport` vraća blok `fire`                  | `tests/test_unit.py`, `tests/test_integration.py`    | prolazi         |
| DHMZ: parsiranje stvarne snimke (60 postaja), najbliže postaje, skrivanje starijeg od 3 h, cache 30 min                                      | `tests/test_unit.py`, `tests/test_integration.py`    | prolazi         |
| Izvješće općine (HTML) usklađeno s `/exposure`, uključuje izvore i HV napomenu                                                               | `tests/test_integration.py`                          | prolazi         |
| Lighthouse pristupačnost `/putovnica`                                                                                                        | `data/evidence/2026-11-04_lighthouse_putovnica.json` | 100 (cilj ≥ 95) |

Napomena: integracijski testovi i Playwright koriste bazu `otporno_test` sa stvarnim ćelijama i zgradama Karlovca
te 24 snimljene točke usporedne mreže; Open-Meteo je u testovima zamijenjen snimljenim stvarnim odgovorom.

## Ručni korak: poplava (30 točaka u Karlovcu)

`otporno validate` piše `docs/validation_points.csv` (30 točaka, sjeme 2026, ponderirano brojem stanovnika).
Za svaku točku otvorite pregled Hrvatskih voda (poveznica je ispisana naredbom), uključite tri scenarija 2019. i
upišite jesu li točke unutar velike, srednje i male vjerojatnosti. Aplikacija na toj razini ne daje razred
(`app_flood` je „Automatska procjena nije dostupna; pogledajte kartu.”), pa se uspoređuje samo ono što ste
pročitali u pregledniku s kartom koju aplikacija prikazuje uz istu točku. **Ovaj korak nije obavljen**: zahtijeva
čovjeka uz preglednik.

## Razumnost klime

`otporno validate` ispisuje modelirani `base_hot_days` (1991.–2020.) za Zagreb–Grič (točka 45,8 N 16,0 E) uz poveznicu
na DHMZ klimatske normale ( https://meteo.hr/klima.php?section=klima_pracenje&param=klimatske_normale ). Vrijednost
DHMZ-a ne prepisujemo; usporedbu radi čovjek. Dok se točka za Zagreb ne dohvati (kvota), ispis je `null`.

Za jedinu već dohvaćenu adresnu točku (45,5 N 15,5 E, okolica Karlovca) modeli daju u prosjeku 17,0 vrućih dana
godišnje u 1991.–2020. i 30,6 u 2031.–2050. (raspon modela 19,6–39,5).

## Poznate slabosti

- Rang vrućine temelji se na nepotpunoj usporednoj mreži dok posao ne završi; kartica prikazuje broj točaka i snižava pouzdanost.
- Karlovac je trenutno u pojasu „umjerena” u cijelosti, pa je zadana potražnja za centre rashlađivanja prazna;
  planer može uključiti niži pojas.
- Pravila akcija za općine rijetko imaju posebnu javnu uputu (oslanjaju se na zakone i HZJZ); izvor je uvijek naveden.
