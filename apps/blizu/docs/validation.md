# Validacija pješačkih udaljenosti (Blizu)

Generirano: 2026-11-03T22:09:48+00:00 (UTC), naredba `blizu validate`.

**Status:** OK

## Metoda

- 20 nasumičnih parova (čvor mreže → najbliži objekt kategorije), `seed = 2026`; izuzeti su parkovi (više pristupnih točaka) i trivijalni parovi (< 300 m, > 3,5 km).
- _Naša udaljenost_: najkraći put po grafu Blizu (OSM pješačka mreža, `scipy` Dijkstra, puni graf).
- _Referenca_: OSRM profil za pješake, `https://routing.openstreetmap.de/routed-foot/route/v1/driving/…` (profil „foot” poslužitelja routing.openstreetmap.de), najviše 1 zahtjev u sekundi.
- Isti OSM podaci, ali drukčiji algoritam i drukčije čišćenje mreže, pa se razlike očekuju (OSRM sam „hvata” točke na svoju mrežu).

## Rezultat

| Pokazatelj                        | Vrijednost |
| --------------------------------- | ---------- |
| Valjanih parova                   | 20         |
| MAE (m)                           | 50         |
| Srednja pogreška (naša − OSRM, m) | -46        |
| Medijan omjera (naša / OSRM)      | 0.991      |
| Udio unutar ±20 %                 | 90 %       |

## Parovi

| #   | Kategorija | Naša (m) | OSRM (m) | Omjer |
| --- | ---------- | -------: | -------: | ----: |
| 1   | ljekarna   |      698 |      704 | 0.992 |
| 2   | prijevoz   |      761 |      971 | 0.783 |
| 3   | namirnice  |      741 |      955 | 0.777 |
| 4   | knjiznica  |      557 |      558 | 0.998 |
| 5   | namirnice  |      921 |      923 | 0.998 |
| 6   | posta      |     1036 |     1053 | 0.984 |
| 7   | ljekarna   |      458 |      470 | 0.974 |
| 8   | ljekarna   |     2329 |     2376 | 0.980 |
| 9   | knjiznica  |     1436 |     1394 | 1.030 |
| 10  | posta      |     1042 |     1185 | 0.879 |
| 11  | ljekarna   |      316 |      316 | 0.998 |
| 12  | namirnice  |      371 |      444 | 0.837 |
| 13  | namirnice  |      682 |      689 | 0.990 |
| 14  | knjiznica  |      483 |      485 | 0.995 |
| 15  | lijecnik   |     1841 |     1847 | 0.997 |
| 16  | skola      |     1711 |     1799 | 0.951 |
| 17  | vrtic      |      841 |      842 | 0.999 |
| 18  | skola      |      337 |      337 | 0.999 |
| 19  | knjiznica  |     2147 |     2274 | 0.944 |
| 20  | prijevoz   |      319 |      319 | 0.999 |
