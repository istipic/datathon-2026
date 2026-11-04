# ADR 0008: Birokratko v2 (Neo-Brutalist look, threshold alerts, fit tuning)

- Status: accepted
- Date: 2026-11-05

## Context

Birokratko (technical name `nabavaradar`) got a new look, e-mail alerts that fire when a tender reaches a threshold,
a better selection of tenders and a few small features. The decisions below are the ones that are not obvious from
the code.

## Decision 1: self-hosted fonts (Cabinet Grotesk, Satoshi)

The design asks for Cabinet Grotesk (headings) and Satoshi (body), both from Fontshare. The production CSP
(`Caddyfile`) is `default-src 'self'`, so the four WOFF2 files used (Cabinet Grotesk 700 and 800, Satoshi 500 and 700)
are stored in `apps/nabavaradar/web/public/fonts/` and loaded with `font-display: swap`; the system font stack is the
fallback.

- Source: the Fontshare CDN files listed by `api.fontshare.com/v2/css` on 2026-11-05.
- Licence: the Fontshare metadata of both families says `license_type: itf_ffl` (ITF Free Font License, free for
  personal and commercial use; evidence in `apps/nabavaradar/data/evidence/2026-11-05_fontshare_*_list.json`).
- Coverage: checked with fontTools that all four files contain č ć š ž đ (and capitals) and the euro sign.
- Size: about 90 KB in total.

## Decision 2: threshold alerts reuse the double opt-in subscription

`subscription` gets `min_fit` (0.5-0.95, also a database check), `min_value_eur`, `counties`, `cpv_divisions`,
`frequency` (`daily` | `weekly`) and `paused`; two new tables record what was sent (`alert_sent`, unique per
subscription and notice, so a notice is mailed at most once) and what the subscriber excluded (`alert_exclusion`).
Rows that existed before migration 0004 are weekly digests (server default `weekly`); new sign-ups default to `daily`.

- A notice qualifies when its fit is `>= min_fit` (inclusive), it passes the filters, its deadline is ahead, it was
  not mailed before and not excluded. Notices of an already mailed procedure are not mailed again (a re-publication of
  the same procedure has a new publication number but the same `procedure_id`).
- One e-mail per subscriber per run, at most 20 notices, with the reasons ("Zašto?"). `nabavaradar alerts send`
  runs daily at 07:00 (cron), `nabavaradar digest send` runs Mondays for weekly subscribers with the same logic.
- Settings and unsubscribe tokens are HMACs of the subscription id with different purposes (a settings token cannot
  unsubscribe and vice versa); nothing usable is stored. Sign-up is limited to 10 per hour per IP and 3 per hour
  per e-mail address.

## Decision 3: fit tuning, measured

`config/fit.yaml` holds the weights and the new signals, and `nabavaradar eval --config X --no-write` measures a
variant with the unchanged protocol (30 017 winner-tender pairs). Baseline recall@10 / @20: 8.65 % / 14.55 %.
Chosen: secondary activities count 0.5 of the main one, +0.25 on C when the CPV group (3 digits) is among the
company's 10 best, design-contest notices (`cn-desg`) excluded: **10.63 % / 17.86 %**. Every single change improved
both measures; the discount gains flatten below 0.5 (0.4: 10.67 % / 18.05 %). All 14 runs are in
`data/evidence/2026-11-05_fit_tuning.json` and rendered in `docs/validation.md`.

Limits: the tuning set and the evaluation set are the same pairs (no hold-out), so the gain is an upper estimate.
Grouping publications of one procedure and "Ne zanima me" change what is shown, not the rank of winners, so they are
tested functionally and not by this measure.

## Decision 4: browser-only state for the small features

Saved tenders, hidden notices and the banknote counter live in `localStorage` (wrapped in try/catch); nothing about
them is sent to the server, except the list of hidden publication numbers and disliked CPV groups, which is sent as
query parameters of `/match` so the API can leave them out. No account, no tracking.

## Consequences

- Metodologija is removed; transparency stays in "Zašto?", the FAQ and the quality table on `/izvori`.
- No new Python or npm dependency; the only new binary assets are the four font files.
