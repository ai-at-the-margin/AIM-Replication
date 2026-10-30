# Phase 0 verification

Generated 2026-10-30T03:56:06+00:00 by `aim verify` (workspace: **live**).

- experiment_version: `e8b3057cb576`
- prompt_version: `2ed04e116046`

## Verdict

Every required input has a working source.

## Providers

### openai

- API key present: True
- models confirmed: gpt-6-astra, gpt-6.1-sol, gpt-6.1-terra, gpt-6-luna, gpt-5.6-sol, gpt-5.5, chat-latest
- models missing: none
- search test (gpt-6.1-sol): OK; events=1; queries=['AAPL historical data October 29 2026 closing stock price']

### anthropic

- API key present: True
- models confirmed: claude-fable-5-1, claude-opus-5-5, claude-sonnet-5-5, claude-haiku-5-5, claude-fable-5, claude-opus-4-8
- models missing: none
- search test (claude-opus-5-5): FAILED; events=None; queries=None; error=HTTP 400: {"type":"error","error":{"type":"invalid_request_error","message":"Your credit balance is too low to access the Anthropic API. Please go to Plans & Billing to upgrade or purchase credits."},"request_id":"req_011CgXkMhhFf9stoBa1XesZw"}

## WRDS

- host: wrds-pgdata.wharton.upenn.edu:9737
- connected: True

| logical table | ok | physical table | effective latest | raw max | future rows dropped | note |
|---|---|---|---|---|---|---|
| comp_secd | True | comp.secd | 2026-10-28 | 2027-11-12 | 1801 | n=21870 on effective date; discarded 1801 future-dated rows on 68 dates |
| comp_g_secd | True | comp.g_secd | 2026-10-28 | 2028-12-01 | 5547 | n=84538 on effective date; discarded 5547 future-dated rows on 154 dates |
| ds_primqtri | True | tr_ds_equities.ds2primqtri | 2026-10-28 | 2026-10-28 | 0 | n=75552 on effective date; discarded 0 future-dated rows on 0 dates |
| ds_fx | False | tr_ds_equities.ds2fxrate |  |  |  | missing required fields: from_currency, to_currency |
| comp_g_exrt_dly | True | comp.g_exrt_dly | 2026-10-28 | 2026-10-28 | 0 | n=152 on effective date; discarded 0 future-dated rows on 0 dates |
| ff_factors_daily | True | ff.factors_daily | 2026-09-30 | 2026-09-30 | 0 | n=1 on effective date; discarded 0 future-dated rows on 0 dates |
| crsp_q_treasuries | True | crsp_q_treasuries.tfz_dly_rf2 |  |  | 0 | no rows |
| snapshot_na | False | comp_snapshot.csco_afnd |  |  |  | missing required fields: gvkey, datadate, pit_start, ceq, ib, at, revt, cogs, dltt, dlc, oancf |
| snapshot_na_q | False | comp_snapshot.csco_ifndq |  |  |  | missing required fields: gvkey, datadate, pit_start, ceq |
| snapshot_global | False | comp_snapshot.None |  |  |  | no matching table found |
| comp_fund_na | True | comp.funda | 2026-08-31 | 2026-09-30 | 0 | n=78 on effective date; discarded 0 future-dated rows on 0 dates |
| comp_fund_global | True | comp.g_funda | 2026-08-31 | 2026-09-30 | 0 | n=133 on effective date; discarded 0 future-dated rows on 0 dates |
| comp_fundq_na | True | comp.fundq | 2026-09-30 | 2026-09-30 | 0 | n=8012 on effective date; discarded 0 future-dated rows on 0 dates |
| comp_fundq_global | True | comp.g_fundq | 2026-09-30 | 2026-09-30 | 0 | n=2071 on effective date; discarded 0 future-dated rows on 0 dates |
| comp_ex_codes | True | comp.r_ex_codes |  |  |  |  |
| ibes_statsum | True | ibes.statsum_epsus | 2026-08-20 | 2026-08-20 | 0 | n=35205 on effective date; discarded 0 future-dated rows on 0 dates |
| tr_ibes_statsum | True | tr_ibes.statsum_epsus | 2026-08-20 | 2026-08-20 | 0 | n=35205 on effective date; discarded 0 future-dated rows on 0 dates |
| ciq_master | True | ciq.ciqtradingitem |  |  |  |  |
| comp_security_master | True | comp.security |  |  |  |  |
| comp_company | True | comp.company |  |  |  |  |
| ds_msci_acwi | False | tr_ds_equities.ds2constmth |  |  |  | missing required fields: date |
| comp_idxcst | True | comp.idxcst_his |  |  |  |  |
| wrds_finratio | True | wrdsapps_finratio.firm_ratio |  |  |  |  |
| ravenpack | True | ravenpack_dj.rpa_djpr_equities_2026 |  |  |  |  |
| ibes_coverage_proxy | True | ibes.statsum_epsus |  |  |  |  |
| crsp_dsf_v2 | True | crsp.dsf_v2 |  |  | 0 | no rows |

### Source per input

| input | status | source used | fallback | effective latest | notes |
|---|---|---|---|---|---|
| prices_na | ok | comp_secd | False | 2026-10-28 |  |
| prices_global | ok | comp_g_secd | False | 2026-10-28 |  |
| fx | ok | comp_g_exrt_dly | False | 2026-10-28 |  |
| rf | ok | ff_factors_daily | False | 2026-09-30 |  |
| fundamentals_na | ok | comp_fund_na | True | 2026-08-31 | snapshot_na: missing required fields: gvkey, datadate, pit_start, ceq, ib, at, revt, cogs, dltt, dlc, oancf |
| fundamentals_global | ok | comp_fund_global | True | 2026-08-31 | snapshot_global: no matching table found |
| forward_earnings | ok | ibes_statsum | False | 2026-08-20 |  |
| security_master | ok | ciq_master | False |  |  |
| gics | ok | comp_company | False |  |  |
| index_membership | ok | comp_idxcst | True |  | ds_msci_acwi: missing required fields: date |
| finratio | ok | wrds_finratio | False |  |  |
| news | ok | ravenpack | False |  |  |
| crsp_validation | ok | crsp_dsf_v2 | False |  |  |

### Special checks

- crsp.dsf_v2_latest: 2025-12-31
- crsp_q_stock.dsf_v2_latest: 2026-06-30
- ciq_gvkey_links: 145303
- datastream_index_tables: ['ds2constdatadly', 'ds2constdatamth', 'ds2constdly', 'ds2constmth', 'ds2equityindex', 'ds2indexaddldata', 'ds2indexdata', 'ds2indexdatatype', 'ds2indexlist', 'wrds_ds_indexconstmerged_dly', 'wrds_ds_indexconstmerged_mth', 'wrds_ds_indexmerged']
- datastream_msci_acwi_lists: []
- snapshot_tables: 125
- snapshot_global_candidates: []
