"""Security master: Capital IQ trading items linked to Compustat, with a Compustat fallback.

CIQ links every trading item (GOOGL, GOOG, TSM, 2330.TW ...) to one company id, so
share classes, cross-listings and ADRs collapse systematically (BUILD_BRIEF §6.4).
"""

from __future__ import annotations

import pandas as pd

from ..resolve.master import MASTER_COLUMNS, issuer_id_for
from ..resolve.normalise import exchange_table, ticker_key
from .schema import TableMap


def ciq_items_sql(m: TableMap) -> str:
    sec = m.extra.get("security_table", "ciqsecurity")
    comp = m.extra.get("company_table", "ciqcompany")
    exch = m.extra.get("exchange_table", "ciqexchange")
    link = m.extra.get("gvkey_link", {"library": "ciq_common", "table": "wrds_gvkey"})
    return (
        f"SELECT ti.{m.c('tradingitemid')} AS tradingitemid, ti.{m.c('securityid')} AS securityid, "
        f"ti.{m.c('ticker')} AS ticker, ti.{m.c('primaryflag')} AS ti_primary, ti.{m.c('status')} AS status, "
        f"s.companyid AS companyid, s.primaryflag AS sec_primary, s.securityname AS securityname, "
        f"c.companyname AS company_name, e.exchangesymbol AS exchangesymbol, e.exchangename AS exchangename "
        f"FROM {m.library}.{m.table} ti "
        f"JOIN {m.library}.{sec} s ON ti.{m.c('securityid')} = s.securityid "
        f"JOIN {m.library}.{comp} c ON s.companyid = c.companyid "
        f"LEFT JOIN {m.library}.{exch} e ON ti.{m.c('exchangeid')} = e.exchangeid "
        f"WHERE ti.{m.c('ticker')} IS NOT NULL "
        f"AND s.companyid IN (SELECT companyid FROM {link['library']}.{link['table']})"
    )


def gvkey_link_sql(m: TableMap) -> str:
    link = m.extra.get("gvkey_link", {"library": "ciq_common", "table": "wrds_gvkey"})
    return f"SELECT * FROM {link['library']}.{link['table']}"


def comp_master_sql(sec: TableMap, company: TableMap, global_tables: bool) -> str:
    sec_table = sec.extra.get("global_table", "g_security") if global_tables else sec.table
    comp_table = company.extra.get("global_table", "g_company") if global_tables else company.table
    sec_fields = ["gvkey", "iid", "ticker", "exchg", "isin", "sedol", "cusip", "tpci", "dlrsni"]
    parts = []
    for i in range(len(sec_fields)):
        if sec.has(sec_fields[i]):
            parts.append(f"s.{sec.c(sec_fields[i])} AS {sec_fields[i]}")
    comp_fields = ["name", "fic", "loc", "gsector", "priusa", "prican", "prirow"]
    for i in range(len(comp_fields)):
        if company.has(comp_fields[i]):
            parts.append(f"c.{company.c(comp_fields[i])} AS {comp_fields[i]}")
    return (f"SELECT {', '.join(parts)} FROM {sec.library}.{sec_table} s "
            f"JOIN {company.library}.{comp_table} c ON s.{sec.c('gvkey')} = c.{company.c('gvkey')}")


def companies_sql(company: TableMap, global_tables: bool) -> str:
    table = company.extra.get("global_table", "g_company") if global_tables else company.table
    fields = ["gvkey", "name", "fic", "loc", "gsector", "ggroup", "gind", "gsubind", "priusa", "prican", "prirow"]
    return f"SELECT {company.select(fields)} FROM {company.library}.{table}"


def _primary_iid(row: dict) -> str | None:
    loc = str(row.get("loc") or "")
    if loc == "USA" and row.get("priusa"):
        return str(row["priusa"])
    if loc == "CAN" and row.get("prican"):
        return str(row["prican"])
    for key in ("prirow", "priusa", "prican"):
        if row.get(key):
            return str(row[key])
    return None


def build_comp_master(comp_rows: pd.DataFrame, exchg_map: dict[str, str]) -> pd.DataFrame:
    """Compustat security rows in master format (source = 'comp')."""
    rows = comp_rows.to_dict("records")
    table = exchange_table()
    out = []
    for i in range(len(rows)):
        r = rows[i]
        exchg = None
        if r.get("exchg") is not None and str(r.get("exchg")) not in ("nan", "None"):
            exchg = str(int(float(r["exchg"])))
        code = exchg_map.get(exchg) if exchg else None
        gvkey = str(r.get("gvkey")).zfill(6)
        primary = _primary_iid(r)
        out.append({
            "item_id": f"comp:{gvkey}:{r.get('iid')}", "source": "comp", "ticker": r.get("ticker"),
            "exchange_code": code, "company_name": r.get("name"), "ciq_companyid": None,
            "ciq_tradingitemid": None, "gvkey": gvkey, "iid": str(r.get("iid")), "isin": r.get("isin"),
            "sedol": r.get("sedol"), "cusip": r.get("cusip"), "fic": r.get("fic"), "country": r.get("loc"),
            "exchg": exchg, "tpci": str(r.get("tpci")), "is_adr": str(r.get("tpci")) == "F",
            "is_primary": primary is not None and str(r.get("iid")) == primary,
            "active": r.get("dlrsni") in (None, "", "nan") or str(r.get("dlrsni")) == "None",
            "gics_sector": r.get("gsector"), "issuer_id": issuer_id_for(None, gvkey),
        })
        if code is not None and not table.info.get(code):
            out[-1]["exchange_code"] = None
    frame = pd.DataFrame(out, columns=MASTER_COLUMNS)
    return frame


def build_ciq_master(items: pd.DataFrame, links: pd.DataFrame, comp_master: pd.DataFrame,
                     asof: str) -> pd.DataFrame:
    """CIQ trading items -> master rows, attaching gvkey (company link) and iid (ticker/exchange)."""
    table = exchange_table()
    link_rows = links.copy().rename(columns=lambda name: str(name).lower())
    company_to_gvkey: dict[str, str] = {}
    records = link_rows.to_dict("records")
    for i in range(len(records)):
        r = records[i]
        start = str(r.get("startdate") or "")[:10]
        end = str(r.get("enddate") or "")[:10]
        if start and start > asof:
            continue
        if end and end not in ("None", "NaT", "nan") and end < asof:
            continue
        company_to_gvkey[str(r.get("companyid")).split(".")[0]] = str(r.get("gvkey")).zfill(6)
    comp_lookup: dict[tuple[str, str, str], dict] = {}
    comp_records = comp_master.to_dict("records")
    for i in range(len(comp_records)):
        r = comp_records[i]
        key = (str(r.get("gvkey")), str(ticker_key(r.get("ticker"))), str(r.get("exchange_code")))
        comp_lookup[key] = r
    by_gvkey: dict[str, dict] = {}
    for i in range(len(comp_records)):
        by_gvkey.setdefault(str(comp_records[i].get("gvkey")), comp_records[i])
    out = []
    item_records = items.to_dict("records")
    for i in range(len(item_records)):
        r = item_records[i]
        company = str(r.get("companyid")).split(".")[0]
        gvkey = company_to_gvkey.get(company)
        code = table.by_ciq_symbol.get(str(r.get("exchangesymbol") or "").upper())
        match = comp_lookup.get((str(gvkey), str(ticker_key(r.get("ticker"))), str(code))) if gvkey else None
        base = match or (by_gvkey.get(str(gvkey)) if gvkey else None) or {}
        out.append({
            "item_id": f"ciq:{str(r.get('tradingitemid')).split('.')[0]}", "source": "ciq",
            "ticker": r.get("ticker"), "exchange_code": code, "company_name": r.get("company_name"),
            "ciq_companyid": company, "ciq_tradingitemid": str(r.get("tradingitemid")).split(".")[0],
            "gvkey": gvkey, "iid": match.get("iid") if match else None, "isin": base.get("isin") if match else None,
            "sedol": base.get("sedol") if match else None, "cusip": base.get("cusip") if match else None,
            "fic": base.get("fic"), "country": base.get("country"), "exchg": match.get("exchg") if match else None,
            "tpci": match.get("tpci") if match else None,
            "is_adr": bool(match.get("is_adr")) if match else False,
            "is_primary": str(r.get("ti_primary")) in ("1", "1.0", "True", "true"),
            "active": True, "gics_sector": base.get("gics_sector"),
            "issuer_id": issuer_id_for(company, gvkey),
        })
    return pd.DataFrame(out, columns=MASTER_COLUMNS)
