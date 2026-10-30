# Runbook

How to run the real experiment, end to end. Every command is idempotent: re-running it skips work that is
already done.

## 0. Setup (once per machine)

```bash
pip install -e ".[wrds,dev]"
```

```bash
cp .env.example .env
```

In `.env`, set:
- `AIM_OPENAI_API_KEY` and `AIM_ANTHROPIC_API_KEY` (the `AIM_` prefix avoids clashes with other tools);
- `WRDS_USERNAME`, plus `WRDS_PASSWORD` if you want `aim verify` to write `~/.pgpass` for you.

Load the file into your shell with `set -a; source .env; set +a`.

WRDS is a PostgreSQL connection to `wrds-pgdata.wharton.upenn.edu:9737`. **The first connection from a new machine
triggers a Duo push: approve it.** Some cloud sandboxes block this port. `aim verify` reports that explicitly
rather than failing silently.

## 1. Phase 0: `aim verify`

```bash
aim verify
```

What it does:
- Lists each provider's models and confirms every id in `config/models.yaml`.
- Makes one search-enabled test call per provider (about $0.05) and checks the queries are captured.
- Probes every WRDS table in `config/wrds_schema.yaml`, picks the physical column for each logical field, and
  writes `config/wrds_schema.resolved.yaml`.
- Computes effective latest dates (the 50%-of-median row-count rule; future-dated rows are dropped and counted).
- Picks primary → fallback sources per input (`config/sources.yaml`).
- Writes `docs/PHASE0_VERIFICATION.md`.

It halts (exit 2) only when a *required* input has no working source. Pipeline commands re-run the relevant
checks automatically when the last verification is more than 24 hours old.

Before production, fill in:
- `knowledge_cutoff` for the OpenAI models, and any placeholder prices (`price_verified: false`), in
  `config/models.yaml`;
- the Anthropic `api_version` if it changes.

## 2. Phases 1–2: plan, dry run, pilot

```bash
aim plan --stage A --dry-run
```

```bash
aim plan --stage C --pilot 2 --dry-run
```

```bash
aim collect --stage C --pilot 2
```

`--dry-run` shows the planned call count (A 1,440 · B 720 · C 480) and the estimated cost. It is required: collect
refuses to run without a dry run that matches the current plan.

Run the pilot (`--pilot 2`) for every stage. Once pilot calls exist, a fresh dry run re-estimates the cost from
measured token usage. Then run `aim refresh` and check the dashboard: refusals, parse methods, the resolution rate
(target ≥ 99%) and `data/manual/ticker_review.csv`.

## 3. Freeze prompts, then collect inside one window (Phase 5)

`prompt_version` and `experiment_version` hash everything that defines the run. Once collection starts, do not edit
`config/prompts/*` or the roster.

```bash
aim collect --stage A --batch
```

```bash
aim collect --stage B --batch
```

```bash
aim collect --stage C
```

```bash
aim batch-poll --stage A
```

```bash
aim batch-poll --stage B
```

- **Stages A and B** go through the Batch APIs at about half price.
- **Stage C** runs live, because it uses web search.
- **`batch-poll`**: repeat until every batch reports collected.

Transport errors (429 `slow_down`, 503/529 overloaded, timeouts) are retried with backoff and honour
`Retry-After`. Refusals and malformed answers are recorded, never retried. `--resume` re-attempts calls that
previously failed in transport. A per-stage budget cap (`experiment.yaml`) stops scheduling new calls once it would
be crossed.

## 4. Phase 3: WRDS and factors

```bash
aim resolve
```

```bash
aim wrds validate-crsp
```

```bash
aim factors build --asof YYYY-MM-DD --universe acwi_proxy
```

```bash
aim factors build --asof YYYY-MM-DD --universe us_broad
```

- **`aim resolve`**: builds the CIQ + Compustat security master (cached), then resolves every holding.
- **`aim wrds validate-crsp`**: compares returns against CRSP for 2024–2025. Acceptance: correlation above 0.99
  and median |diff| below 1bp.
- **`aim factors build`**: run for both universes. Use the last trading day of the window as the as-of date.
  Prices and FX must cover it; otherwise the coverage gate moves it back.

Every pull is cached in `data/raw/wrds/<library>.<table>/<asof>[__tag].parquet`, with the SQL and pull time beside
it. Delete a cache file to force a re-pull.

## 5. Phase 6: analyses, figures and report

```bash
aim refresh
```

This runs parse, resolve, exposures, analyze, figures, report and dashboard export. Then edit the "Note" column of
`docs/RESULTS.md`: each difference from the paper needs a substantive explanation before circulating.

```bash
aim dashboard serve
```

Open http://127.0.0.1:8765 and switch between the **live** and **demo** datasets in the header.

## 6. Manual files (`data/manual/`)

| File | Use |
|---|---|
| `ticker_overrides.csv` | Force a raw ticker (+ optional exchange) to a master `item_id` or `gvkey`/`iid` |
| `crosslisting_overrides.csv` | Exceptions where two CIQ companies are really one issuer |
| `query_labels_gold.csv` | Hand labels for ≥ 200 search queries (Cohen's κ for the classifier) |
| `ticker_review.csv` | Written by `aim resolve`: low-confidence and unresolved tickers, with suggestions |

## 7. Phase 7: extensions

- Second and third dates: re-run collection in a new window and run `aim factors build` with the new as-of date.
- US universe: `--universe us_broad` on `factors build`, `exposures` and `analyze`.
- Forced discovery: `aim discovery screen --mandate MOMENTUM --top 100` writes the timestamped candidate set and
  the exact prompt to `data/outputs/discovery/`.

## Troubleshooting

- **`no API key`**: check that `AIM_OPENAI_API_KEY` / `AIM_ANTHROPIC_API_KEY` are exported in the shell running `aim`.
- **`cannot reach wrds-pgdata…`**: the network blocks port 9737. Use a machine on the university network or VPN.
- **A WRDS column was renamed**: add the new name to the candidate list in `config/wrds_schema.yaml` and re-run
  `aim verify`.
- **A model id changed**: `aim verify` lists it under "models missing". Update `config/models.yaml` *before*
  collection (it changes `experiment_version`).
