# Birokratko

**Natječaji koji odgovaraju tvojoj djelatnosti.** Za tvrtku (po OIB-u) Birokratko rangira otvorene javne natječaje
prema upisanim NKD djelatnostima i objašnjava zašto (sličnost opisa, CPV područje, lokacija, preostalo vrijeme), uz
povijesnu konkurenciju za svaki natječaj. Javnom naručitelju procjenjuje tržište dobavljača po županijama i povijesnu
konkurenciju prije objave nabave.

Datathon Portala otvorenih podataka 2026., izazov C „Gospodarstvo i učinkovito upravljanje”. Kod: EUPL-1.2.

> **Naziv.** Aplikacija se prije zvala NabavaRadar; vidljivo ime je sada **Birokratko** (sučelje, e-pošta, OpenAPI,
> dokumentacija). Tehnički identifikatori ostaju `apps/nabavaradar`, paket `nabavaradar_api`, CLI `nabavaradar`,
> baza `nabavaradar` i varijable `NABAVARADAR_*`, da migracije, `docker-compose.prod.yml` i `make APP=nabavaradar`
> rade nepromijenjeni. Sučelje je 2026-11-04 preoblikovano u „službeni dosje” (crna traka, bordo žig, numerirane
> kartice, ravnalo umjesto trake postotka), različito od Blizua i Otporka.

> **Važno o podacima.** Podaci o tvrtkama iz Sudskog registra dolaze iz **testnog okruženja portala (snimka od
> 2024-06-16)**: produkcijski pristupni podaci vraćaju HTTP 401 dok račun nije potvrđen. Aplikacija to svugdje
> prikazuje. Vidi [ADR 0006](../../../docs/adr/0006-nabavaradar-data-decisions.md).

## Arhitektura

```
 Sudski registar (API v3)   TED Search API v3    CPV 2008 (xlsx)    CKAN registri ugovora (P1)
        │                         │                    │                      │
        └──────────── nabavaradar ingest (Typer CLI) ──┴──────────────────────┘
                                   │   embed (multilingual-e5-small) · crosswalk · calibrate · stats
        PostgreSQL + pgvector ◄────┤   eval → docs/validation.md + config/market.yaml
        company, company_activity, │
        nkd, cpv, notice, award,   │
        crosswalk, competition_stat,│
        subscription, provenance   ▼
                         FastAPI /api/v1  (indeks otvorenih natječaja u memoriji, red za upite prema registru 6/min)
                                   │
                    React SPA (Vite, @dt/ui)  ◄── Caddy (CSP, /api proxy)
```

- `api/` — paket `nabavaradar_api` (uv workspace član `nabavaradar-api`), ASGI `nabavaradar_api.main:app`, CLI `nabavaradar`.
- `web/` — paket `nabavaradar-web` (React 18, Vite, TypeScript strict, Tailwind 3, `@dt/ui`; marka `#4F46E5`, brojevi u IBM Plex Mono).
- `data/evidence/` — sirovi odgovori izvora s datumom (spec Sudrega i vodič, OpenAPI TED-a, uzorci, probe); `api/tests/fixtures/` — stvarni snimljeni odgovori za testove.

## Izvori

| ID                    | Izvor                                                                                                                                                                                                                                 | Razina      | Napomena                                                                       |
| --------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | ----------- | ------------------------------------------------------------------------------ |
| `sudreg`              | Sudski registar, javni servis v3 (`/subjekti`, `/tvrtke`, `/sjedista`, `/pretezite_djelatnosti`, `/predmeti_poslovanja`, `/evidencijske_djelatnosti`, `/nacionalna_klasifikacija_djelatnosti`, `/pravni_oblici`, `/detalji_subjekta`) | službeni    | **testno okruženje**, snimka 1 od 2024-06-16; imena polja iz OpenAPI-ja v3.0.4 |
| `ted-competition`     | TED `POST /v3/notices/search`, `buyer-country=HRV`, `cn-*`                                                                                                                                                                            | EU službeni | polja u `config/ted_fields.yaml` s uzorcima iz snimljenih odgovora             |
| `ted-result`          | isto, `can-*`                                                                                                                                                                                                                         | EU službeni | obavijesti prije ~02/2024 nemaju podatke o pobjednicima                        |
| `cpv-2008`            | `https://ted.europa.eu/documents/d/ted/cpv_2008_xls` (službeni xlsx)                                                                                                                                                                  | EU službeni | 9 454 šifre, svi hrvatski nazivi (fallback na engleski nije bio potreban)      |
| `municipal-registers` | CKAN `package_search(q='registar ugovora javna nabava', rows=100)` (P1)                                                                                                                                                               | zajednica   | izvješće o pokrivenosti: `GET /api/v1/municipal/coverage`                      |
| `nabavaradar-derived` | crosswalk NKD→CPV, statistika konkurencije, kalibracija                                                                                                                                                                               | izvedeni    |                                                                                |

NKD šifrarnik dolazi **iz API-ja registra** (`/nacionalna_klasifikacija_djelatnosti`), pa fallback na DZS NKD 2007 ni
Eurostat NACE nije bio potreban.

## Pokretanje

```bash
make dev                                   # PostgreSQL (pgvector) + Mailpit
cp apps/nabavaradar/.env.example .env      # ili dopuni korijenski .env: DATABASE_URL (.../nabavaradar), SUDREG_*, CONTACT_EMAIL
make migrate APP=nabavaradar
# redoslijed učitavanja (sve naredbe su idempotentne):
make ingest APP=nabavaradar STEP=sources
make ingest APP=nabavaradar STEP=cpv
make ingest APP=nabavaradar STEP=sudreg    # ~4,5 min, jedna snimka za sve tablice
make ingest APP=nabavaradar STEP=ted       # ~3,5 min (COMPETITION_DAYS=1100 za povijest potrebnu validaciji)
make ingest APP=nabavaradar STEP=derive    # embeddinzi (CPU, desetci minuta prvi put; nastavlja se nakon prekida), crosswalk, kalibracija, statistika
make ingest APP=nabavaradar STEP=municipal # P1
uv run --package nabavaradar-api python -m nabavaradar_api.cli eval   # validacija → docs/validation.md
uv run --package nabavaradar-api uvicorn nabavaradar_api.main:app --port 8000
pnpm --filter nabavaradar-web dev          # SPA na :5173 (proxy na API)
```

Raspored (cron, vidi `deploy/crontab`): TED svaki dan u 06:00 (inkrementalno), `derive` u 06:30, tjedni sažetak
ponedjeljkom u 07:00 (`nabavaradar digest send`).

## API (`/api/v1`)

| Ruta                                                   | Opis                                                                                                           |
| ------------------------------------------------------ | -------------------------------------------------------------------------------------------------------------- |
| `GET /company/{oib}`                                   | profil iz baze, inače živi `detalji_subjekta` kroz red (6/min); **202 + `Retry-After`** dok čeka; nema osoba   |
| `GET /match?oib=&q=&county=&deadline_min_days=&limit=` | rangirani otvoreni natječaji s `fit`, `components{S,C,G,T}`, `best_activity`, `competition{…}`; 30/min po IP-u |
| `GET /notices/{pub_no}`                                | pojedinosti, konkurencija CPV skupine, dodjele po grupama (pobjednici samo ako su tvrtke u registru)           |
| `GET /competition?cpv=&nuts2=`                         | medijan ponuda, udio jedne ponude, n, oznaka „niska konkurencija”                                              |
| `POST /sounding`                                       | `{text\|cpv, county}` → CPV prijedlozi, sposobni dobavljači po županijama, konkurencija, savjeti s izvorima    |
| `POST/GET/DELETE /subscriptions`                       | tjedni sažetak, dvostruka potvrda, odjava tokenom (P1)                                                         |
| `GET /validation`, `/sources`, `/status`, `/health`    | rezultati zadnje validacije, izvori s svježinom, brojevi i datumi podataka                                     |
| `GET /cpv?q=`, `GET /counties`                         | CPV odabir, popis županija                                                                                     |

Validacija ulaza: OIB (kontrolna znamenka, 422 prije bilo kojeg vanjskog poziva), CPV `^\d{8}(-\d)?$` ili prefiks od 2–8
znamenki, županije iz fiksnog popisa (`config/counties.yaml`, DGU šifre ↔ NUTS3, provjereno prema Eurostat GISCO),
tekst ≤ 2000 znakova, e-adresa RFC 5322 (osnovno).

## Formula

`prilagodba = 0,55·S + 0,25·C + 0,10·G + 0,10·T` — S: najveći kosinus djelatnost↔natječaj, skaliran 5.–95. percentilom
(pohranjeno pri učitavanju); C: CPV odjeljak u top-3 (1,0) / top-10 (0,5) crosswalka; G: ista županija 1,0, ista regija
0,5, inače 0,2, nepoznato 0,5; T: 1,0 od 15 dana, linearno do 0 na 3 dana, istekli izuzeti. Jednaki rezultati
razrješavaju se sirovom sličnošću. Detalji i živi brojevi: stranica `/metodologija`.

## Testovi

```bash
uv run pytest apps/nabavaradar/api                      # jedinični + integracija sa snimljenim fixtureima; DB testovi se preskaču bez TEST_DATABASE_URL
TEST_DATABASE_URL=postgresql+psycopg://postgres:<lozinka>@127.0.0.1:5432/postgres \
TEST_REAL_DATABASE_URL=postgresql+psycopg://postgres:<lozinka>@127.0.0.1:5432/nabavaradar \
  uv run pytest apps/nabavaradar/api                    # + migracije, red 6/min, pretplate, sken učitanih podataka
pnpm --filter nabavaradar-web test                      # vitest nad snimljenim odgovorima
NABAVARADAR_API_URL=http://127.0.0.1:8000 pnpm --filter nabavaradar-web e2e   # Playwright (treba API + podaci + Mailpit)
```

Playwright koristi OIB 45050126417 (KONČAR – Elektroindustrija d.d., uvrštena na Zagrebačkoj burzi; OIB je u službenim
dokumentima izdavatelja, izvor u `data/evidence/2026-11-04_e2e_company_oib_source.json`). Za e2e pokrenite API s
`RATE_LIMIT=1000/minute` (globalno ograničenje je 60/min po IP-u; `/match` ostaje 30/min).

## Poznata ograničenja

- Podaci o tvrtkama su iz testne snimke 2024-06-16; nove tvrtke i promjene nakon toga ne postoje.
- 80,2 % tvrtki ima NKD djelatnost; ostale se mogu ocijeniti samo uz opis „Što nudite?”.
- Recall validacije je skroman (vidi `validation.md`): rangiranje po djelatnostima ne zna što tvrtka stvarno nudi.
- NKD→CPV povezivanje koristi i tekstove ciljnih obavijesti (blago povoljno za C); τ je odabran na istom skupu.
- Embeddinzi (~470 MB model) učitavaju se pri pokretanju API-ja (~10 s); `ingest derive` na CPU-u traje desetke minuta.
- Lighthouse (mobilni, `/tvrtka/:oib`): pristupačnost 100, performanse 81, najbolje prakse 100; CLS 0.22 (lista se učitava nakon zaglavlja), LCP 3.1 s. Dokazi: `data/evidence/*_lighthouse_*.json`.
- Registri ugovora: dio datoteka je neispravan, u XLS formatu ili ima manje od 3 prepoznata polja (razlozi u izvješću).
- Docker slika produkcije nije izgrađena u ovoj sesiji (compose je validiran); nije postavljeno na poslužitelj.
