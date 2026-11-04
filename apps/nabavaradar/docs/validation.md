# Birokratko – validacija

_Generirano naredbom `nabavaradar eval` (2026-11-04T01:23:34.538132+00:00). Brojevi se ne uređuju ručno._

## Pitanje

Kad bismo tvrtki koja je stvarno dobila ugovor pokazali natječaje tog mjeseca, bi li se njezin stvarni natječaj našao među prvih 10 / 20?

## Protokol

1. Uzimaju se obavijesti o dodjeli ugovora (TED) u kojima je pobjednik valjan OIB (ISO 7064, MOD 11,10) koji postoji u tablici `company` (Sudski registar).
2. Cilj je stvarna natječajna obavijest pobjednika (veza preko procedure-identifier).
3. Za svakog pobjednika rangiraju se **sve** natječajne obavijesti (naručitelj iz Hrvatske) objavljene u mjesecu cilja. Svaka obavijest ocjenjuje se na dan svoje objave (komponenta T računa se od objave do roka).
4. Metoda: ocjena prilagodbe `0,55·S + 0,25·C + 0,10·G + 0,10·T` (profil = do 10 NKD djelatnosti, glavna prva). Osnovna metoda: Postgres full-text (`simple` konfiguracija) s riječima iz naziva djelatnosti (ILI-upit, riječi od najmanje 4 slova), poredano po `ts_rank`.
5. Pri izjednačenju ocjena cilj se računa kao lošije rangiran (konzervativno). Nepogođen cilj (osnovna metoda ne pronalazi obavijest uopće) računa se kao promašaj.

## Rezultati

- Razdoblje ciljeva: **2023-11 – 2026-11** (37 mjeseci)
- Broj ocijenjenih parova pobjednik–cilj: **n = 30017** (od toga 26179 s barem jednom NKD djelatnošću, 3838 bez – računaju se kao promašaj)
- Prosječan broj kandidata po cilju: 627

| Metoda | recall@10 | recall@20 |
|---|---:|---:|
| **Birokratko (prilagodba S/C/G/T)** | 8.6 % | 14.6 % |
| Osnovna: Postgres full-text | 4.7 % | 7.2 % |
| Slučajan poredak (očekivanje) | 1.6 % | 3.3 % |

Samo pobjednici s NKD profilom (isključeni oni bez djelatnosti):

| Metoda | recall@10 | recall@20 |
|---|---:|---:|
| Birokratko | 9.9 % | 16.7 % |
| Full-text | 5.4 % | 8.2 % |

Medijan ranga cilja (Birokratko): 126.0

### Obuhvat podataka

- parova (pobjednik, obavijest) s identifikatorom pobjednika: 95337
- od toga valjan OIB: 95296
- od toga pronađen u `company`: 93261
- od toga povezano s natječajnom obavijesti (`procedure-identifier`): 30017
- kalibracija S: 5. percentil = 0.75657, 95. percentil = 0.82407

## Prag tau (tržišno sondiranje)

Prag `tau` odabran je maksimizacijom F1 između djelatnosti pobjednika i CPV odjeljka u kojem su dobili ugovor (2070 pobjednika, 2934 parova pobjednik–odjeljak).

- **tau = 0.8947**, F1 = 0.1323, preciznost = 0.0955, odziv = 0.2154 (TP 632, FP 5987, FN 2302)
- pretraženi raspon: 0.8691 – 0.9266 (201 korak)

## Ograničenja

- **Procurjevanje u povezivanju NKD→CPV.** Sličnost se računa i iz tekstova obavijesti (do 200 po CPV prefiksu), među kojima su i ciljne obavijesti. To blago povoljno utječe na komponentu C.
- **Prag tau je odabran na istom skupu pobjednika** na kojem se prikazuje F1 (nema odvojenog testnog skupa).
- **Starost registra.** Podaci o tvrtkama potječu iz snimke Sudskog registra navedene na stranici *Izvori* (testno okruženje portala). Pobjednici koji su osnovani poslije snimke, ili više ne postoje, nisu u `company` i ne ulaze u vrednovanje; tvrtke u stečaju/likvidaciji namjerno nisu pohranjene.
- **Pokrivenost TED-a.** Obavijesti o dodjeli prije otprilike veljače 2024. imaju stariji format bez podataka o pobjednicima (API ih ne vraća), pa vrednovanje počinje kad se podaci pojave.
- **Pobjednik po postupku, ne po grupi.** Cilj je cijela natječajna obavijest; ne provjerava se jesu li ponuđene sve grupe.
- **Tvrtke bez NKD djelatnosti** (slobodni tekst predmeta poslovanja se ne pohranjuje) ne mogu se ocijeniti i računaju se kao promašaj u glavnoj tablici.
- **Mjesečna granulacija.** Kandidati su sve obavijesti istog mjeseca; korisnik u praksi vidi otvorene natječaje, što je manji skup.
- Rezultat opisuje mogućnost rangiranja stvarnih pobjednika; ne dokazuje da je tvrtka *trebala* pobijediti.
