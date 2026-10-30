"""Shared fixtures."""

from __future__ import annotations

import pandas as pd
import pytest

from aimargin.settings import load_config


@pytest.fixture(scope="session")
def config():
    return load_config()


@pytest.fixture
def master_frame() -> pd.DataFrame:
    """A small security master with the four collapse cases from BUILD_BRIEF §6.4."""
    rows = [
        # item, source, ticker, exchange, name, companyid, gvkey, iid, country, adr, primary
        ("ciq:1", "ciq", "GOOGL", "XNAS", "Alphabet Inc.", "100", "160329", "01", "USA", False, True),
        ("ciq:2", "ciq", "GOOG", "XNAS", "Alphabet Inc.", "100", "160329", "02", "USA", False, False),
        ("ciq:3", "ciq", "2330", "XTAI", "Taiwan Semiconductor Manufacturing Company Limited", "200", "200001", "01W", "TWN", False, True),
        ("ciq:4", "ciq", "TSM", "XNYS", "Taiwan Semiconductor Manufacturing Company Limited", "200", "200001", "90", "TWN", True, False),
        ("ciq:5", "ciq", "NOVO B", "XCSE", "Novo Nordisk A/S", "300", "300001", "01W", "DNK", False, True),
        ("ciq:6", "ciq", "NVO", "XNYS", "Novo Nordisk A/S", "300", "300001", "90", "DNK", True, False),
        ("ciq:7", "ciq", "ASML", "XAMS", "ASML Holding N.V.", "400", "400001", "01W", "NLD", False, True),
        ("ciq:8", "ciq", "ASML", "XNAS", "ASML Holding N.V.", "400", "400001", "02", "NLD", False, False),
        ("ciq:9", "ciq", "0700", "XHKG", "Tencent Holdings Limited", "500", "500001", "01W", "CHN", False, True),
        ("ciq:10", "ciq", "600519", "XSHG", "Kweichow Moutai Co., Ltd.", "600", "600001", "01W", "CHN", False, True),
        ("ciq:11", "ciq", "BRK.B", "XNYS", "Berkshire Hathaway Inc.", "700", "002176", "02", "USA", False, True),
        ("ciq:12", "ciq", "SAN", "XPAR", "Sanofi", "800", "800001", "01W", "FRA", False, True),
        ("ciq:13", "ciq", "SAN", "XMAD", "Banco Santander, S.A.", "900", "900001", "01W", "ESP", False, True),
        ("comp:014000:01", "comp", "XYZW", "XNYS", "Compustat Only Corp", None, "014000", "01", "USA", False, True),
    ]
    records = []
    for i in range(len(rows)):
        r = rows[i]
        records.append({"item_id": r[0], "source": r[1], "ticker": r[2], "exchange_code": r[3], "company_name": r[4],
                        "ciq_companyid": r[5], "ciq_tradingitemid": r[0].split(":")[-1] if r[1] == "ciq" else None,
                        "gvkey": r[6], "iid": r[7], "country": r[8], "is_adr": r[9], "is_primary": r[10],
                        "active": True, "gics_sector": "45"})
    return pd.DataFrame(records)
