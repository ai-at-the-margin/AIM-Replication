"""Ticker normalisation, resolution and issuer collapse (BUILD_BRIEF §6.4 acceptance)."""

from __future__ import annotations

import pandas as pd

from aimargin.resolve.master import SecurityMaster
from aimargin.resolve.normalise import exchange_code, parse_ticker, ticker_key
from aimargin.resolve.resolver import Resolver


def test_ticker_forms():
    assert parse_ticker("0700.HK").exchange == "XHKG" and parse_ticker("0700.HK").key == "700"
    assert parse_ticker("600519.SS").exchange == "XSHG"
    assert parse_ticker("600519.SH").exchange == "XSHG"
    assert parse_ticker("000858.SZ").exchange == "XSHE" and parse_ticker("000858.SZ").key == "858"
    assert parse_ticker("2330.TW").exchange == "XTAI"
    assert parse_ticker("ASML.AS").exchange == "XAMS"
    novo = parse_ticker("NOVO-B.CO")
    assert novo.exchange == "XCSE" and novo.key == "NOVO.B"
    assert parse_ticker("BRK.B").key == "BRK.B" and parse_ticker("BRK.B").exchange is None
    assert ticker_key("BRK-B") == "BRK.B"
    assert parse_ticker("$MSFT").key == "MSFT"
    assert parse_ticker("NASDAQ:MSFT").exchange == "XNAS"
    assert parse_ticker("700 HK").exchange == "XHKG"
    assert exchange_code("Nasdaq Global Select Market") == "XNAS"
    assert exchange_code("Euronext Amsterdam") == "XAMS"


def _resolver(master_frame, tmp_path):
    return Resolver(SecurityMaster.from_frame(master_frame), tmp_path)


def test_four_collapse_cases(master_frame, tmp_path):
    r = _resolver(master_frame, tmp_path)
    pairs = [
        (("GOOGL", "NASDAQ", "Alphabet"), ("GOOG", "NASDAQ", "Alphabet Class C")),
        (("TSM", "NYSE", "TSMC"), ("2330.TW", "", "Taiwan Semiconductor")),
        (("NVO", "NYSE", "Novo Nordisk"), ("NOVO-B.CO", "", "Novo Nordisk")),
        (("ASML", "NASDAQ", "ASML Holding"), ("ASML.AS", "", "ASML Holding")),
    ]
    for i in range(len(pairs)):
        a = r.resolve(*pairs[i][0])
        b = r.resolve(*pairs[i][1])
        assert a.status == "resolved" and b.status == "resolved", pairs[i]
        assert a.fields["issuer_id"] == b.fields["issuer_id"], pairs[i]


def test_exchange_disambiguates_same_ticker(master_frame, tmp_path):
    r = _resolver(master_frame, tmp_path)
    sanofi = r.resolve("SAN", "Euronext Paris", "Sanofi")
    santander = r.resolve("SAN.MC", "", "Banco Santander")
    assert sanofi.fields["resolved_name"] == "Sanofi"
    assert santander.fields["resolved_name"].startswith("Banco Santander")


def test_flags_and_fallbacks(master_frame, tmp_path):
    r = _resolver(master_frame, tmp_path)
    moutai = r.resolve("600519.SS", "", "Kweichow Moutai")
    assert moutai.fields["is_china_a_share"] is True
    tencent = r.resolve("0700", "HKEX", "Tencent")
    assert tencent.fields["is_hk_listed"] is True
    comp = r.resolve("XYZW", "NYSE", "Compustat Only Corp")
    assert comp.method.startswith("comp_")
    by_name = r.resolve("TCEHY", "OTC", "Tencent Holdings")
    assert by_name.status != "unresolved" and by_name.fields["issuer_id"] == tencent.fields["issuer_id"]
    unknown = r.resolve("ZZZZ", "NASDAQ", "Imaginary Robotics Corp")
    assert unknown.status == "unresolved"
    assert r.write_review(tmp_path / "review.csv") >= 1


def test_manual_override(master_frame, tmp_path):
    pd.DataFrame([{"raw_ticker": "MYSTERY", "raw_exchange": "", "raw_name": "", "item_id": "ciq:12",
                   "gvkey": "", "iid": "", "note": "team decision"}]).to_csv(tmp_path / "ticker_overrides.csv",
                                                                           index=False)
    r = _resolver(master_frame, tmp_path)
    result = r.resolve("MYSTERY", "", "")
    assert result.method == "manual_override" and result.fields["resolved_name"] == "Sanofi"
