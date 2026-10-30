# WRDS access report

Generated: 2026-10-29T21:48:12

Libraries visible to this account: 385


## Core tables (from the build brief)

| library | table | purpose | readable | date_column | latest_date | rows_on_latest_date | query_seconds | note |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| comp | secd | NA daily prices/returns (primary price source) | True | datadate | 2027-11-12 | 1.0 | 1.3 |  |
| comp | g_secd | Global daily prices/returns (primary price source) | True | datadate | 2028-12-01 | 1.0 | 0.5 |  |
| comp | g_exrt_dly | Daily FX rates (GBP-based) | True | datadate | 2026-10-28 | 152.0 | 0.6 |  |
| comp | security | NA security master (tickers, exchanges) | True |  |  |  | 0.2 | readable; no recognised date column (master/static table) |
| comp | g_security | Global security master (tickers, ISIN) | True |  |  |  | 0.1 | readable; no recognised date column (master/static table) |
| comp | company | NA company master, GICS | True |  |  |  | 0.1 | readable; no recognised date column (master/static table) |
| comp | g_company | Global company master, GICS | True |  |  |  | 0.3 | readable; no recognised date column (master/static table) |
| comp | funda | NA annual fundamentals | True | datadate | 2026-09-30 |  | 1.5 |  |
| comp | fundq | NA quarterly fundamentals (rdq) | True | datadate | 2026-09-30 |  | 1.0 |  |
| comp | g_funda | Global annual fundamentals | True | datadate | 2026-09-30 |  | 2.8 |  |
| comp | g_fundq | Global quarterly fundamentals | True | datadate | 2026-09-30 |  | 0.4 |  |
| comp | idxcst_his | S&P index constituents history | True |  |  |  | 0.1 | readable; no recognised date column (master/static table) |
| ff | factors_daily | Fama-French daily factors incl. risk-free rate | True | date | 2026-09-30 |  | 0.3 |  |
| crsp | dsf_v2 | CRSP daily stock file, CIZ format (US cross-check) | True | dlycaldt | 2025-12-31 | 10686.0 | 0.5 |  |
| crsp | dsf | CRSP daily stock file, legacy SIZ format | True | date |  |  | 0.3 | no rows after 2025-06-01 (data may be stale) |
| crsp | msf_v2 | CRSP monthly stock file, CIZ format | True | mthcaldt | 2025-12-31 |  | 0.3 |  |
| crsp | ccmxpf_lnkhist | CRSP-Compustat link table | True |  |  |  | 0.5 | readable; no recognised date column (master/static table) |


## Optional datasets that could upgrade the design

| library | purpose | visible | n_tables | sample_tables | readable_sample | note |
| --- | --- | --- | --- | --- | --- | --- |
| comp_snapshot | Compustat Snapshot: true point-in-time fundamentals | True | 125.0 | chars, cs_items, csco_aaudit, csco_afnd, csco_afntind, csco_ainvval, csco_akey, csco_atxt, csco_iaudit, csco_ifndq, csco_ifndytd, csco_ifntq | True |  |
| ibes | I/B/E/S analyst forecasts: forward earnings yield, coverage | True | 194.0 | act_epsint, act_epsus, act_xepsint, act_xepsus, actg, actgu, actpsum_epsint, actpsum_epsus, actpsum_xepsint, actpsum_xepsus, actpsumu_epsint, actpsumu_epsus | True |  |
| tr_ds_equities | Datastream equities: global total-return index (RI) | True | 43.0 | ds2adj, ds2capevent, ds2company, ds2constdatadly, ds2constdatamth, ds2constdly, ds2constmth, ds2ctryqtinfo, ds2cusipchg, ds2datatype, ds2div, ds2dps | True |  |
| tr_worldscope | Worldscope: alternative global fundamentals | False |  |  |  | not in your library list |
| ciq | Capital IQ: company/security identifiers for cross-listings | True | 259.0 | chars, ciqaddress, ciqaddresstype, ciqbusinessdescription, ciqbusinessdescriptionlong, ciqcapstdtasrptdclasstype, ciqcapstdtclasstype, ciqcapstdtcompntasrptddata, ciqcapstdtcomponent, ciqcapstdtconvertibletype, ciqcapstdtcumulativetype, ciqcapstdtdescription | True |  |
| msci | MSCI data (indices / constituents / GICS) if licensed | False |  |  |  | not in your library list |
| barra | MSCI Barra risk model exposures (exact replication) | False |  |  |  | not in your library list |
| axioma | Axioma risk model exposures (alternative to Barra) | False |  |  |  | not in your library list |
| factset | FactSet (fundamentals / ownership) if licensed | False |  |  |  | not in your library list |
| ravenpack_dj | RavenPack news analytics (future news-check extension) | True | 55.0 | djpr_chars, rpa_djpr_equities_2000, rpa_djpr_equities_2001, rpa_djpr_equities_2002, rpa_djpr_equities_2003, rpa_djpr_equities_2004, rpa_djpr_equities_2005, rpa_djpr_equities_2006, rpa_djpr_equities_2007, rpa_djpr_equities_2008, rpa_djpr_equities_2009, rpa_djpr_equities_2010 | True |  |
| wrdsapps_finratio | WRDS Financial Ratios Suite (US) | True | 2.0 | firm_ratio, id | True |  |
| wrdsapps_beta | WRDS Beta Suite | False |  |  |  | not in your library list |
| ff_all | Fama-French full library | True | 12.0 | factors_china, factors_daily, factors_monthly, fivefactors_daily, fivefactors_monthly, industry12, industry48, liq_ps, liq_sadka, portfolios, portfolios25, portfolios_d | True |  |
| crsp_a_stock | CRSP stock, ANNUAL update | True | 95.0 | dse, dseall, dsedelist, dsedist, dseexchdates, dsenames, dsenasdin, dseshares, dsf, dsf_v2, dsfhdr, dsi | True |  |
| crsp_q_stock | CRSP stock, QUARTERLY update | True | 95.0 | dse, dseall, dsedelist, dsedist, dseexchdates, dsenames, dsenasdin, dseshares, dsf, dsf_v2, dsfhdr, dsi | True |  |
| crsp_m_stock | CRSP stock, MONTHLY update | False |  |  |  | not in your library list |


## All flagged libraries (keyword match)

audit, audit_acct_os, audit_audit_comp, audit_common, audit_corp_legal, auditsmp, auditsmp_all, boardex, boardex_eur, boardex_na, boardex_row, boardex_trial, boardex_uk, ciq, ciq_common, ciq_keydev, ciq_ratings, ciq_transcripts, ciqsamp, ciqsamp_capstrct, ciqsamp_common, ciqsamp_keydev, ciqsamp_pplintel, ciqsamp_ratings, ciqsamp_transactions, ciqsamp_transcripts, comp, comp_bank_daily, comp_execucomp, comp_filings, comp_global_daily, comp_na_daily_all, comp_segments_hist_daily, comp_snapshot, compsamp, compsamp_all, compsamp_computext, compsamp_snapshot, compseg, compsnap, contrib_liquidity_taq, crsp, crsp_a_ccm, crsp_a_indexes, crsp_a_stock, crsp_a_treasuries, crsp_q_ccm, crsp_q_indexes, crsp_q_indexhist, crsp_q_mutualfunds, crsp_q_stock, crsp_q_treasuries, crspq, crspsamp, crspsamp_all, crspsamp_mf, execcomp, ff, ff_all, ibes, ibessamp_kpi, markit, markit_cds, markit_cdxcomps, markit_cdxconst, markit_red, mfl, mflinks_all, morningstarsamp_cisdm, msci_climate_samp, msci_common_samp, msci_esg_samp, mscicoms, mscicsmp, msciesmp, optionm, optionm_all, optionmsamp_europe, optionmsamp_us, ravenpack_common, ravenpack_dj, ravenpack_trial, revelio_layoffs, rpna, rpnasamp, taqm_2003, taqm_2004, taqm_2005, taqm_2006, taqm_2007, taqm_2008, taqm_2009, taqm_2010, taqm_2011, taqm_2012, taqm_2013, taqm_2014, taqm_2015, taqm_2016, taqm_2017, taqm_2018, taqm_2019, taqm_2020, taqm_2021, taqm_2022, taqm_2023, taqm_2024, taqm_2025, taqm_2026, taqmsamp, taqmsamp_all, taqmsec, taqsamp, taqsamp_all, tfn, tr_13f, tr_common, tr_dealscan, tr_ds_comds, tr_ds_econ, tr_ds_equities, tr_ds_fut, tr_ibes, tr_ibes_guidance, tr_insiders, tr_mutualfunds, tr_sdc_samples, tr_tass, trsamp_worldscope, wrdsapps, wrdsapps_backtest_basic, wrdsapps_backtest_plus, wrdsapps_bondret, wrdsapps_eushort, wrdsapps_evtstudy_int, wrdsapps_evtstudy_int_ginsight, wrdsapps_evtstudy_lr, wrdsapps_evtstudy_lr_ciq, wrdsapps_evtstudy_us, wrdsapps_finratio, wrdsapps_finratio_ccm, wrdsapps_finratio_ibes, wrdsapps_finratio_ibes_ccm, wrdsapps_link_comp_eushort, wrdsapps_link_crsp_bond, wrdsapps_link_crsp_comp_bdx, wrdsapps_link_crsp_factset, wrdsapps_link_crsp_ibes, wrdsapps_link_crsp_optionm, wrdsapps_link_crsp_taq, wrdsapps_link_crsp_taqm, wrdsapps_link_supplychain, wrdsapps_link_trinsider_bdx, wrdsapps_patents, wrdsapps_plink_boardex_trinsider, wrdsapps_plink_exec_boardex, wrdsapps_plink_exec_trinsider, wrdsapps_subsidiary, wrdsapps_windices, wrdsappssamp_all


Full library list saved to wrds_libraries.csv
