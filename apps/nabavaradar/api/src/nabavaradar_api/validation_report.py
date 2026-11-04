"""Renders ``docs/validation.md`` and ``config/market.yaml`` from an evaluation result.

Every number in the report comes from the result dictionary; nothing is typed in by hand.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from nabavaradar_api.counties import CONFIG_DIR


def pct(value: float | None) -> str:
    """Percentage with one decimal, or an en dash."""
    return "–" if value is None else f"{value * 100:.1f} %"


def render_validation_md(r: dict[str, Any]) -> str:
    """Markdown report of one ``run_evaluation`` result."""
    ks = r["ks"]
    lines = [
        "# NabavaRadar – validacija",
        "",
        f"_Generirano naredbom `nabavaradar eval` ({r['computed_at']}). Brojevi se ne uređuju ručno._",
        "",
        "## Pitanje",
        "",
        "Kad bismo tvrtki koja je stvarno dobila ugovor pokazali natječaje tog mjeseca, bi li se njezin "
        "stvarni natječaj našao među prvih 10 / 20?",
        "",
        "## Protokol",
        "",
        "1. Uzimaju se obavijesti o dodjeli ugovora (TED) u kojima je pobjednik valjan OIB (ISO 7064, MOD 11,10) "
        "koji postoji u tablici `company` (Sudski registar).",
        f"2. Cilj: {r['mode_note']}",
        "3. Za svakog pobjednika rangiraju se **sve** natječajne obavijesti (naručitelj iz Hrvatske) objavljene u "
        "mjesecu cilja. Svaka obavijest ocjenjuje se na dan svoje objave (komponenta T računa se od objave do roka).",
        "4. Metoda: ocjena prilagodbe `0,55·S + 0,25·C + 0,10·G + 0,10·T` (profil = do 10 NKD djelatnosti, glavna prva). "
        "Osnovna metoda: Postgres full-text (`simple` konfiguracija) s riječima iz naziva djelatnosti (ILI-upit, riječi od "
        "najmanje 4 slova), poredano po `ts_rank`.",
        "5. Pri izjednačenju ocjena cilj se računa kao lošije rangiran (konzervativno). Nepogođen cilj (osnovna metoda ne "
        "pronalazi obavijest uopće) računa se kao promašaj.",
        "",
        "## Rezultati",
        "",
        f"- Razdoblje ciljeva: **{r['window']['first_month']} – {r['window']['last_month']}** "
        f"({len(r['months'])} mjeseci)",
        f"- Broj ocijenjenih parova pobjednik–cilj: **n = {r['n']}** "
        f"(od toga {r['n_scored']} s barem jednom NKD djelatnošću, {r['n_without_activities']} bez – računaju se kao promašaj)",
        f"- Prosječan broj kandidata po cilju: {r['mean_candidates_per_target']:.0f}"
        if r.get("mean_candidates_per_target")
        else "- Prosječan broj kandidata po cilju: –",
        "",
        "| Metoda | " + " | ".join(f"recall@{k}" for k in ks) + " |",
        "|---|" + "|".join("---:" for _ in ks) + "|",
        "| **NabavaRadar (prilagodba S/C/G/T)** | "
        + " | ".join(pct(r["fit"][f"recall@{k}"]) for k in ks)
        + " |",
        "| Osnovna: Postgres full-text | "
        + " | ".join(pct(r["fts_baseline"][f"recall@{k}"]) for k in ks)
        + " |",
        "| Slučajan poredak (očekivanje) | "
        + " | ".join(pct(r["random_baseline"][f"recall@{k}"]) for k in ks)
        + " |",
        "",
        "Samo pobjednici s NKD profilom (isključeni oni bez djelatnosti):",
        "",
        "| Metoda | " + " | ".join(f"recall@{k}" for k in ks) + " |",
        "|---|" + "|".join("---:" for _ in ks) + "|",
        "| NabavaRadar | "
        + " | ".join(pct(r["fit_scored_only"][f"recall@{k}"]) for k in ks)
        + " |",
        "| Full-text | "
        + " | ".join(pct(r["fts_baseline_scored_only"][f"recall@{k}"]) for k in ks)
        + " |",
        "",
        f"Medijan ranga cilja (NabavaRadar): {r['median_rank_fit']}",
        "",
        "### Obuhvat podataka",
        "",
    ]
    lk = r["linkage"]
    lines += [
        f"- parova (pobjednik, obavijest) s identifikatorom pobjednika: {lk['award_winner_pairs_with_id']}",
        f"- od toga valjan OIB: {lk['valid_oib']}",
        f"- od toga pronađen u `company`: {lk['found_in_company']}",
        f"- od toga povezano s natječajnom obavijesti (`procedure-identifier`): {lk['linked_to_competition_notice']}",
        f"- kalibracija S: 5. percentil = {r['calibration']['p5']}, 95. percentil = {r['calibration']['p95']}",
        "",
        "## Prag tau (tržišno sondiranje)",
        "",
    ]
    t = r["tau"]
    if t.get("tau") is None:
        lines.append(f"Prag nije određen: {t.get('reason')}.")
    else:
        lines += [
            f"Prag `tau` odabran je maksimizacijom F1 između djelatnosti pobjednika i CPV odjeljka u kojem su dobili ugovor "
            f"({t['winners']} pobjednika, {t['truth_pairs']} parova pobjednik–odjeljak).",
            "",
            f"- **tau = {t['tau']}**, F1 = {t['f1']}, preciznost = {t['precision']}, odziv = {t['recall']} "
            f"(TP {t['tp']}, FP {t['fp']}, FN {t['fn']})",
            f"- pretraženi raspon: {t['grid'][0]:.4f} – {t['grid'][1]:.4f} (201 korak)",
            "",
        ]
    lines += [
        "## Ograničenja",
        "",
        "- **Procurjevanje u povezivanju NKD→CPV.** Sličnost se računa i iz tekstova obavijesti (do 200 po CPV prefiksu), "
        "među kojima su i ciljne obavijesti. To blago povoljno utječe na komponentu C.",
        "- **Prag tau je odabran na istom skupu pobjednika** na kojem se prikazuje F1 (nema odvojenog testnog skupa).",
        "- **Starost registra.** Podaci o tvrtkama potječu iz snimke Sudskog registra navedene na stranici *Izvori* "
        "(testno okruženje portala). Pobjednici koji su osnovani poslije snimke, ili više ne postoje, nisu u `company` i "
        "ne ulaze u vrednovanje; tvrtke u stečaju/likvidaciji namjerno nisu pohranjene.",
        "- **Pokrivenost TED-a.** Obavijesti o dodjeli prije otprilike veljače 2024. imaju stariji format bez podataka o "
        "pobjednicima (API ih ne vraća), pa vrednovanje počinje kad se podaci pojave.",
        "- **Pobjednik po postupku, ne po grupi.** Cilj je cijela natječajna obavijest; ne provjerava se jesu li ponuđene sve grupe.",
        "- **Tvrtke bez NKD djelatnosti** (slobodni tekst predmeta poslovanja se ne pohranjuje) ne mogu se ocijeniti i "
        "računaju se kao promašaj u glavnoj tablici.",
        "- **Mjesečna granulacija.** Kandidati su sve obavijesti istog mjeseca; korisnik u praksi vidi otvorene natječaje, "
        "što je manji skup.",
        "- Rezultat opisuje mogućnost rangiranja stvarnih pobjednika; ne dokazuje da je tvrtka *trebala* pobijediti.",
        "",
    ]
    return "\n".join(lines)


def write_outputs(result: dict[str, Any], docs_path: Path) -> None:
    """Write ``docs/validation.md`` and ``config/market.yaml`` (tau)."""
    docs_path.parent.mkdir(parents=True, exist_ok=True)
    docs_path.write_text(render_validation_md(result), encoding="utf-8")
    tau = result["tau"]
    if tau.get("tau") is not None:
        market = {
            "tau": tau["tau"],
            "f1": tau["f1"],
            "precision": tau["precision"],
            "recall": tau["recall"],
            "winners": tau["winners"],
            "computed_at": result["computed_at"],
            "source": "nabavaradar eval (maximises F1 of winners' activities vs awarded CPV division)",
        }
        (CONFIG_DIR / "market.yaml").write_text(
            "# Written by `nabavaradar eval`; do not edit by hand.\n"
            + yaml.safe_dump(market, allow_unicode=True, sort_keys=False),
            encoding="utf-8",
        )
