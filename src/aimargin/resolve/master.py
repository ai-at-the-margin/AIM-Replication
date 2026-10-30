"""In-memory security master used by the resolver.

One row per trading item. Rows come from Capital IQ (``source = 'ciq'``), from the
Compustat security tables (``source = 'comp'``) or, in the demo workspace, from the
synthetic world (``source = 'synthetic'``, treated like CIQ).

Required columns (missing ones are created empty):
item_id, source, ticker, exchange_code, company_name, ciq_companyid, ciq_tradingitemid,
gvkey, iid, isin, sedol, cusip, fic, country, exchg, tpci, is_adr, is_primary, active
"""

from __future__ import annotations

from dataclasses import dataclass, field

import pandas as pd

from .normalise import name_key, ticker_key

MASTER_COLUMNS = [
    "item_id", "source", "ticker", "exchange_code", "company_name", "ciq_companyid", "ciq_tradingitemid",
    "gvkey", "iid", "isin", "sedol", "cusip", "fic", "country", "exchg", "tpci", "is_adr", "is_primary",
    "active", "gics_sector", "issuer_id",
]


def issuer_id_for(ciq_companyid: object, gvkey: object) -> str | None:
    """issuer_id = CIQ company id when known, else the gvkey (BUILD_BRIEF §6.4 step 5)."""
    if ciq_companyid is not None and str(ciq_companyid) not in ("", "None", "nan", "<NA>"):
        return "ciq:" + str(ciq_companyid).split(".")[0]
    if gvkey is not None and str(gvkey) not in ("", "None", "nan", "<NA>"):
        return "gvkey:" + str(gvkey).zfill(6)
    return None


@dataclass
class SecurityMaster:
    frame: pd.DataFrame
    by_key_exchange: dict[tuple[str, str], list[int]] = field(default_factory=dict)
    by_key: dict[str, list[int]] = field(default_factory=dict)
    names: list[str] = field(default_factory=list)
    name_rows: dict[str, list[int]] = field(default_factory=dict)
    by_gvkey: dict[str, list[int]] = field(default_factory=dict)

    @classmethod
    def from_frame(cls, frame: pd.DataFrame) -> SecurityMaster:
        data = frame.copy().reset_index(drop=True)
        for i in range(len(MASTER_COLUMNS)):
            if MASTER_COLUMNS[i] not in data.columns:
                data[MASTER_COLUMNS[i]] = None
        data["active"] = data["active"].fillna(True).astype(bool)
        data["is_primary"] = data["is_primary"].fillna(False).astype(bool)
        data["is_adr"] = data["is_adr"].fillna(False).astype(bool)
        keys = []
        nkeys = []
        issuers = []
        tickers = data["ticker"].tolist()
        names = data["company_name"].tolist()
        companies = data["ciq_companyid"].tolist()
        gvkeys = data["gvkey"].tolist()
        existing_issuer = data["issuer_id"].tolist()
        for i in range(len(data)):
            keys.append(ticker_key(tickers[i]))
            nkeys.append(name_key(names[i]))
            if existing_issuer[i] is not None and str(existing_issuer[i]) not in ("", "nan", "None"):
                issuers.append(existing_issuer[i])
            else:
                issuers.append(issuer_id_for(companies[i], gvkeys[i]))
        data["ticker_key"] = keys
        data["name_key"] = nkeys
        data["issuer_id"] = issuers
        master = cls(frame=data)
        exchanges = data["exchange_code"].tolist()
        for i in range(len(data)):
            if keys[i] is None:
                continue
            master.by_key.setdefault(keys[i], []).append(i)
            if exchanges[i] is not None:
                master.by_key_exchange.setdefault((keys[i], str(exchanges[i])), []).append(i)
            if nkeys[i]:
                if nkeys[i] not in master.name_rows:
                    master.names.append(nkeys[i])
                master.name_rows.setdefault(nkeys[i], []).append(i)
            if gvkeys[i] is not None and str(gvkeys[i]) not in ("", "nan", "None"):
                master.by_gvkey.setdefault(str(gvkeys[i]).zfill(6), []).append(i)
        return master

    def row(self, index: int) -> dict:
        return self.frame.iloc[index].to_dict()

    def __len__(self) -> int:
        return len(self.frame)
