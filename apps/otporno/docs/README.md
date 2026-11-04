# Otporko

**Putovnica rizika kućanstva i pregled izloženosti općine** — za adresu bilo gdje u Hrvatskoj Otporko prikazuje
razinu rizika od poplave i vrućine (danas i 2031.–2050.) s konkretnim, citiranim koracima, a općinama i gradovima
broj stanovnika i osoba 65+ po razini rizika, kartu prioriteta i prijedlog lokacija centara za rashlađivanje.

Datathon Portala otvorenih podataka 2026., izazov B „Okoliš i održivi prostor”. Kod: EUPL-1.2.

## Arhitektura

```
 Hrvatske vode WMS   Open-Meteo Climate API   Eurostat Census 2021 grid   GISCO LAU   OpenStreetMap
        │ (samo prikaz)        │ (CMIP6, kvota)           │ (1 km)            │ (556)     (Overpass/Geofabrik)
        └──────────────┬───────┴───────────────────────────┴───────────────────┴────────────┘
                       │   otporno ingest ... (Typer CLI, rezumabilan posao za klimatske točke)
          PostgreSQL+PostGIS: municipality, cell, heat_point, heat_cell, candidate_site,
                              action_rule, precompute_status, api_call_log + provenance
                       │
              FastAPI /api/v1  (passport, municipalities, cells, cooling-centres, sources)
                       │
              React SPA (Vite, @dt/ui, MapLibre)  ◄── Caddy
```

- `api/` — paket `otporno_api` (uv workspace član `otporno-api`), ASGI `otporno_api.main:app`, CLI `otporno`.
- `web/` — paket `otporno-web` (React 18, Vite, TypeScript strict, Tailwind 3). Vlastiti izgled (topla „papirnata”
  podloga, lijeva navigacija, serifni naslovi); dijeli samo pristupačne komponente iz `@dt/ui`.

## Izvori podataka

| ID                          | Izvor                                                 | Uloga                                                         |
| --------------------------- | ----------------------------------------------------- | ------------------------------------------------------------- |
| `hv-flood-2019`             | Hrvatske vode, karte opasnosti od poplava 2019. (WMS) | prikaz karte uz adresu; **razina se ne računa** (ljestvica c) |
| `open-meteo-climate`        | Open-Meteo Climate API, CC BY 4.0, 3 modela CMIP6     | vrući dani (Tmax ≥ 30 °C), tropske noći (Tmin ≥ 20 °C)        |
| `eurostat-census-grid-2021` | Eurostat popis 2021., mreža 1 km (`opendata_core`)    | stanovnici i stanovnici 65+ po ćeliji                         |
| `gisco-lau`                 | GISCO LAU 2024                                        | granice 556 općina i gradova                                  |
| `osm-public-buildings`      | OpenStreetMap (ODbL)                                  | kandidati za centre za rashlađivanje                          |

Odluke i dokazi: [docs/adr/0007-otporno-data-decisions.md](../../../docs/adr/0007-otporno-data-decisions.md),
mapa `apps/otporno/data/evidence/`.

## Pokretanje (razvoj)

```bash
make dev                                          # PostgreSQL + Mailpit
make migrate APP=otporno
uv run --package otporno-api otporno ingest sources
uv run --package otporno-api otporno ingest all-demo          # općine, mreža, pravila, zgrade, Karlovac + Zagreb
uv run --package otporno-api otporno ingest heat-grid --lau HR_01791 --lau HR_01333   # kvota: traje danima, rezumabilno
uv run --package otporno-api otporno ingest heat-cells --lau HR_01791                 # nakon što točke stignu
uv run --package otporno-api python -m uvicorn otporno_api.main:app --port 8020
cd apps/otporno/web && pnpm dev                   # http://127.0.0.1:5175
```

CLI: `ingest sources | municipalities | grid | flood --lau | heat-grid | heat-cells | buildings --lau | actions |
all-demo`, `validate`. `ingest corine` je P1 (požar) i još nije implementiran.

## API (`/api/v1`)

| Ruta                                        | Opis                                                                                   |
| ------------------------------------------- | -------------------------------------------------------------------------------------- |
| `GET /geocode?q=`                           | adresa u cijeloj Hrvatskoj (Nominatim, cache 30 dana)                                  |
| `GET /passport?lat=&lon=`                   | poplava (WMS metapodaci), vrućina, požar (nedostupno), akcije s izvorima; 422 izvan HR |
| `GET /municipalities?q=`                    | pretraga općina                                                                        |
| `GET /municipalities/{lau}/exposure`        | stanovnici / 65+ po razini; `status` ready · computing · unavailable                   |
| `POST /municipalities/{lau}/compute`        | pokreće izračun u pozadini (idempotentno)                                              |
| `GET /cells?lau=&w_flood=&w_heat=&w_fire=`  | GeoJSON ćelija s prioritetom (težine zbroj 1 ± 0,01, inače 422)                        |
| `POST /cooling-centres {lau_id,k,min_band}` | prijedlog 1–5 lokacija, pokrivenost 415 m                                              |
| `GET /health/climate-quota`                 | potrošnja Open-Meteo kvote i broj spremljenih točaka                                   |
| `GET /sources`, `GET /health`               | provenijencija izvora, zdravlje                                                        |

## Testovi

```bash
TEST_DATABASE_URL=postgresql+psycopg://postgres:<lozinka>@127.0.0.1:5432/otporno_test uv run pytest apps/otporno/api
cd apps/otporno/web && pnpm test && pnpm exec playwright test   # smoke traži API na :8020 (npr. nad otporno_test)
```

Fixture su stvarni snimljeni odgovori (Open-Meteo 45,5 N 15,5 E, HV WMS capabilities, ćelije/objekti Karlovca,
24 točke mreže, odgovori API-ja od 2026-11-04). Baza mora imati ime koje završava na `_test`.

## Poznata ograničenja

- Poplava: razina se ne određuje (WMS nije upitljiv, nema WFS-a ni vektora); prikazuje se samo karta.
- Besplatna kvota Open-Meteo punu usporednu mrežu puni danima; do tada je rangiranje približno i pouzdanost niža.
- Točka adrese zaokružuje se na 0,1° (oko 10 km): rezultat opisuje okolicu, ne zgradu.
- Ćelije od 1 km dodjeljuju se općini po središtu; rubne ćelije mogu uključivati susjedne stanovnike.
- P1 (požar CORINE, DHMZ uživo, općinsko izvješće) nije izrađen.
