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
- Explicit verification can make a paid search test for each available OpenAI and Anthropic probe model.
  Use `--no-search-test` for model listings alone.
- Probes every WRDS table in `config/wrds_schema.yaml`, picks the physical column for each logical field, and
  writes `config/wrds_schema.resolved.yaml`.
- Computes effective latest dates (the 50%-of-median row-count rule; future-dated rows are dropped and counted).
- Picks primary → fallback sources per input (`config/sources.yaml`).
- Writes `docs/PHASE0_VERIFICATION.md`.

It halts (exit 2) only when a *required* input has no working source. Pipeline commands re-run the relevant
checks automatically when verification is stale. Automatic provider preflight uses model listings only.

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

`--dry-run` shows the default planned call count (A 1,920 · B 960 · C 840) and the estimated cost. It is required: collect
refuses to run without a dry run that matches the current plan.

Run the pilot (`--pilot 2`) for every stage. Once pilot calls exist, a fresh dry run re-estimates the cost from
measured token usage. Then run `aim refresh` and check the dashboard: refusals, parse methods, the resolution rate
(target ≥ 99%) and `data/manual/ticker_review.csv`.

## 3. Freeze prompts, then collect inside one window (Phase 5)

`prompt_version` and `experiment_version` hash everything that defines the run. Once collection starts, do not edit
`config/prompts/*` or the roster.

```bash
aim collect --stage A
```

```bash
aim collect --stage B
```

```bash
aim collect --stage C
```

Run a matching full-stage dry run before each command. The expanded roster uses
direct collection. For a baseline-only configuration, add `--batch` to both
planning and collection for A/B and repeat `aim batch-poll --stage A` or
`--stage B` until collected. Stage C uses direct collection.

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

## Direct DeepSeek and Kimi pilot

Export `AIM_DEEPSEEK_API_KEY` and `AIM_KIMI_API_KEY` using the same shell setup as the
existing keys. Use an international Kimi API Platform key with the configured
`api.moonshot.ai` endpoint. The default Stage A roster now has 16 models, so Pilot 1
plans 64 calls. Previously completed calls in the same workspace are skipped.

```bash
aim plan --stage A --dry-run --pilot 1
aim collect --stage A --pilot 1
```

Automatic collection preflight refreshes model listings when verification is stale.
It omits paid search probes. To refresh listings explicitly without checking WRDS
or sending probes, run `aim verify --no-wrds --no-search-test`. Explicit
`aim verify` can send paid OpenAI and Anthropic search probes when their probe
models are available. `--skip-verify` skips collection preflight entirely.

DeepSeek and Kimi are enabled for direct A/B collection. An A/B plan containing the new providers cannot
use `--batch`. Use the original roster in a separate configuration directory
selected by `AIM_CONFIG_DIR` for OpenAI/Anthropic-only batch runs.

The dry-run cost is for the full plan, including calls the runner may skip.
DeepSeek estimates use peak, cache-miss rates. Kimi uses standard uncached rates
with the provider's default cache TTL. These are token-based estimates, not
invoice reconciliation. Both new providers request high reasoning effort and cap
completion at 8,192 tokens, including reasoning.

After parsing, resolution, and exposure aggregation, `aim analyze` and
`aim refresh` keep the original baseline analysis. Use
`aim analyze --cohort expanded` for a separate four-provider analysis in
`outputs/expanded` under the data directory. Run `aim figures --cohort expanded`
to render figures and their CSVs in `outputs/expanded/figures` from that saved
analysis. Figures that require unavailable Stage B or C inputs are skipped.
Default figures, the paper comparison, the report, and dashboard portfolio views
use the baseline.

## Expanded Stage C search pilot

Stage C Pilot 1 plans 56 direct calls. The original 32 OpenAI/Anthropic calls
keep their IDs. DeepSeek V4 Pro (`deepseek-v4-pro`) and Moonshot Kimi K3.1 Pro
(`kimi-k3.1-pro`) and K3 (`kimi-k3`) add 24 calls. DeepSeek Flash ignores the
Responses web-search tool and stays in A/B. The new models use each provider's
server-side Responses search with automatic invocation. No external search tool
or client-side search loop is used.

```bash
aim plan --stage C --dry-run --pilot 1
aim collect --stage C --pilot 1
```

Use `aim analyze --cohort expanded` for the combined analysis. Default analysis
and dashboard outputs still use the OpenAI/Anthropic baseline. For the expanded
models, the Responses endpoint can behave differently from the Chat Completions
endpoint used in A/B. Kimi uses its Responses reasoning defaults and may decide
to search before model generation.
DeepSeek documents successful search-query and page-fetch counts, but does not
guarantee query text or source URLs. Kimi exposes search queries and optional
source URLs, and does not document a separate fetch count for this endpoint.
Search attempts, known zero use, and unavailable telemetry are recorded
separately. Query content analysis uses visible queries only.

Dry-run assumptions use 60% search invocation. DeepSeek estimates four billed
queries per invocation and one fetch per query. Kimi estimates one billed search
per invocation. The estimate adds tool fees separately from token charges.
Measured token usage already includes tool context, so it receives no additional
context-token allowance. Billed counts can differ from attempts and visible
query rows. When usage is unavailable, the stored cost reflects the known
components only. The dry-run figure is an estimate, not a billing cap.
