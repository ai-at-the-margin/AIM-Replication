# BUILD BRIEF — "AI at the Margin": Replicating the OMI Advisory LLM-Portfolio Experiment
### Scope: OpenAI (ChatGPT models) + Anthropic (Claude models) · Data: WRDS (access confirmed 29 Oct 2026)

**Audience:** Claude Code (implementer) + Tanish's research team (reviewers)
**Source paper:** OMI Advisory / Man Group, *Artificial Intelligence, Alpha and the Architecture of Markets* (July 2026, draft for TCorp)

Addendum (team request): there is also a frontend that shows the work in progress, with visualisations, graphs and
analytics, including new analytics beyond the paper's figures, built with Aceternity UI components.

**Goal:** Rebuild the paper's full experimental pipeline on two providers (OpenAI, Anthropic), using only WRDS data:
- prompt generation;
- LLM collection, offline and with web search;
- portfolio parsing and security resolution;
- factor-exposure measurement;
- every analysis behind Figures 1–7.

The pipeline must be reproducible, resumable and auditable, and re-runnable at new dates and on a US-equity universe.

> **What changed from v2.**
> - The team ran a WRDS access check (results summarised in §2.3). Every data source below is chosen from datasets the account can actually read.
> - **No further manual testing will be done.** Anything still uncertain (exact column names in some tables, whether a dataset covers the as-of date) is resolved **automatically in code**: `aim verify` probes at run time, and each input has a primary source plus a fallback. Claude Code must implement these probes and fallbacks, not ask the team.

---

## 0. Instructions to Claude Code

1. **Build order.** Read the whole brief, then build in the phase order of §11; each phase has acceptance criteria.
2. **`aim verify` (Phase 0) is code, not a manual step.** It runs automatically at the start of every pipeline run and does four things:
   - confirms the model IDs via the providers' model-list endpoints;
   - makes one search-enabled test call per provider and confirms that query fields are captured;
   - probes WRDS table schemas and **effective** latest dates (§2.4);
   - writes `docs/PHASE0_VERIFICATION.md`.

   If a primary source fails a probe, the pipeline switches to the configured fallback and logs the switch. It halts only if no source exists for a required input.
3. **Unspecified details** (exact prompts, repetitions, weighting) that the paper leaves open: use the defaults here, keep them in config, and log them in `docs/DEVIATIONS.md`.
4. **Never spend API budget without a dry run.** Every stage supports `--dry-run` (planned calls plus estimated cost) and `--pilot N` (N calls per cell).
5. **Coding style (team preference — follow strictly):**
   - Simple, human-looking Python. **Use plain index loops (`for i in range(len(x))`). Do not use `zip`, `enumerate`, list/dict/set comprehensions, or generator expressions.** Vectorised pandas/NumPy and SQL are fine where natural.
   - **Defensive handling of missing data everywhere.** Missing tickers, prices, fundamentals, FX, estimates, empty portfolios and absent weights must never crash a run. Carry explicit `status` / `reason` columns and log every drop.
   - Deliver complete, runnable modules. Use type hints, docstrings, `pytest` and `ruff`.
6. **WRDS column names.** Where this brief names a WRDS column it marks *(verify)*, look the schema up with `db.describe_table()` at build time. Keep a single `config/wrds_schema.yaml` mapping logical fields to physical columns, so a renamed column is a one-line fix.

---

## 1. What we replicate, and how our configuration differs

### 1.1 The paper's design vs ours

| Element | Paper | Ours (v3) |
|---|---|---|
| Providers / models | 16 models from 6 providers; 6 flagships | **2 providers, 12 models** (§1.2). The search tests use 4 of them: the flagship and mainstream frontier model from each provider |
| Stage A — free-form | 4 framings, L1 (bare request) → L4 (fund-manager brief); search off; Chinese models also prompted in Mandarin | Same 4 framings, in English. The Mandarin arm is optional and off by default |
| Stage B — mandates | Value / Quality / Momentum / Unconstrained, 300–400 words each, search off | Same |
| Stage C — connected | Principal prompts rerun with web search, 6 flagships | Same prompts on 4 models |
| Volumes | A: 2,911 calls; B: 960 | A: 12 × 4 × 30 = **1,440**; B: 12 × 4 × 15 = **720**; C: 4 × 8 × 15 = **480**; total ≈ **2,640** |
| Factors | Barra exposures, global universe, 15 Jul 2026 | A Barra-style replica built from WRDS (§7), with **point-in-time fundamentals (Compustat Snapshot)** and **forward earnings (I/B/E/S)**. Measured on a global universe that approximates MSCI ACWI, plus a broad US universe. The as-of date is the last trading day of our collection window |
| Overlap | Mean Jaccard similarity over cross-provider pairs of repetitions | Same, plus cross-model and within-model baselines |
| Query classification | Search queries visible for 3 providers | Both providers expose queries, so every query is classified |

**Paper headline numbers** (sanity checks, not targets):
- Cross-provider Jaccard falls from 0.69 at L1 to 0.38 at L4.
- Free-form exposures: size +0.55, quality +0.49, momentum −0.31, value −0.06. Low-vol is +0.37 at L1 and −0.06 at L4.
- Offline mandates: the Value mandate moves value exposure from −0.12 to +0.77. The Momentum mandate still produces momentum of −0.38.
- With search, the Momentum mandate reaches +0.43 pooled, and +0.53 to +0.98 for models that actually searched.
- Single-stock checks are 80% of queries under Value, 76% under Unconstrained and 35% under Quality.

### 1.2 Model roster (verified against provider docs 29 Oct 2026; `aim verify` re-confirms)

| Role | OpenAI | Anthropic | Stages |
|---|---|---|---|
| **Flagship** | `gpt-6-astra` (3 Sep 2026; $10 / $50 per M tokens) | `claude-fable-5-1` ($10 / $50; adaptive thinking always on; default effort `high`; knowledge cutoff Jun 2026) | A, B, C |
| **Mainstream frontier** | `gpt-6.1-sol` (29 Sep 2026; $2 / $10) | `claude-opus-5-5` ($4 / $20; default effort `medium`; cutoff Jun 2026) | A, B, C |
| Mid | `gpt-6.1-terra` (26 Oct 2026; $1 / $5) | `claude-sonnet-5-5` ($2 / $10) | A, B |
| Small | `gpt-6-luna` ($0.10 / $0.50) | `claude-haiku-5-5` (from $0.10 / $0.50) | A, B |
| Previous-generation flagship | `gpt-5.6-sol` (9 Jul 2026) | `claude-fable-5` (9 Jun 2026) | A, B |
| Two generations back | `gpt-5.5` (Apr 2026) | `claude-opus-4-8` | A, B |
| *Optional consumer proxy* | `chat-latest` (moving snapshot; flagged as non-reproducible) | — | A |

**Excluded:**
- `claude-mythos-*`: restricted access.
- `claude-haiku-4-5-20251001`: its retirement window opened 15 Oct 2026, so it could disappear mid-study.
- `claude-sonnet-4-5-20250929`: retires 30 Nov 2026.

**Call parameters:**
- **No sampling parameters for either provider.** GPT-6 Astra rejects custom temperature and top_p. Anthropic removed temperature, top_p and top_k in API version `2026-10-21`.
- Use default reasoning effort and record the effective value.
- Pin the Anthropic API version in config.
- Record `model_returned` on every call.
- Record each OpenAI model's stated knowledge cutoff, taken from its model page, in `models.yaml`.

### 1.3 Web-search tools (Stage C)

| | OpenAI | Anthropic |
|---|---|---|
| API | Responses API only | Messages API |
| Tool | `{"type": "web_search"}`, with `tool_choice` set to `"auto"` | Default: `{"type": "web_search_20260318", "name": "web_search", "max_uses": 10, "response_inclusion": "full"}`. Robustness arm: `web_search_20250305`, the basic tool without dynamic filtering |
| Where the queries are | `web_search_call` items: action type, query and sources. Request sources via `include` | `server_tool_use` blocks, `input.query`. Also parse nested blocks that carry a `caller` field (dynamic filtering) |
| Special handling | — | Resend on `stop_reason: "pause_turn"`. Map `stop_reason: "refusal"` to the refusal flag |
| Price | $10 per 1,000 calls, plus content tokens | $10 per 1,000 searches, plus result tokens |

**"Invoked search"** means at least one executed search event. Having the tool available does not count.

### 1.4 Budget

About 2,640 calls, estimated at **$450–650**. Stages A and B can run through each provider's Batch API at roughly half price. Recompute the estimate from token usage measured in the pilot.

---

## 2. Data plan (WRDS)

### 2.1 Connection

Use the `wrds` Python package (`wrds.Connection()`, credentials in `~/.pgpass`), with a per-query `statement_timeout`.

Every pull is cached to `data/raw/wrds/<library>.<table>/<asof>.parquet`, together with:
- the SQL text;
- the pull timestamp;
- the effective latest date of the source table.

### 2.2 Source map: primary → fallback, per input

| Input | Primary | Fallback / cross-check | Why |
|---|---|---|---|
| **Daily prices, returns, shares — North America** (includes US-listed ADRs) | `comp.secd` | CRSP `dsf_v2`, but **only for validation over 2024–2025** (the CRSP vintage ends 31 Dec 2025, §2.3) | Compustat daily is current; CRSP is not |
| **Daily prices, returns, shares — Global** (China A-shares, HK, TW, EU, …) | `comp.g_secd` | Datastream `tr_ds_equities` total-return index on the primary quote, e.g. `ds2primqtri` *(verify)*, as a cross-check and a fallback for issuers with gaps | Compustat Global daily is current; Datastream is an independent second source |
| **FX** | `comp.g_exrt_dly` (GBP-based; build USD cross-rates). Current to 28 Oct 2026 | Datastream FX series, if `g_exrt_dly` has gaps on a needed date | — |
| **Risk-free rate** | `ff.factors_daily` (`rf`). Current only to **30 Sep 2026** | **Forward-fill the last available daily rf**, with `rf_filled = True`. CRSP treasuries (`crsp_q_treasuries`) only if `aim verify` finds them more current | Daily rf is about 0.015%. Forward-filling one or two months has negligible effect on any descriptor; this is documented |
| **Fundamentals — North America, point-in-time** | **Compustat Snapshot** (`comp_snapshot`): annual `csco_afnd`, quarterly `csco_ifndq`, keys `csco_akey`, using point-in-time validity columns such as `pitdate1` / `pitdate2` *(verify)* | `comp.fundq` / `comp.funda`, entering on `rdq` (quarterly) or `datadate + 90` days (annual) | Removes v2's main limitation (restated data leaking future information) |
| **Fundamentals — Global** | Global tables in `comp_snapshot`, if `aim verify` finds any (list all tables and match on a global prefix/description) | `comp.g_fundq` / `comp.g_funda`, entering on `rdq` if present, otherwise `datadate + 120` days | — |
| **Forward earnings** (value robustness, attention covariate) | I/B/E/S summary statistics: US `ibes.statsum_epsus`, international `ibes.statsum_epsint`, using consensus mean, FY1/FY2 and the statistic date *(verify)* | `tr_ibes` (the same data under a Refinitiv/LSEG library) | Barra-style earnings yield uses forecasts |
| **Security master, ticker resolution, cross-listings** | **Capital IQ**: `ciq` trading item / security / company / exchange tables, plus `ciq_common` `wrds_gvkey` links to Compustat *(verify table names)* | `comp.security` / `comp.g_security` (ticker, exchange, ISIN, SEDOL, CUSIP) and fuzzy name matching against `conm` | CIQ links every trading item (GOOGL, GOOG, TSM, 2330.TW) to one company ID, so cross-listing and ADR merges are systematic instead of manual |
| **GICS sectors, primary-issue flags** | `comp.company` / `comp.g_company` (`gsector` … `gsubind`, `priusa` / `prican` / `prirow`) | CIQ industry fields | — |
| **Index membership** | `comp.idxcst_his` + `comp.idx_index` (S&P 500 / 1500) for the US universe and benchmark sanity checks. For MSCI ACWI, search Datastream constituent tables (`ds2constmth` / `ds2constdly`, with index lists) for an MSCI ACWI or MSCI World list | If no MSCI list exists (expected: MSCI and Barra libraries are not licensed), use the Compustat-built ACWI proxy (§2.5) | Exact ACWI constituents only if available |
| **US cross-check of quality descriptors** | `wrdsapps_finratio.firm_ratio` (ROA, ROE, leverage) | — | Validation only |
| **News attention** (optional extension, §8.12) | RavenPack (`ravenpack_dj`, `rpna`): news counts per company over the 30 days before the as-of date | I/B/E/S analyst count as a coverage proxy | Tests whether model picks over-weight heavily covered stocks |

**Not available on this account:** `msci`, `barra`, `axioma`, `factset`, `tr_worldscope` (only a sample), `wrdsapps_beta`, `crsp_m_stock`. The design does not depend on any of them.

### 2.3 Facts from the access check (29 Oct 2026)

**Current enough to use:**
- `comp.secd` and `comp.g_secd`: readable. The raw `MAX(datadate)` returned **2027-11-12** and **2028-12-01**, each with **1 row**. These are erroneous future-dated records, not real coverage (see §2.4).
- `comp.g_exrt_dly`: current to 2026-10-28.
- `comp.funda`, `fundq`, `g_funda`, `g_fundq`: latest `datadate` 2026-09-30 (fiscal period ends; normal for late October).
- `ff.factors_daily`: to 2026-09-30.

**Lagging:**
- CRSP `dsf_v2` and `msf_v2`: to **2025-12-31** (annual/quarterly update vintages). Legacy `crsp.dsf` has no rows after mid-2025.
- `crsp_q_stock` is visible; `aim verify` checks whether its `dsf_v2` is any more recent.

**Readable (sample-table checks):**
- `comp_snapshot` (125 tables), `ibes` (194), `tr_ds_equities` (43), `ciq` (259), `ravenpack_dj`, `wrdsapps_finratio`, `ff_all`.

### 2.4 Data-quality rules (mandatory)

1. **Effective latest date.** A table's latest usable date is the most recent date $d$ (on or before the current date) with
   $$n(d) \ge 0.5 \times \operatorname{median}\{n(d') : d' \in \text{previous 20 trading days}\},$$
   where $n(d)$ is the row count on date $d$. This removes the bogus future-dated rows found in `secd` / `g_secd`. Discard every row dated after the current date and log how many there were.
2. **Coverage gate.** Before building factors at as-of date $T$, require effective latest date ≥ $T$ for prices and FX. Otherwise move $T$ back to the latest common covered date and record the change.
3. **Return sanity.** Flag |daily return| > 100%. Drop it if it reverses the next day, which indicates a price error. Never drop silently.
4. **Duplicate rows.** Deduplicate on (`gvkey`, `iid`, `datadate`), keeping the row with non-null `prccd` and `trfd`.

### 2.5 Derived quantities

- **Daily total return**, per (`gvkey`, `iid`), converted to USD with the daily cross-rate before computing any descriptor:
  $$r_t = \frac{(\text{prccd}_t/\text{ajexdi}_t)\,\text{trfd}_t}{(\text{prccd}_{t-1}/\text{ajexdi}_{t-1})\,\text{trfd}_{t-1}} - 1.$$
  If `trfd` is missing, use the price return and flag it. Use the primary issue for returns.
- **Issuer market cap**: $\sum_{\text{issues}} \text{cshoc}\times\text{prccd}\times\text{FX}$ at the `gvkey` level, so multi-class firms are sized correctly.
- **Universe `acwi_proxy` (global replication).** Use an actual MSCI ACWI list from Datastream if `aim verify` finds one. Otherwise:
  - take primary common equity (`tpci = '0'`) in ACWI member countries (country list in config);
  - within each country, take the largest issuers until 85% of cumulative USD market cap is reached;
  - log the count (expected ~2,500–3,000).

  Full market cap is used instead of free float; this is noted in `DEVIATIONS.md`.
- **Universe `us_broad` (team focus).**
  - US-exchange listings (`exchg` ∈ {11, 12, 14}) of common stock and ADRs (`tpci` ∈ {'0','F'}), with market cap ≥ $300m.
  - Non-US holdings map to their US ADR line through CIQ where one exists; otherwise they are flagged `outside_universe`.
  - Secondary benchmark: S&P 1500 membership from `idxcst_his`.

### 2.6 Validation against CRSP (uses the 2024–2025 overlap)

For US issuers present in both CRSP and Compustat over 1 Jan 2024 – 31 Dec 2025, link `permno` ↔ `gvkey` through `crsp.ccmxpf_lnkhist` and compare:
- daily total returns;
- market caps;
- 12-1 momentum.

Report the correlation and the 99th percentile of absolute differences.

**Acceptance:** correlation > 0.99 for daily returns and the median absolute difference below 1 bp. This validates the Compustat return construction before it is used for an as-of date that CRSP does not reach.

---

## 3. Repository layout

```
ai-margin/
├── BUILD_BRIEF.md · README.md · pyproject.toml · .env.example
├── config/
│   ├── models.yaml · experiment.yaml · universe.yaml · factors.yaml
│   ├── sources.yaml          # primary/fallback per input (§2.2)
│   ├── wrds_schema.yaml      # logical field -> physical column, filled by `aim verify`
│   └── prompts/  freeform_en.yaml · freeform_zh.yaml · mandates_en.yaml · output_suffix.yaml
├── data/  raw/{api,wrds}/ · interim/ · processed/ · manual/{ticker_overrides,crosslisting_overrides,query_labels_gold}.csv
├── src/aimargin/
│   ├── providers/  base.py · openai_adapter.py · anthropic_adapter.py
│   ├── collect/    planner.py · runner.py · batch.py · ratelimit.py · cost.py
│   ├── store/      db.py · schemas.py
│   ├── parse/      extract.py · validate.py · refusal.py
│   ├── resolve/    ciq_resolver.py · comp_resolver.py · fuzzy.py · crosslist.py
│   ├── wrds_io/    connect.py · verify.py · freshness.py · prices.py · fx.py · rf.py ·
│   │               snapshot.py · fundamentals.py · ibes.py · ciq.py · datastream.py · ravenpack.py · crsp_validate.py
│   ├── factors/    returns.py · universe.py · descriptors.py · standardise.py · exposures.py
│   ├── analysis/   overlap.py · consensus.py · exposure_stats.py · mandates.py · search_usage.py ·
│   │               query_classify.py · language.py · generations.py · refusals.py · reasoning.py ·
│   │               compliance.py · attention.py · bootstrap.py
│   ├── figures/    fig1_overlap.py … fig7_queries.py
│   └── cli.py
├── tests/ · notebooks/ (exploratory only)
└── docs/  PHASE0_VERIFICATION.md · DEVIATIONS.md · DATA_DICTIONARY.md · RUNBOOK.md · RESULTS.md
```

**CLI:**
```
aim verify
aim plan     --stage {A,B,C} [--dry-run]
aim collect  --stage {A,B,C} [--pilot N] [--batch] [--resume]
aim parse | aim resolve
aim wrds pull --asof YYYY-MM-DD --universe {acwi_proxy,us_broad}
aim wrds validate-crsp
aim factors build --asof YYYY-MM-DD --universe ...
aim exposures | aim analyze [--section ...] | aim figures | aim report
```

---

## 4. Storage schemas (DuckDB over parquet; raw API responses as JSON)

**`calls`** — one row per API call:
- **Identity:** `call_id` (deterministic hash), `run_id`, `stage`, `provider`, `model_requested`, `model_returned`, `role`, `generation`, `size_class`.
- **Prompt:** `prompt_family`, `prompt_id`, `language`, `rep`, `search_enabled`, `search_tool_version`.
- **Settings:** `api_version`, `reasoning_effort_effective`, `via_batch`.
- **Timing:** `submitted_ts_utc`, `completed_ts_utc`, `latency_s`.
- **Usage and cost:** `input_tokens`, `output_tokens`, `reasoning_tokens`, `search_count`, `est_cost_usd`.
- **Outcome:** `stop_reason`, `provider_refusal_flag`, `http_status`, `error`, `raw_path`.

**`responses`** — `call_id`, `final_text`, `reasoning_text`, `reasoning_word_count`, `tool_events_json`.

**`search_events`** — `call_id`, `event_idx`, `provider_event_type`, `query_text`, `query_visible`, `caller`, `result_urls_json`, `query_class`, `mentioned_tickers_json`, `class_method`.

**`portfolios`** — `call_id`, `parse_status`, `n_names_raw`, `n_names_resolved`, `weights_provided`, `weight_sum_raw`, `notes`.

**`holdings`** — `call_id`, `position_idx`, `raw_ticker`, `raw_exchange`, `raw_name`, `raw_weight`, `weight_norm`, `ciq_companyid`, `ciq_tradingitemid`, `gvkey`, `iid`, `issuer_id`, `resolved_name`, `isin`, `sedol`, `cusip`, `fic`, `exchg`, `gics_sector`, `is_adr`, `is_china_a_share`, `in_universe_acwi`, `in_universe_us`, `resolution_method`, `resolution_confidence`, `resolution_status`.

**`descriptors` / `exposures`** — `asof_date`, `universe`, `issuer_id`, raw descriptors, standardised `size, value, quality, momentum, resvol, lowvol, beta`, plus `fwd_ep`, `analyst_count`, `news_count_30d`, `in_estimation_universe`, `source_flags`, `missing_flags`.

**`portfolio_exposures`** — `call_id`, `asof_date`, `universe`, `weighting` (model or equal), factor columns, `coverage_weight`.

**`source_log`** — `asof_date`, `input`, `source_used`, `fallback_used`, `effective_latest_date`, `rows`, `notes`.

---

## 5. Prompts

The paper does not publish its prompts. Freeze ours, identified by a `prompt_version` hash, before production, and never edit them after collection starts.

### 5.1 Free-form framings (Stages A, C)

Each is followed by the output suffix in §5.3.

- **L1:** "Pick 10 stocks for me to buy."
- **L2:** "I have $100,000 I'd like to invest in individual stocks. Which 10 stocks should I buy, and how much of the money should go into each?"
- **L3:** "I'm an investor with a five-year horizon and moderate risk tolerance. I want a diversified portfolio of 10 listed equities from anywhere in the world, with a weight for each. I want reasonable diversification across sectors and I don't want any single stock above 20% of the portfolio. What should I buy?"
- **L4:** "You are a portfolio manager at an institutional asset manager. Construct a concentrated, high-conviction portfolio of 10 global equities benchmarked against the MSCI ACWI, for a long-only fund with a three-to-five-year horizon. Choose stocks you expect to outperform the benchmark, assign position weights, and respect sensible diversification and liquidity limits for an institutional fund."

### 5.2 Mandates (Stages B, C)

Each mandate is 300–400 words: a common block plus a style block. Claude Code drafts the four full texts; the team reviews and freezes them.

**Common block:**
- Fund X: long-only global equity, benchmarked to MSCI ACWI (net, USD).
- 10 holdings, each weighted 5–15%, summing to 100%.
- At least four GICS sectors.
- Market cap at least US$5bn, with adequate liquidity.
- Listed common equity only. No tracking-error constraint. Quarterly rebalancing.
- The manager must state ticker, exchange and weight for each holding.

**Style blocks:**
- **VALUE:** low price-to-book, low price-to-earnings, high cash-flow yield; materially more value exposure than the benchmark; avoid value traps.
- **QUALITY:** high ROE and ROA, low leverage, stable earnings.
- **MOMENTUM:** strongest price performance over the past 12 months excluding the most recent month, **measured as of today**.
- **UNCONSTRAINED:** no style bias.

### 5.3 Output suffix

> "At the end of your answer, include a JSON code block of the form `{"portfolio": [{"ticker": "...", "exchange": "...", "company": "...", "weight_pct": number}, ...]}` containing exactly 10 holdings whose weights sum to 100."

Do not use structured-output modes; they would suppress refusals.

### 5.4 Call rules

- No system prompt and no sampling parameters. Use default reasoning effort.
- Each call is a fresh conversation (OpenAI `store: false`).
- Stage C: the search tool is enabled and the model chooses whether to use it.
- **Collect each stage inside a short window.** As-of date $T$ = the last trading day of the window. If it is not covered by WRDS on build day, apply the coverage gate (§2.4); the factor build can be rerun later once data catch up.

---

## 6. Collection, parsing, resolution

### 6.1 Runner

- Asynchronous, with per-provider limits. Use exponential backoff with jitter and honour `Retry-After`; this includes OpenAI's `429 slow_down` and `503 server_is_overloaded`.
- Idempotent through `call_id`, so runs can be resumed.
- Transport errors are retried. **Refusals and malformed outputs are observations: never retried.**
- `--batch` mode (Stages A and B) records submission and completion times.
- Raw responses are written to disk before any parsing.
- A budget guard enforces a cost cap per stage.

### 6.2 Adapters

```python
class ProviderAdapter:
    def build_request(self, prompt_text, search_enabled, params) -> dict
    def send(self, request) -> dict
    def normalise(self, raw) -> NormalisedResponse   # final_text, reasoning_text, tool_events, usage, model_returned, stop_reason, refusal_flag
```

- **OpenAI:** Responses API. Read message items, `web_search_call` items and refusal content parts.
- **Anthropic:** pinned API version. Read `server_tool_use` blocks (including nested ones with `caller`) and `web_search_tool_result` blocks (including error codes). Implement the `pause_turn` loop and map `stop_reason: "refusal"`.

### 6.3 Parsing and outcomes

1. **Extract the portfolio.** Take the last JSON block. If that fails, fall back to deterministic list or table extraction and set `parse_method = fallback`.
2. **Classify the outcome** as one of:
   - `refusal`: a provider refusal flag, or a decline with no list. Detected by rule-based phrases with a second opinion from an LLM judge; disagreements go to human review.
   - `format_failure`: a list is present but cannot be recovered.
   - `insufficient_names`: fewer than 10 distinct issuers.
   - `valid`: exactly 10 distinct issuers.
3. **Weights.** Normalise if all ten are valid; otherwise use equal weights and set `weights_provided = False`. Report results under both weightings.

### 6.4 Security resolution (Capital IQ first)

1. **Normalise ticker strings.** Strip `$` and exchange suffixes. Parse forms such as `BRK.B`/`BRK-B`, `0700.HK`, `600519.SS`/`.SH`, `000858.SZ`, `2330.TW`, `ASML.AS`, `NOVO-B.CO`. Map exchange words to a canonical exchange code (config table).
2. **CIQ match.** Match (ticker, exchange) to a CIQ trading item active at $T$, then trading item → security → company, then company → `gvkey` via `ciq_common`.
3. **Compustat match.** If CIQ fails, match exactly on (`tic`, `exchg`) in `comp.security` / `comp.g_security`.
4. **Name match.** Fuzzy-match `company` against CIQ company names and Compustat `conm`. Matches below the confidence threshold go to `data/manual/ticker_overrides.csv`.
5. **Issuer collapse.**
   - `issuer_id` = the CIQ company ID, mapped to the primary `gvkey`.
   - Share classes (GOOGL/GOOG) and cross-listings/ADRs (TSM↔2330.TW, NVO↔NOVO-B.CO, ASML↔ASML.AS) collapse automatically because they share a CIQ company.
   - `crosslisting_overrides.csv` exists only for exceptions.
6. **Flags.** Set `is_adr`, `is_china_a_share` and universe membership.

**Acceptance:** at least 99% of holdings resolved, and the four collapse tests above pass.

---

## 7. Factor exposures (Barra-style replica)

**Inputs:**
- Returns: daily USD total returns from §2.5.
- Risk-free rate: from §2.2, forward-filled where flagged.
- EWMA weights: $w_t\propto 2^{-(T-t)/h}$, where $T$ is the as-of date and $h$ the half-life.
- All windows and half-lives live in `factors.yaml`.

### 7.1 Standardisation (per universe and as-of date)

Winsorise each raw descriptor at the 1st/99th percentiles, then standardise with a cap-weighted mean and an equal-weighted standard deviation:
$$z_i=\frac{d_i-\sum_{j\in U}w^{cap}_jd_j}{\sqrt{\tfrac1N\sum_{j\in U}(d_j-\bar d)^2}}$$

- This gives zero cap-weighted exposure, so loadings are in standard deviations, matching the paper's units.
- **Composites:** average whichever sub-descriptors are available (re-weighted), then re-standardise.
- **Missing data:** a stock with no data for a factor stays missing and flagged. Never zero-fill.

### 7.2 Descriptors

- **Size:** $\ln$(issuer market cap).
- **Beta (control):** EWMA regression of excess returns on the excess cap-weighted universe return. Window 252 days, $h = 63$.
- **Momentum (RSTR):**
  $$\text{RSTR} = \sum_{t=T-L-W}^{T-L} w_t\,[\ln(1+r_t)-\ln(1+r_{f,t})]$$
  with $W = 504$, $L = 21$, $h = 126$. A simple 12-1 month return is computed as a robustness check.
- **Residual volatility:** $0.74\,\text{DASTD} + 0.16\,\text{CMRA} + 0.10\,\text{HSIGMA}$, orthogonalised to Beta and Size. **Low-Vol = −ResVol.**
  - DASTD: EWMA standard deviation of daily excess returns, 252 days, $h = 42$.
  - CMRA: the range of 12 monthly cumulative excess log returns.
  - HSIGMA: EWMA standard deviation of the beta-regression residuals, $h = 63$.
- **Value:** book-to-price, using point-in-time book equity from Snapshot (or the fallback). Robustness arm: a blend of BTOP, trailing E/P and **I/B/E/S forward E/P** (12-month-forward consensus EPS interpolated from FY1/FY2, divided by price).
- **Quality:** an equal-weighted composite of four sub-factors:
  - Profitability: ROA, ROE, gross profit / assets.
  - Leverage, sign-flipped: debt / assets.
  - Earnings variability, sign-flipped: 5-year standard deviation of earnings growth (minimum 3 years).
  - Accruals, sign-flipped: (ib − oancf) / at.

  All are computed from point-in-time fundamentals.

### 7.3 Validation

- Synthetic unit tests, and a check that cap-weighted universe exposures are approximately zero.
- The CRSP comparison (§2.6).
- US quality inputs compared against `wrdsapps_finratio`: rank correlations reported.
- Point-in-time vs restated comparison: compute value and quality both from Snapshot and from standard Compustat for the same date, and report how much the exposures differ. This quantifies the look-ahead bias that point-in-time data removes.
- Global spot check: compare 12-1 momentum for 50 non-US issuers against Datastream total-return indices.

### 7.4 Portfolio exposure

$$X_{pk}=\sum_{i\in p}w_ix_{ik}$$

Weights are re-normalised over holdings with data, and `coverage_weight` is recorded. Computed under model weights and equal weights, alongside GICS sector weights.

---

## 8. Analyses

All headline statistics carry **bootstrap 95% confidence intervals** (2,000 draws, resampling repetitions within cells). Group contrasts use permutation tests.

### 8.1 Name overlap (Fig. 1)

$J(A,B)=|A\cap B|/|A\cup B|$ on issuer sets, averaged over all pairs of repetitions. Reported by framing (L1–L4):
- **(a)** the two flagships (headline);
- **(b)** all OpenAI × Anthropic model pairs;
- **(c)** within-provider cross-model pairs;
- **(d)** within-model pairs (determinism baseline);
- plus a 12 × 12 heatmap.

### 8.2 Consensus names

A stock is a consensus name for a model if it appears in at least 50% of that model's repetitions. Report two-flagship and all-12 consensus sets, and how they change from L1 to L4.

### 8.3 Factor profiles (Figs. 2–3)

- Mean exposures by model, with the sector mix.
- Mean exposures by framing.
- Compare the cross-model standard deviation of exposures with $1-\bar J$. This tests the paper's "different names, similar positions" claim.

### 8.4 Mandate responses (Fig. 4)

For model $m$ and mandate $s$ targeting factor $k(s)$:
$$\Delta_{m,s}=\bar X_{m,s,k(s)}-\bar X_{m,\text{UNCONSTR},k(s)},$$
with confidence intervals. Also report the full exposure vectors and the Jaccard overlap between mandate books.

### 8.5 Search on vs off (Fig. 5)

Momentum exposure by task and model, offline vs connected. Split the connected results by whether search was actually invoked, and repeat with 12-1 momentum.

### 8.6 Search invocation and queries (Figs. 6–7)

- Share of calls that invoke search, by model × prompt.
- **Query classes:** `single_stock_check`, `screen_or_list`, `factor_or_market_data`, `macro_news`, `other`. Classify with rules plus an LLM; measure against a gold set of at least 200 hand-labelled queries and report Cohen's κ.
- **Lookup-to-portfolio share:** fraction of single-stock checks whose stock ends up in the final book (caveat: measured after the fact).
- **Ordering test:** whether screens come before single-stock checks within a call.
- Anthropic only: dynamic-filtering vs basic search tool.

### 8.7 Language (optional arm)

English vs Mandarin: share of China A-shares, HK-listed and US-listed holdings; Jaccard; exposures.

### 8.8 Model size and generation

Within each provider:
- flagship vs mid vs small;
- current vs older generations;
- factor profiles and Jaccard to the same-provider flagship.

### 8.9 Refusals and output failures

Rates by framing × model. Paper benchmark: about 26% at L1 and at most 2% elsewhere.

### 8.10 Reasoning vs delivery

Within mandate cells, regress the delivered target exposure on reasoning length and on whether the reasoning mentions the constraint.

### 8.11 Mandate compliance

A book passes if:
- its target exposure exceeds +0.25σ;
- no weight exceeds 15%;
- it spans at least four sectors;
- every holding's market cap is at least $5bn.

Report pass rates by model × search state.

### 8.12 Attention and familiarity (extension enabled by WRDS; not in the paper)

For each pick, compare the stock's analyst count (I/B/E/S) and 30-day news count (RavenPack) with the cap-matched universe distribution. Report the average percentile by framing, mandate and search state.

This tests the paper's untested conjecture that models "retain familiar candidates", and gives the team a measurable characteristic for a later trading strategy.

---

## 9. Figures

1. Jaccard overlap by framing.
2. Loadings by model, with sector mix.
3. Loadings by framing.
4. Mandate loadings and Δ.
5. Momentum, offline vs connected.
6. Search-invocation heatmap.
7. Query-type bars.

Plus tables: refusals, compliance, generation comparison, CRSP validation, point-in-time vs restated, attention. Every figure is saved as PNG with its underlying CSV.

---

## 10. Reproducibility and governance

- **Versioning:** `experiment_version` hashes the prompts, model roster, parameters and API versions. `source_log` records which data source fed each input on each as-of date.
- **Raw data are immutable.** One command chain regenerates everything from them.
- **WRDS licensing:** `data/raw/wrds` and any derived file containing raw vendor values never go to a public repository; `.gitignore` enforces this. Aggregated results and exposures for the ~hundreds of resolved names may be shared with the team and Man Group only. Check the WRDS terms before sharing anything outside the university.
- **`DEVIATIONS.md` lists:**
  - 2 providers instead of 6;
  - our own prompts;
  - the replica factor model instead of Barra;
  - the ACWI proxy (if Datastream has no list);
  - full-cap rather than free-float weighting;
  - forward-filled risk-free rate;
  - Compustat rather than CRSP for current prices.

---

## 11. Build phases and acceptance criteria

**Phase 0 — `aim verify`.**
- Confirm models and search-field capture.
- Probe WRDS schemas into `wrds_schema.yaml`.
- Compute effective latest dates.
- Choose sources and write `source_log`.
- Check `crsp_q_stock` vintage, Snapshot global coverage, Datastream MSCI lists and the CIQ ↔ gvkey link.

✅ `PHASE0_VERIFICATION.md` written; every input has a working source.

**Phase 1 — Skeleton and config.**
✅ `aim plan --stage A --dry-run` shows 1,440 planned calls and their cost.

**Phase 2 — Adapters and pilot.**
✅ `--pilot 2` succeeds for every cell, offline and connected; budget re-estimated.

**Phase 3 — WRDS layer and factor engine.**
✅ CRSP validation passes (§2.6). Synthetic tests pass. Universe sizes logged. Point-in-time vs restated comparison produced.

**Phase 4 — Parsing and resolution.**
✅ At least 99% resolution on pilot outputs; collapse tests pass.

**Phase 5 — Full collection.**
Freeze prompts, then run Stages A–C inside one window.
✅ Planned call counts met.

**Phase 6 — Analyses, figures and report.**
✅ `docs/RESULTS.md` shows our numbers next to the paper's headline numbers, with each difference explained.

**Phase 7 — Extensions (designed now).**
- Repeat Stages A–C at a second and third date.
- Run everything on the `us_broad` universe.
- **Forced-discovery arm:** the model must choose from a timestamped WRDS screen, e.g. the top 100 stocks by our momentum, value or quality score at $T$. Log the candidate set and apply the same compliance tests. This is the paper's proposed next experiment.
- Add further providers.
