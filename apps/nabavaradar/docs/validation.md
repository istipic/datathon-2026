# Birokratko – validacija

_Generirano naredbom `nabavaradar eval` (2026-11-04T23:13:22.157654+00:00). Brojevi se ne uređuju ručno._

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
- Broj ocijenjenih parova pobjednik–cilj: **n = 30009** (od toga 26173 s barem jednom NKD djelatnošću, 3836 bez – računaju se kao promašaj)
- Prosječan broj kandidata po cilju: 624

| Metoda | recall@10 | recall@20 |
|---|---:|---:|
| **Birokratko (prilagodba S/C/G/T)** | 10.6 % | 17.9 % |
| Osnovna: Postgres full-text | 4.7 % | 7.2 % |
| Slučajan poredak (očekivanje) | 1.6 % | 3.3 % |

Samo pobjednici s NKD profilom (isključeni oni bez djelatnosti):

| Metoda | recall@10 | recall@20 |
|---|---:|---:|
| Birokratko | 12.2 % | 20.5 % |
| Full-text | 5.4 % | 8.2 % |

Medijan ranga cilja (Birokratko): 89.0

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

## Prilagodba rangiranja

Svaka izmjena mjerena je istim protokolom na istim parovima (n = 30017); prihvaćena je samo ako nijedna mjera nije pogoršana. Sirovi rezultati: `data/evidence/2026-11-05_fit_tuning.json`.

| Varijanta | recall@10 | recall@20 | razlika @10 | razlika @20 |
|---|---:|---:|---:|---:|
| stanje prije izmjena (težine 0,55/0,25/0,10/0,10, sve djelatnosti jednako) | 8.6 % | 14.6 % |  |  |
| sporedne djelatnosti x 0,85 | 9.6 % | 15.9 % | +0.91 p.b. | +1.36 p.b. |
| sporedne djelatnosti x 0,70 | 10.0 % | 16.7 % | +1.34 p.b. | +2.12 p.b. |
| sporedne djelatnosti x 0,60 | 10.2 % | 17.2 % | +1.51 p.b. | +2.61 p.b. |
| sporedne djelatnosti x 0,50 | 10.3 % | 17.5 % | +1.62 p.b. | +2.94 p.b. |
| bonus CPV skupine +0,25 (10 najbližih skupina) | 8.8 % | 14.9 % | +0.15 p.b. | +0.31 p.b. |
| bonus CPV skupine +0,50 (5 najbližih skupina) | 8.8 % | 15.0 % | +0.12 p.b. | +0.45 p.b. |
| isključene obavijesti tipa cn-desg (natječaji za idejna rješenja) | 8.7 % | 14.6 % | +0.01 p.b. | +0.03 p.b. |
| x 0,70 + bonus skupine 0,25 + isključen cn-desg | 10.3 % | 17.1 % | +1.66 p.b. | +2.53 p.b. |
| x 0,60 + bonus skupine 0,25 + isključen cn-desg | 10.5 % | 17.5 % | +1.83 p.b. | +2.99 p.b. |
| x 0,50 + bonus skupine 0,25 + isključen cn-desg  (ODABRANO) | 10.6 % | 17.9 % | +1.98 p.b. | +3.31 p.b. |
| x 0,40 + bonus skupine 0,25 + isključen cn-desg | 10.7 % | 18.1 % | +2.03 p.b. | +3.50 p.b. |
| x 0,30 + bonus skupine 0,25 + isključen cn-desg | 10.7 % | 18.1 % | +2.03 p.b. | +3.54 p.b. |
| x 0,50 + bonus skupine 0,50 (5 skupina) + isključen cn-desg | 10.6 % | 17.8 % | +1.97 p.b. | +3.29 p.b. |

Veći popust za sporedne djelatnosti pomaže sve do oko 0,4; ispod 0,5 dobitak je zanemariv, pa je odabrano 0,5 (sporedne djelatnosti ostaju značajne). Bonus CPV skupine i isključenje obavijesti tipa `cn-desg` daju male, ali dosljedne dobitke. Grupiranje obavijesti istog postupka i „Ne zanima me” ne mijenjaju ovu mjeru (djeluju na prikaz, ne na rang pobjednika).

Konfiguracija u primjeni (`config/fit.yaml`) pri ovom izračunu: težine {'S': 0.55, 'C': 0.25, 'G': 0.1, 'T': 0.1}, popust sporednih djelatnosti 0.5, bonus CPV skupine 0.25 (najbližih 10), isključeni tipovi ['cn-desg'].

## Ograničenja

- **Procurjevanje u povezivanju NKD→CPV.** Sličnost se računa i iz tekstova obavijesti (do 200 po CPV prefiksu), među kojima su i ciljne obavijesti. To blago povoljno utječe na komponentu C.
- **Prag tau je odabran na istom skupu pobjednika** na kojem se prikazuje F1 (nema odvojenog testnog skupa).
- **Starost registra.** Podaci o tvrtkama potječu iz snimke Sudskog registra navedene na stranici *Izvori* (testno okruženje portala). Pobjednici koji su osnovani poslije snimke, ili više ne postoje, nisu u `company` i ne ulaze u vrednovanje; tvrtke u stečaju/likvidaciji namjerno nisu pohranjene.
- **Pokrivenost TED-a.** Obavijesti o dodjeli prije otprilike veljače 2024. imaju stariji format bez podataka o pobjednicima (API ih ne vraća), pa vrednovanje počinje kad se podaci pojave.
- **Pobjednik po postupku, ne po grupi.** Cilj je cijela natječajna obavijest; ne provjerava se jesu li ponuđene sve grupe.
- **Tvrtke bez NKD djelatnosti** (slobodni tekst predmeta poslovanja se ne pohranjuje) ne mogu se ocijeniti i računaju se kao promašaj u glavnoj tablici.
- **Mjesečna granulacija.** Kandidati su sve obavijesti istog mjeseca; korisnik u praksi vidi otvorene natječaje, što je manji skup.
- Rezultat opisuje mogućnost rangiranja stvarnih pobjednika; ne dokazuje da je tvrtka *trebala* pobijediti.
