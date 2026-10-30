# AI at the Margin

Replication of the OMI Advisory / Man Group LLM-portfolio experiment (*Artificial Intelligence, Alpha and the
Architecture of Markets*, July 2026) on **OpenAI and Anthropic models**, using **WRDS** data only. The full spec is
[`BUILD_BRIEF.md`](BUILD_BRIEF.md).

The pipeline does four things:

1. **Collects portfolios.** Twelve models build ten-stock portfolios under four free-form framings (Stage A), four
   institutional mandates (Stage B), and with web search available (Stage C).
2. **Resolves every ticker to an issuer.** Capital IQ first, then Compustat, then name matching. Share classes,
   ADRs and cross-listings collapse to one issuer.
3. **Measures each book on a Barra-style factor model** built from point-in-time Compustat, I/B/E/S, FX and the
   risk-free rate.
4. **Reproduces Figures 1–7 and adds new analytics.** It also runs a React dashboard over the results.

```
aim verify → plan (dry run) → collect A/B/C → parse → resolve → factors build → exposures
          → analyze → figures → report → dashboard export / serve
```

## Quick start

```bash
pip install -e ".[wrds,dev]"
```

```bash
aim demo
```

```bash
aim dashboard serve
```

`aim demo` runs the whole pipeline in about two minutes on **simulated models and a synthetic market**. It needs
no API keys and no WRDS access. Every page and figure it produces is labelled **synthetic**. Tickers and names are
real, so the resolver is exercised on real formats; prices, fundamentals and responses are simulated.

`aim dashboard serve` opens the dashboard at http://127.0.0.1:8765. The built frontend is committed in
`frontend/dist`, so Node is not needed to run it.

## The real run

[`docs/RUNBOOK.md`](docs/RUNBOOK.md) has the step-by-step procedure, including the WRDS Duo push. In short:

```bash
cp .env.example .env
```

```bash
aim verify
```

```bash
aim plan --stage A --dry-run
```

```bash
aim collect --stage A --pilot 2
```

```bash
aim collect --stage A --batch
```

```bash
aim batch-poll --stage A
```

```bash
aim factors build --universe acwi_proxy
```

```bash
aim refresh
```

```bash
aim dashboard serve
```

- **`.env`**: fill in `AIM_OPENAI_API_KEY`, `AIM_ANTHROPIC_API_KEY` and `WRDS_USERNAME` (plus optionally
  `WRDS_PASSWORD`).
- **`aim verify`**: Phase 0. It confirms models and search capture, probes the WRDS schemas and picks sources.
- **`aim plan … --dry-run`**: required before any spend.
- **`aim collect … --pilot 2`**: Phase 2 pilot (two calls per cell).
- **`aim collect … --batch`**: full Stage A at about half price. Then repeat for B (batch) and C (live).
- **`aim batch-poll`**: collects batch results.
- **`aim factors build`**: as-of = the last trading day of the collection window.
- **`aim refresh`**: parse, resolve, exposures, analyze, figures, RESULTS.md and dashboard data.

## What the dashboard shows

Twelve pages, built with **Aceternity UI** components (sidebar, spotlight, bento grid, hover cards, timeline,
tracing beam, infinite cards, vanish input, glowing borders, animated tooltips) on React, Tailwind and Recharts.
The chart palette has been validated for colour-blind safety in both light and dark modes.

| Page | Contents |
|---|---|
| Overview | KPIs, headline findings with links, consensus-name ticker, build-phase status |
| Pipeline & data | Live acceptance checks per phase, provider and WRDS verification, source per input, effective dates, budget, roster, deviations |
| Collection | Outcome of every call, refusal heatmap, cost per model and per valid book, tokens, retries, latency |
| Name overlap (Fig. 1) | Jaccard by framing for four baselines with bootstrap CIs, 12 × 12 heatmap, consensus names |
| Factor profiles (Figs. 2–3) | Loadings heatmap, sector mix, framing lines, framing effect vs noise, **factor-space PCA**, **name distance vs factor distance** |
| Mandates (Fig. 4) | Mandate × factor heatmap, Δ vs own Unconstrained with CIs, **compliance pass rates and funnel**, reasoning vs delivery, mandate-book overlap |
| Search & queries (Figs. 5–7) | Offline vs connected dumbbells (RSTR and 12-1), invocation heatmap, query classes, lookup-to-book share, ordering test, Cohen's κ |
| **AI crowd book** (new) | Aggregate book vs market weights, concentration, crowd-book factor exposure, regional mix, attention percentiles, ADR usage |
| **Information date** (new) | Offline momentum books re-measured 0–18 months back: the *implied information date* of each model against its stated cutoff |
| **Models** (new) | Size and generation profiles, overlap with flagship, how models size positions, ticker-resolution quality |
| Portfolio explorer | Every call: response text, holdings and how each ticker resolved, loadings, every search query |
| Results vs paper | Our headline numbers next to the paper's, with a first reading of each difference |

To develop the dashboard:

```bash
cd frontend && npm install && npm run dev
```

The dev server proxies `/api` and `/data` to `aim dashboard serve`.

## Repository layout

```
config/            models, experiment, universes, factors, sources (primary → fallback), WRDS schema map, exchanges, prompts
src/aimargin/
  providers/       OpenAI Responses + Anthropic Messages adapters (search capture, pause_turn, refusals)
  collect/         planner, async runner (retries, idempotent, budget guard), Batch API, cost model
  parse/           JSON / table / list extraction, refusal rules, outcome classes, weights
  resolve/         ticker normalisation, CIQ → Compustat → fuzzy resolver, issuer collapse, overrides
  wrds_io/         connection + cache, schema probes, freshness rule, prices, FX, rf, Snapshot PIT, I/B/E/S, CIQ, Datastream, RavenPack, CRSP validation
  factors/         returns, universes, descriptors, standardisation, exposures
  analysis/        §8.1–8.12 plus crowding, factor space, weighting, geography, information date, ops
  figures/         Figures 1–7 + extension figures (PNG + CSV)
  dashboard/       JSON export + stdlib server
  demo/            synthetic world + simulated provider transport
frontend/          React dashboard (Vite, Tailwind v4, Motion, Recharts, Aceternity UI)
docs/              RUNBOOK, DEVIATIONS, DATA_DICTIONARY, generated PHASE0_VERIFICATION / RESULTS
tests/             pytest suite, including an AST check of the team coding style
```

## Conventions

- **Coding style** (BUILD_BRIEF §0.5): plain index loops; no `zip`, `enumerate`, comprehensions or generator
  expressions. `tests/test_style.py` enforces this. Missing data never crashes a run: drops are logged in
  `drop_log` and statuses are explicit.
- **Data licensing** (§10): `data/raw`, `data/processed`, `data/outputs` and `data/dashboard` are git-ignored.
  Never push WRDS-derived files to a public repository.
- **Checks:** `pytest` and `ruff check src tests` must pass before pushing.
