"""Table definitions (BUILD_BRIEF §4), with a few extra audit columns.

Every table has an explicit primary key so writes are idempotent upserts.
"""

from __future__ import annotations

TABLES: dict[str, dict] = {
    "calls": {
        "pk": ["call_id"],
        "columns": [
            ("call_id", "VARCHAR"), ("run_id", "VARCHAR"), ("experiment_version", "VARCHAR"),
            ("prompt_version", "VARCHAR"), ("stage", "VARCHAR"), ("provider", "VARCHAR"),
            ("model_requested", "VARCHAR"), ("model_returned", "VARCHAR"), ("role", "VARCHAR"),
            ("generation", "VARCHAR"), ("size_class", "VARCHAR"), ("prompt_family", "VARCHAR"),
            ("prompt_id", "VARCHAR"), ("language", "VARCHAR"), ("rep", "INTEGER"),
            ("search_enabled", "BOOLEAN"), ("search_tool_version", "VARCHAR"), ("api_version", "VARCHAR"),
            ("reasoning_effort_effective", "VARCHAR"), ("via_batch", "BOOLEAN"),
            ("submitted_ts_utc", "VARCHAR"), ("completed_ts_utc", "VARCHAR"), ("latency_s", "DOUBLE"),
            ("input_tokens", "BIGINT"), ("output_tokens", "BIGINT"), ("reasoning_tokens", "BIGINT"),
            ("search_count", "INTEGER"), ("est_cost_usd", "DOUBLE"), ("stop_reason", "VARCHAR"),
            ("provider_refusal_flag", "BOOLEAN"), ("http_status", "INTEGER"), ("error", "VARCHAR"),
            ("attempts", "INTEGER"), ("raw_path", "VARCHAR"), ("status", "VARCHAR"),
        ],
    },
    "responses": {
        "pk": ["call_id"],
        "columns": [
            ("call_id", "VARCHAR"), ("final_text", "VARCHAR"), ("reasoning_text", "VARCHAR"),
            ("reasoning_word_count", "INTEGER"), ("tool_events_json", "VARCHAR"),
        ],
    },
    "search_events": {
        "pk": ["call_id", "event_idx"],
        "columns": [
            ("call_id", "VARCHAR"), ("event_idx", "INTEGER"), ("provider_event_type", "VARCHAR"),
            ("query_text", "VARCHAR"), ("query_visible", "BOOLEAN"), ("caller", "VARCHAR"),
            ("result_urls_json", "VARCHAR"), ("error_code", "VARCHAR"), ("query_class", "VARCHAR"),
            ("mentioned_tickers_json", "VARCHAR"), ("class_method", "VARCHAR"),
        ],
    },
    "portfolios": {
        "pk": ["call_id"],
        "columns": [
            ("call_id", "VARCHAR"), ("parse_status", "VARCHAR"), ("parse_method", "VARCHAR"),
            ("outcome", "VARCHAR"), ("refusal_rule", "BOOLEAN"), ("refusal_judge", "VARCHAR"),
            ("n_names_raw", "INTEGER"), ("n_names_resolved", "INTEGER"), ("n_issuers", "INTEGER"),
            ("weights_provided", "BOOLEAN"), ("weight_sum_raw", "DOUBLE"), ("notes", "VARCHAR"),
        ],
    },
    "holdings": {
        "pk": ["call_id", "position_idx"],
        "columns": [
            ("call_id", "VARCHAR"), ("position_idx", "INTEGER"), ("raw_ticker", "VARCHAR"),
            ("raw_exchange", "VARCHAR"), ("raw_name", "VARCHAR"), ("raw_weight", "DOUBLE"),
            ("weight_norm", "DOUBLE"), ("weight_equal", "DOUBLE"), ("ciq_companyid", "VARCHAR"),
            ("ciq_tradingitemid", "VARCHAR"), ("gvkey", "VARCHAR"), ("iid", "VARCHAR"),
            ("issuer_id", "VARCHAR"), ("resolved_name", "VARCHAR"), ("resolved_ticker", "VARCHAR"),
            ("isin", "VARCHAR"), ("sedol", "VARCHAR"), ("cusip", "VARCHAR"), ("fic", "VARCHAR"),
            ("country", "VARCHAR"), ("exchg", "VARCHAR"), ("exchange_code", "VARCHAR"),
            ("gics_sector", "VARCHAR"), ("is_adr", "BOOLEAN"), ("is_china_a_share", "BOOLEAN"),
            ("is_hk_listed", "BOOLEAN"), ("is_us_listed", "BOOLEAN"), ("in_universe_acwi", "BOOLEAN"),
            ("in_universe_us", "BOOLEAN"), ("resolution_method", "VARCHAR"),
            ("resolution_confidence", "DOUBLE"), ("resolution_status", "VARCHAR"),
            ("duplicate_of", "INTEGER"),
        ],
    },
    "descriptors": {
        "pk": ["asof_date", "universe", "issuer_id"],
        "columns": [
            ("asof_date", "VARCHAR"), ("universe", "VARCHAR"), ("issuer_id", "VARCHAR"),
            ("gvkey", "VARCHAR"), ("iid", "VARCHAR"), ("name", "VARCHAR"), ("country", "VARCHAR"),
            ("gics_sector", "VARCHAR"), ("mcap_usd", "DOUBLE"), ("ln_mcap", "DOUBLE"), ("beta_raw", "DOUBLE"),
            ("rstr_raw", "DOUBLE"), ("mom_12_1_raw", "DOUBLE"), ("dastd_raw", "DOUBLE"), ("cmra_raw", "DOUBLE"),
            ("hsigma_raw", "DOUBLE"), ("btop_raw", "DOUBLE"), ("etop_raw", "DOUBLE"), ("fwd_ep_raw", "DOUBLE"),
            ("roa_raw", "DOUBLE"), ("roe_raw", "DOUBLE"), ("gpa_raw", "DOUBLE"), ("debt_assets_raw", "DOUBLE"),
            ("earn_var_raw", "DOUBLE"), ("accruals_raw", "DOUBLE"), ("analyst_count", "DOUBLE"),
            ("news_count_30d", "DOUBLE"), ("in_estimation_universe", "BOOLEAN"),
            ("source_flags", "VARCHAR"), ("missing_flags", "VARCHAR"),
        ],
    },
    "exposures": {
        "pk": ["asof_date", "universe", "issuer_id"],
        "columns": [
            ("asof_date", "VARCHAR"), ("universe", "VARCHAR"), ("issuer_id", "VARCHAR"),
            ("size", "DOUBLE"), ("value", "DOUBLE"), ("value_blend", "DOUBLE"), ("quality", "DOUBLE"),
            ("momentum", "DOUBLE"), ("mom_12_1", "DOUBLE"), ("resvol", "DOUBLE"), ("lowvol", "DOUBLE"),
            ("beta", "DOUBLE"), ("fwd_ep", "DOUBLE"), ("analyst_count", "DOUBLE"), ("news_count_30d", "DOUBLE"),
            ("mcap_usd", "DOUBLE"), ("gics_sector", "VARCHAR"), ("country", "VARCHAR"),
            ("in_estimation_universe", "BOOLEAN"), ("cap_weight", "DOUBLE"), ("source_flags", "VARCHAR"),
            ("missing_flags", "VARCHAR"),
        ],
    },
    "portfolio_exposures": {
        "pk": ["call_id", "asof_date", "universe", "weighting"],
        "columns": [
            ("call_id", "VARCHAR"), ("asof_date", "VARCHAR"), ("universe", "VARCHAR"), ("weighting", "VARCHAR"),
            ("size", "DOUBLE"), ("value", "DOUBLE"), ("value_blend", "DOUBLE"), ("quality", "DOUBLE"),
            ("momentum", "DOUBLE"), ("mom_12_1", "DOUBLE"), ("resvol", "DOUBLE"), ("lowvol", "DOUBLE"),
            ("beta", "DOUBLE"), ("coverage_weight", "DOUBLE"), ("n_covered", "INTEGER"),
            ("sector_weights_json", "VARCHAR"), ("country_weights_json", "VARCHAR"),
        ],
    },
    "momentum_history": {
        "pk": ["asof_date", "lag_months", "issuer_id"],
        "columns": [
            ("asof_date", "VARCHAR"), ("lag_months", "INTEGER"), ("measure_date", "VARCHAR"),
            ("issuer_id", "VARCHAR"), ("mom_12_1", "DOUBLE"), ("mom_12_1_z", "DOUBLE"),
        ],
    },
    "source_log": {
        "pk": ["asof_date", "input"],
        "columns": [
            ("asof_date", "VARCHAR"), ("input", "VARCHAR"), ("source_used", "VARCHAR"),
            ("fallback_used", "BOOLEAN"), ("effective_latest_date", "VARCHAR"), ("rows", "BIGINT"),
            ("notes", "VARCHAR"), ("logged_ts_utc", "VARCHAR"),
        ],
    },
    "drop_log": {
        "pk": ["log_id"],
        "columns": [
            ("log_id", "VARCHAR"), ("stage", "VARCHAR"), ("entity", "VARCHAR"), ("reason", "VARCHAR"),
            ("detail", "VARCHAR"), ("logged_ts_utc", "VARCHAR"),
        ],
    },
}
