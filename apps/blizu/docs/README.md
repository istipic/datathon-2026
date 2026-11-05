# Blizu

**Što ti je blizu?** — za svaku adresu u Gradu Zagrebu Blizu pokazuje koliko je minuta hoda do svakodnevnih
javnih usluga (liječnik, ljekarna, vrtić, škola, knjižnica, pošta, javni prijevoz, park, trgovina) za četiri
persone (opće, starija osoba, roditelj s djetetom, invalidska kolica), a gradskim planerima pokazuje gdje je
nezadovoljena potreba najveća i gdje bi 1–5 novih ustanova koristilo najviše ljudi.

Datathon Portala otvorenih podataka 2026., izazov A „Društvo i javne usluge”. Kod: EUPL-1.2.

## Arhitektura

```
 data.gov.hr (CKAN)  ZET GTFS  OpenStreetMap (Overpass / Geofabrik)  Eurostat Census 2021 grid
        │                │                    │                                │
        └────────────────┴───── blizu ingest (Typer CLI) ──────────────────────┘
                                      │
              PostgreSQL+PostGIS ◄────┤────► data/derived: graph_*.npz, access_*.npz, manifest.json
              (facility, cell, cell_access,    (scipy CSR grafovi, udaljenosti čvor→najbliži objekt)
               gtfs_stop_frequency,
               vrtic_free_places, provenance)
                                      │
                         FastAPI  /api/v1  (učitava .npz pri pokretanju)
                                      │
                       React SPA (Vite, @dt/ui)  ◄── Caddy (CSP, /api proxy)
```

- `api/` — paket `blizu_api` (uv workspace član `blizu-api`), ASGI app `blizu_api.main:app`, CLI `blizu`.
- `web/` — paket `blizu-web` (React 18, Vite, TypeScript strict, Tailwind 3, `@dt/ui`).
- Konvencije su iz [docs/FOUNDATION.md](../../../docs/FOUNDATION.md); paket se zove `blizu_api` (a ne `blizu`)
  zbog toga što `infra/python-api.Dockerfile` i `make` pretpostavljaju `<app>_api`.

## Izvori podataka

| ID                          | Izvor                                                                                 | Razina      | Licencija                         | Svježina u trenutku izrade       |
| --------------------------- | ------------------------------------------------------------------------------------- | ----------- | --------------------------------- | -------------------------------- |
| `zg-vrtici`                 | CKAN `geoportal-djecji-vrtici` (CSV, EPSG:4326 potvrđen vrijednostima)                | službeni    | CC BY 4.0                         | resurs iz 23.06.2022. (**star**) |
| `zg-vrtici-mjesta`          | CKAN `slobodna-mjesta-u-vrticima-…`, `newest_resource(CSV)`                           | službeni    | Otvorena dozvola (OD)             | stanje 01.01.2025.               |
| `zg-skole`                  | CKAN `djeji-vrtii-osnovne-i-srednje-kole-…-inspire` → INSPIRE WFS, `primaryEducation` | službeni    | nije navedena u CKAN metapodacima | dohvaćeno uživo, 177 objekata    |
| `zet-gtfs`                  | https://zet.hr/gtfs-scheduled/latest                                                  | službeni    | nije navedena uz feed             | feed 21.10.2026.                 |
| `osm-zagreb`                | OSM: pješačka mreža + 6 kategorija objekata                                           | zajednica   | ODbL 1.0                          | trenutak preuzimanja             |
| `eurostat-census-grid-2021` | Eurostat GISCO Census 2021, mreža 1 km (V3)                                           | EU službeni | Eurostat (navesti izvor)          | V3, 19.06.2026.                  |
| `blizu-derived-graph`       | izvedeno: pješački graf (puni / za kolica), udaljenosti, ćelije                       | izvedeno    | ODbL (izvedena baza)              | trenutak izrade                  |

Dokazi sondiranja (sirovi odgovori s datumom) su u [`../data/evidence/`](../data/evidence/); testovi koriste
isključivo snimljene stvarne odgovore (`api/tests/fixtures/`, `web/src/__fixtures__/`).

**Ograničenja izvora koja su važna za tumačenje**

- Registar vrtića je iz 2022. (pouzdanost se zbog toga umanjuje, vidi `scoring.yaml`); privatni i vjerski vrtići
  su u registru, ali ne u tablici slobodnih mjesta (spajanje je po nazivu ustanove, `rapidfuzz` ≥ 90).
- INSPIRE izvor za škole **nema nazive ni adrese**: nazivi se, gdje postoji OSM objekt unutar 50 m, preuzimaju iz
  OpenStreetMapa (110 od 177 imenovano); ostali se prikazuju kao „Osnovna škola (naziv nije u izvoru)”.
- Potpunost OSM-a (liječnici, ljekarne, pošte, knjižnice, parkovi, trgovine) ovisi o volonterima.
- Mreža stanovništva je 1 km²: ne znamo gdje u ćeliji ljudi žive; ćelije na granici Zagreba mogu sadržavati
  stanovnike susjednih općina (centroid ćelije mora biti unutar granice Grada Zagreba).
- Pristupačnost za kolica izvodi se samo iz OSM oznaka (`highway=steps`, `wheelchair=no`).

## Pokretanje (razvoj)

```bash
cp .env.example .env                 # POSTGRES_PASSWORD, CONTACT_EMAIL
make dev                             # PostgreSQL+PostGIS+pgvector, Mailpit
uv sync                              # (uv sync --extra semantic za semantičku pretragu)
make migrate APP=blizu               # Alembic: tablice jezgre + Blizu
make ingest  APP=blizu STEP=all      # sources, graph, facilities, gtfs, access, grid
uv run --package blizu-api uvicorn blizu_api.main:app --port 8010   # API (port 8000 može biti zauzet)
pnpm install && BLIZU_API_URL=http://127.0.0.1:8010 pnpm --filter blizu-web dev   # SPA na :5173
```

Korisne varijable (`apps/blizu/.env.example`): `DATABASE_URL`, `CONTACT_EMAIL`, `NOMINATIM_URL`, `HF_HOME`,
`CORS_ORIGINS`, `DATA_DIR`, `OSM_FEATURE_SOURCE` (`auto` | `overpass` | `geofabrik`), `SEMANTIC_SEARCH`,
`RATE_LIMIT`. Na Windowsu koristite `127.0.0.1`, ne `localhost`.

### Koraci unosa (`blizu ingest <korak>`)

| Korak        | Što radi                                                                                                                                                        | Tipično trajanje                                    |
| ------------ | --------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------- |
| `sources`    | registrira `data_source` redove (naslov, izdavač, licencija čitaju se iz CKAN metapodataka)                                                                     | 2 s                                                 |
| `graph`      | pješačka mreža Grada Zagreba → dva neusmjerena CSR grafa u EPSG:3765 (`graph_*.npz`): osmnx/Overpass, a ako Overpass ne odgovori, Geofabrik ekstrakt (`osmium`) | osmnx: 1–5 min kad Overpass radi; ekstrakt: ≈ 3 min |
| `facilities` | vrtići (CSV), škole (WFS), OSM kategorije; dedupliciranje službeno ≻ OSM u 50 m; slobodna mjesta                                                                | 20–30 s                                             |
| `gtfs`       | referentna srijeda, polasci 07–09 h / 2 po stajalištu (roditeljska stanica), ≥ 6/h = „prijevoz”                                                                 | 6 s                                                 |
| `access`     | snap objekata na čvor (≤ 200 m), `dijkstra(min_only, limit=4000)` po varijanti i kategoriji                                                                     | 2 s                                                 |
| `grid`       | Eurostat mreža za Hrvatsku → ćelije unutar Zagreba → prosječne minute po ćeliji/personi/kategoriji                                                              | 25–60 s (566 MB preuzimanje)                        |

**Overpass.** Javni Overpass poslužitelji su povremeno preopterećeni (502/504, ConnectTimeout); u razvoju su bili
nedostupni satima (jedan `graph_from_place` trajao je 77 minuta). Zato `OSM_FEATURE_SOURCE=auto` (zadano) radi
ovako: jedan pokušaj Overpassa (graf: 3 min; objekti: 2 pokušaja po 90 s), pa **Geofabrik ekstrakt Hrvatske**
(`croatia-latest.osm.pbf`, ≈ 200 MB) čitan s `osmium` — za graf (`graph_pbf.py`, isti „walk” filter kao osmnx,
najveća povezana komponenta, 344 tis. čvorova) i za objekte. Graf iz ekstrakta daje iste mrežne udaljenosti kao osmnx
graf (medijan omjera 1,000; p10 0,965; p90 1,01 na 40 parova). Vidi
[ADR 0005](../../../docs/adr/0005-geofabrik-fallback-for-osm-features.md). Svaki korak upisuje `ingestion_run`
(uključujući neuspjele) i datoteku u `data/derived/manifest.json` (`graph.via`, `osm_via`).

**Izmjereno:** `make ingest APP=blizu STEP=all` od nule (nova baza, prazan `DATA_DIR`, bez osmnx cachea) uz
nedostupan Overpass: **466 s (7,8 min)**, izlaz 0, sedam izvora s uspješnim `ingestion_run`.

## API (`/api/v1`)

| Ruta                                                        | Opis                                                                                                             |
| ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------- |
| `GET /geocode?q=`                                           | Nominatim (ograničen na Zagreb), 1 zahtjev/s, cache 30 dana; vraća `title`, `label`, koordinate                  |
| `GET /access?lat&lon&persona`                               | indeks, ocjena, pouzdanost, 9 kategorija (minute, ocjena, težina, najbliži objekt, razina, starost)              |
| `GET /compare?a=lat,lon&b=…`                                | dvije adrese, razlike po kategorijama                                                                            |
| `GET /facilities?category&bbox`                             | GeoJSON (najviše 2000 značajki)                                                                                  |
| `GET /plan/need?category&persona`                           | GeoJSON ćelija (`pop_group`, `mean_minutes`, `unmet`) + sažetak i kvantilni pragovi                              |
| `GET /isochrone?lat&lon&persona&max_min=15`                 | ulice u dosegu pješice po vremenskim kantama od 15 s, objekti u dosegu i brojevi 5/10/15/20 min (`max_min` 5–20) |
| `GET /route?lat&lon&persona&category` (ili `&facility_id=`) | najkraći pješački put do najbližeg objekta kategorije: `minutes`, `distance_m`, `facility`, `coordinates`        |
| `POST /plan/optimise`                                       | `{category, persona, k: 1..5}` → lokacije, `+N osoba`, udio prije/poslije, `cells` (po ćeliji prije/poslije)     |
| `GET /search?q=`                                            | top 3 kategorije (semantički `multilingual-e5-small`; inače ključne riječi); `method` u odgovoru                 |
| `GET /kindergartens/free-places`                            | slobodna mjesta spojena s registrom; nespojeni redovi posebno                                                    |
| `GET /scoring`                                              | `scoring.yaml` (verzionirana konfiguracija bodovanja)                                                            |
| `GET /health`, `GET /api/v1/sources`                        | iz jezgre; izvori s datumom dohvaćanja i starošću podataka                                                       |

Greške su `application/problem+json`. Adresa izvan Grada Zagreba ili dalja od 300 m od pješačke mreže → 422.
Granica „60/min po IP-u” iz jezgre je podesiva (`RATE_LIMIT`; produkcijski `docker-compose.prod.yml` koristi 300/min).
Ako podaci još nisu učitani, API radi i vraća 503 „Podaci se još učitavaju.”.

### Ugovori za animaciju karte (v2)

Tri odgovora daju karti samo stvarne brojeve (isti graf, ista snimka objekata i isti `snap` kao `/access`).
Snimljeni odgovori za Trg bana Jelačića su u `web/src/__fixtures__/2026-11-05_*.json`; OpenAPI (`/openapi.json`)
opisuje parametre i oblik odgovora.

**`GET /isochrone?lat&lon&persona&max_min=15`** (`max_min` cijeli broj 5–20). Jedan Dijkstra
(`scipy.sparse.csgraph.dijkstra`, `limit = max_min·60·brzina − udaljenost_snapa`) na grafu persone (kolica: graf bez
stepenica). Vrijeme čvora je `(udaljenost snapa + mrežna udaljenost) / brzina`, dakle isto kao u `/access`. Brid (u, v)
ulazi u kantu `ceil(min(t_u, t_v) / 0,25) · 0,25` i crta se kao ravna dužina između čvorova (graf pamti jedan brid po
paru čvorova); bridovi čiji je dalji kraj izvan granice se izostavljaju; koordinate imaju 5 decimala; najmanja kanta je
0,25 pa je kanti najviše `4·max_min` (≤ 80).

```json
{
  "origin": {"lon": 15.9772, "lat": 45.8131, "snapped_m": 8.9},
  "persona": "starija", "speed_mps": 0.9, "max_min": 15, "bucket_min": 0.25,
  "buckets": {"type": "FeatureCollection", "features": [
    {"type": "Feature", "properties": {"t": 0.25}, "geometry": {"type": "MultiLineString", "coordinates": [[[lon, lat], [lon, lat]], ...]}}
  ]},
  "facilities": [{"id": 7527, "category": "ljekarna", "name": "…", "t": 1.4, "lon": 15.97785, "lat": 45.81362}],
  "counts": {"5": {"ljekarna": 2}, "10": {"ljekarna": 4, "skola": 1}, "15": {}}
}
```

- `facilities[].id` je **cijeli broj** (isti id kao u `/facilities`); `t` su minute hoda zaokružene na 0,1 kao `minutes` u
  `/access` (park se doseže preko najbližeg pristupnog čvora). Popis uključuje sve objekte svih kategorija s `t ≤ max_min`,
  poredane po `t`. Objekti se na čvorove vežu istom funkcijom i udaljenošću (≤ 200 m) kao polja `access_*.npz`.
- `counts` je kumulativan po kategoriji za pragove 5/10/15/20 koji su ≤ `max_min`; kategorije bez objekata u dosegu
  se izostavljaju (`{}` znači „ništa u dosegu”). Najbliži objekt kategorije ima `t` jednak minutama iz `/access` (±0,1;
  provjereno na 221 paru adresa × kategorija iz stvarnih podataka bez razlike).
- Odgovor se sprema u LRU (64 izokrone, ključ = (lat, lon na 5 decimala, persona, `max_min`)) kao već serijalizirani
  JSON, pa je topli odgovor ≈ 4 ms. Izmjereno na stvarnom grafu (344 tis. čvorova): hladno 35–200 ms, najveći odgovor
  284 kB (opće, 20 min, centar), 89 kB za starije 15 min.

**`GET /route?lat&lon&persona&category`** (ili `&facility_id=`). Najbliži objekt kategorije (ili zadani objekt) i put
po Dijkstrinim prethodnicima, uz isti limit od 4 km kao `/access`. Odgovor: `persona`, `category`, `speed_mps`, `origin`,
`minutes` i `distance_m` (**jednaki** kao u `/access`, uključuju udaljenost snapa), `facility`
(`id`, `category`, `name`, `address`, `lon`, `lat`, `source_id`, `tier`) i `coordinates` (`[lon, lat]` čvorova puta, od
čvora adrese do pristupnog čvora objekta; kad su isti čvor, točka se ponavlja da LineString ostane valjan).

**`POST /plan/optimise` → `cells`**. Uz `sites`, `share_before/after` i `total_newly_covered` odgovor sadrži za svaku 1 km
ćeliju `{cell_id, unmet_before, unmet_after, need_before, need_after}`, računato istom čvornom pokrivenošću kakvu koristi
optimizator. `unmet_*` su **ljudi** ciljne skupine u ćeliji čiji je najbliži objekt dalji od `good_min` minuta hoda
(prije / nakon predloženih lokacija): zbroj `unmet_before − unmet_after` je `total_newly_covered` (±1), a svaka
`unmet_after ≤ unmet_before`. `need_*` su isto u jedinicama `unmet` iz `/plan/need` (`P·(1 − s)`): `need_before` je jednak toj
vrijednosti, a `need_after` oduzima potražnju novopokrivenih čvorova ćelije.

**Greške:** `422` (`application/problem+json`) za adresu izvan Grada Zagreba, dalju od 300 m od mreže, `max_min`
izvan 5–20, nepoznatu personu/kategoriju te `/route` bez `category` i `facility_id` ili s `facility_id` druge
kategorije; `404` za `/route` kad objekt ne postoji, kategorija nema podataka ili je najbliži objekt dalje od 4 km;
`503` dok se podaci učitavaju.

## Bodovanje

`api/src/blizu_api/config/scoring.yaml` (verzija 1) sadrži brzine, pragove g/m i težine po personi; stranica
`/metodologija` prikazuje upravo tu datoteku. Formule: `minute = udaljenost / brzina / 60`;
`s(t)` = 1 do g, 0 od m, linearno između; indeks = `round(100 · Σ w·s / Σ w)` (težine se ponovno normiraju na
kategorije s podacima i težinom > 0); ocjena A ≥ 85, B ≥ 70, C ≥ 55, D ≥ 40, inače E; pouzdanost = faktor razine
(službeni 1,0 / zajednica 0,8) × faktor starosti (≤ 12 mj. 1,0; ≤ 36 mj. 0,85; inače 0,7).

**Planiranje.** Nezadovoljena potreba po ćeliji `U = P · (1 − s(prosječne minute))`, P = ciljna skupina (65+ za liječnike
i ljekarne, djeca do 15 za vrtiće i škole, inače ukupno stanovništvo; bez dobnih skupina koristi se ukupno).
Optimizator: kandidati = čvorovi u naseljenim ćelijama, jedan na ≈ 300 m; potražnja čvora = `U` ćelije podijeljen
jednako na čvorove ćelije; čvor je pokriven ako je nova ustanova unutar `g · brzina · 60` m po mreži; pohlepni MCLP
(`opendata_core.optimize.greedy_mclp`, ≥ 63 % optimuma). Prikazani brojevi su **ljudi** ciljne skupine, a udio
„prije/poslije” i KPI „unutar g minuta” računaju se istom (čvorovnom) definicijom.

## Testovi

```bash
uv run pytest apps/blizu/api                        # 240+ testova, bez mreže (stvarni fixturi)
TEST_DATABASE_URL=… uv run pytest apps/blizu/api    # + testovi koji trebaju PostGIS
uv run --package blizu-api --extra semantic pytest -m slow apps/blizu/api   # pravi e5 model
pnpm --filter blizu-web test                        # 38 vitest testova (+ 7 Playwright)
BLIZU_API_URL=http://127.0.0.1:8010 pnpm --filter blizu-web e2e   # Playwright (treba API + podaci)
uv run --package blizu-api blizu validate           # usporedba s OSRM-om → docs/validation.md
```

Integracijski testovi (`api/tests/test_integration.py`) grade `DataStore` iz **stvarnog** podgrafa od 1 km oko Trga
bana Jelačića (3403 čvora, 8960 bridova), stvarnih objekata i ćelija snimljenih 2026-11-03 te pokreću proizvodne
funkcije (`snap_facilities`, `nearest_facility_distances`, `compute_cell_access`, `Planner`, HTTP API).

## Validacija i kvaliteta

- **Udaljenosti vs OSRM (foot):** 20 nasumičnih parova, MAE 50 m, medijan omjera naša/OSRM 0,991,
  90 % unutar ±20 % — [validation.md](validation.md).
- **API:** `/access` p95 3,8–4,6 ms (100 zahtjeva nakon zagrijavanja, oba grafa); `/plan/optimise` k=3: 3,5 s hladno
  (graf od 344 tis. čvorova, 4 niti), ≈ 20–30 ms iz cachea.
- **Lighthouse (mobilni), `/kartica`:** performanse 85–88, pristupačnost 100, CLS ≈ 0, TBT ≤ 20 ms.
- Karta se prikazuje kroz OpenFreeMap („liberty”), uz OSM raster kao pričuvu i uvijek vidljivu atribuciju
  „© OpenStreetMap contributors”.

## Produkcija

`docker-compose.prod.yml` (servis `blizu-api` + volumen `blizu-data` na `/data`, SPA preko `blizu-web`, Caddy):

```bash
docker compose -f docker-compose.prod.yml up -d --build db
make migrate APP=blizu PROD=1        # alembic u kontejneru
make ingest  APP=blizu STEP=all PROD=1   # unos u volumen /data, zatim restart blizu-api
docker compose -f docker-compose.prod.yml up -d --build
```

Slika API-ja ne uključuje `semantic` ekstra (≈ 1 GB torch); za semantičku pretragu izgradite je s
`--build-arg UV_SYNC_ARGS="--extra semantic"` i postavite `BLIZU_SEMANTIC_SEARCH=true`.

## Poznati nedostaci

- `mypy --strict` nije uključen u CI za `blizu_api` (30 nalaza, uglavnom tipovi `osmium`/`pandas`); jezgra jest.
- Dobne skupine: Eurostat V3 ima `Y_LT15`/`Y_1564`/`Y_GE65`; ako se izvor promijeni, planer automatski pada na
  ukupno stanovništvo i to piše u sučelju.
- Karta nije testirana u jsdom-u (nema WebGL); pokriva je Playwright i ručna provjera u pravom pregledniku.
