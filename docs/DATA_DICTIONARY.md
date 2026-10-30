# Data dictionary

Everything lives in one DuckDB file per workspace: `data/processed/aim.duckdb` for the live run, and
`data/demo/processed/aim.duckdb` for the synthetic demo. Raw provider responses are JSON files under
`data/raw/api/<stage>/<model>/<call_id>.json`, written before any parsing. Column definitions are in
`src/aimargin/store/schemas.py`.

## calls: one row per API call

| Column | Meaning |
|---|---|
| `call_id` | Deterministic hash of (stage, model, prompt, language, rep, search flag, tool version, prompt_version) |
| `run_id`, `experiment_version`, `prompt_version` | Provenance |
| `stage`, `provider`, `model_requested`, `model_returned`, `role`, `generation`, `size_class` | Identity |
| `prompt_family`, `prompt_id`, `language`, `rep`, `search_enabled`, `search_tool_version` | Prompt |
| `api_version`, `reasoning_effort_effective`, `via_batch` | Settings. Effort is read from the response when exposed, else `default:<documented default>` |
| `submitted_ts_utc`, `completed_ts_utc`, `latency_s`, `attempts` | Timing |
| `input_tokens`, `output_tokens`, `reasoning_tokens`, `search_count`, `est_cost_usd` | Usage and cost |
| `stop_reason`, `provider_refusal_flag`, `http_status`, `error`, `status` | Outcome (`status` is `completed` or `error`) |

## responses

`final_text`, `reasoning_text`, `reasoning_word_count`, and `tool_events_json` (every normalised tool event).

## search_events: one row per search event

`provider_event_type` is `web_search_call` (OpenAI) or `server_tool_use` (Anthropic). The other columns:

- `query_text` and `query_visible`;
- `caller` (Anthropic dynamic filtering);
- `result_urls_json` and `error_code`;
- `query_class` (rules) and `mentioned_tickers_json`.

## portfolios: one row per call

`parse_status` (refusal, format_failure or parsed) and `parse_method` (json, fallback_table, fallback_list or
none). The other columns:

- `outcome`: valid, insufficient_names, excess_names, format_failure, refusal or api_error;
- `n_names_raw`, `n_names_resolved` and `n_issuers`;
- `weights_provided` and `weight_sum_raw`.

## holdings: one row per position

- **Raw fields:** `raw_ticker`, `raw_exchange`, `raw_name`, `raw_weight`.
- **Weights:** `weight_norm` (model weights normalised, or equal weights if any weight is missing) and
  `weight_equal`.
- **Resolution:**
  - `issuer_id`: the CIQ company id, or `gvkey:` plus the gvkey;
  - `ciq_*`, `gvkey`, `iid`, `isin`, `sedol`, `cusip`;
  - `country`, `exchange_code`, `gics_sector`;
  - `resolution_method`, `resolution_confidence` and `resolution_status`.
- **Flags:** `is_adr`, `is_china_a_share`, `is_hk_listed`, `is_us_listed`, `in_universe_acwi`, `in_universe_us`,
  and `duplicate_of` (another position of the same issuer).

## descriptors / exposures: one row per (as-of, universe, issuer)

- **Raw descriptors:** `beta_raw`, `rstr_raw`, `mom_12_1_raw`, `dastd_raw`, `cmra_raw`, `hsigma_raw`, `btop_raw`,
  `etop_raw`, `fwd_ep_raw`, `roa_raw`, `roe_raw`, `gpa_raw`, `debt_assets_raw`, `earn_var_raw`, `accruals_raw`.
- **Standardised exposures:** `size`, `value`, `value_blend`, `quality`, `momentum`, `mom_12_1`, `resvol`, `lowvol`
  (= −resvol), `beta`, `fwd_ep`.
- **Other fields:** `mcap_usd` and `cap_weight`, `analyst_count`, `news_count_30d`, `in_estimation_universe`,
  `source_flags`, and `missing_flags` (factors left missing, never zero-filled).

## portfolio_exposures: one row per (call, as-of, universe, weighting)

`weighting` is `model` or `equal`. The table holds the factor loadings (each re-normalised over holdings that have
data), plus `coverage_weight`, `n_covered`, `sector_weights_json` and `country_weights_json`.

## momentum_history

12-1 momentum (raw and z-score) for every issuer, measured 0–18 months before the as-of date. Used by the
information-date analysis.

## source_log / drop_log

- `source_log`: which source fed each input on each as-of date, with row counts and notes.
- `drop_log`: every dropped or flagged observation, with a reason.

## Outputs

| Path | Contents |
|---|---|
| `outputs/analysis.json` | Every analysis (input to the figures, the report and the dashboard) |
| `outputs/tables/*.csv` | Tables: exposures, mandate Δs, refusals, compliance, PIT vs restated, finratio check, … |
| `outputs/figures/*.png` + `.csv` | Figures 1–7 and the extension figures, each with its data |
| `dashboard/*.json` | Dashboard export (`meta`, `status`, `analysis`, `portfolios`, `details/<call_id>.json`) |
