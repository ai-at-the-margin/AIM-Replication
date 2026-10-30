# Deviations from the paper and choices left open by it

Kept current as the design changes (BUILD_BRIEF §0.3, §10). The dashboard's Pipeline page shows the same list.

## Design

| Item | Paper | Ours | Why |
|---|---|---|---|
| Providers | 16 models from 6 providers; 6 flagships | 12 models from OpenAI and Anthropic; Stage C on 4 | Scope of this replication |
| Mandarin arm | Chinese models prompted in Mandarin | Optional, off by default (`optional_arms.mandarin`) | No Chinese providers in scope |
| Prompts | Not published | Our own (`config/prompts/`), frozen via `prompt_version` | Required to run |
| Repetitions | A: 2,911 calls in total; B: 960 | A: 30 per cell (1,440); B: 15 (720); C: 15 (480) | BUILD_BRIEF §1.1 |
| Output format | Not stated | JSON block requested at the end; no structured-output modes | Structured modes would suppress refusals |
| Search queries | Visible for 3 providers | Both providers expose queries; all are classified | — |

## Measurement

| Item | Paper | Ours | Why |
|---|---|---|---|
| Factor model | MSCI Barra exposures | Barra-style replica (§7) | Barra not licensed on this WRDS account |
| Universe | Barra global | MSCI ACWI list from Datastream if found; else a Compustat ACWI proxy (85% of cap per country, primary common equity) | MSCI not licensed |
| Cap weights | Free float | Full market cap | Free float not available consistently |
| Prices | Bloomberg | Compustat daily (`secd`, `g_secd`); CRSP only to validate 2024–2025 | The CRSP vintage ends 31 Dec 2025 |
| Risk-free rate | — | Fama-French daily rf, forward-filled after 30 Sep 2026 (`rf_filled`) | Source lag; effect negligible |
| Fundamentals | Barra | Compustat Snapshot point-in-time; fallback is restated Compustat entered on `rdq` or `datadate` + 90/120 days | Avoid look-ahead |
| Issuer market cap | — | Sum over non-ADR issues (ADR lines only when nothing else exists) | Avoid double counting ADR shares |
| Earnings variability | Not specified | Sample sd of annual Δ(income before extraordinary items)/total assets, last 5 years, minimum 3 | Stable when earnings change sign |
| Outcome classes | Valid vs not | Adds `excess_names` (more than 10 issuers) and `api_error` | Never silently treat these as picks |
| Universe membership | — | As of T; earlier dates in the information-date analysis reuse the T universe | Simplicity; adds some survivorship bias to that extension only |

## Infrastructure

- `config/wrds_schema.yaml` holds the candidate columns. `aim verify` writes the resolved mapping to
  `config/wrds_schema.resolved.yaml` so comments in the hand-maintained file survive.
- OpenAI reasoning text is the reasoning *summary* (`reasoning.summary = auto`). It does not change reasoning
  effort. Anthropic reasoning text is present only for models that return thinking blocks by default.
