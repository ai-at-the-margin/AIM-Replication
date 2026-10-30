"""Synthetic market world for the demo workspace, exposed through the DataSource interface.

The world is designed so the pipeline has something meaningful to find: famous
mega-caps were the winners of the period *before* most model knowledge cutoffs and
have drifted lower since, while a different set of names lead the most recent
twelve months. A model that recalls "celebrated winners" therefore delivers
negative current momentum, as in the paper; a model that searches can find the
current leaders.
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import numpy as np
import pandas as pd

from ..resolve.master import MASTER_COLUMNS
from ..utils import get_logger
from ..wrds_io import fundamentals as fund_mod
from ..wrds_io import fx as fx_mod
from ..wrds_io.freshness import effective_latest_date
from ..wrds_io.source import DataSource
from .companies import (
    COUNTRY_CURRENCY,
    COUNTRY_EXCHANGE,
    EXCHANGE_CURRENCY,
    EXCHANGE_EXCHG,
    FILLER_COUNTRIES,
    parse_curated,
)

log = get_logger(__name__)

SECTOR_VALUE = {"10": 0.7, "15": 0.4, "20": 0.1, "25": -0.1, "30": 0.0, "35": -0.2, "40": 0.8, "45": -0.6,
                "50": -0.2, "55": 0.5, "60": 0.4}
SECTOR_QUALITY = {"10": -0.2, "15": -0.1, "20": 0.1, "25": 0.0, "30": 0.3, "35": 0.3, "40": -0.3, "45": 0.5,
                  "50": 0.1, "55": -0.4, "60": -0.4}
SECTOR_BETA = {"10": 1.0, "15": 1.05, "20": 1.05, "25": 1.15, "30": 0.65, "35": 0.8, "40": 1.05, "45": 1.25,
               "50": 1.0, "55": 0.55, "60": 0.85}
FX_LEVEL_PER_GBP = {"USD": 1.27, "EUR": 1.17, "JPY": 192.0, "CHF": 1.10, "CAD": 1.75, "HKD": 9.9, "CNY": 9.2,
                    "TWD": 41.0, "INR": 107.0, "KRW": 1750.0, "AUD": 1.95, "SEK": 13.6, "BRL": 7.0, "ZAR": 23.5,
                    "SAR": 4.76, "DKK": 8.7, "SGD": 1.70, "MXN": 23.0, "NOK": 13.8, "GBP": 1.0}
FILLER_WORDS_A = ["Northern", "Pacific", "Atlas", "Summit", "Harbor", "Crescent", "Vertex", "Granite", "Silver",
                  "Evergreen", "Meridian", "Orion", "Cobalt", "Sterling", "Aurora", "Keystone", "Pioneer", "Beacon",
                  "Cascade", "Lumen", "Redwood", "Quantum", "Horizon", "Falcon", "Sapphire", "Delta", "Union"]
FILLER_WORDS_B = {"10": "Energy", "15": "Materials", "20": "Industries", "25": "Brands", "30": "Foods",
                  "35": "Therapeutics", "40": "Financial", "45": "Systems", "50": "Media", "55": "Power",
                  "60": "Properties"}


def _rng(seed: int) -> np.random.Generator:
    return np.random.default_rng(seed)


class SyntheticWorld:
    """Generates (once) and holds every synthetic table."""

    def __init__(self, asof: dt.date, n_filler: int = 1800, n_days: int = 1000, seed: int = 20261030):
        self.asof = asof
        self.n_filler = n_filler
        self.n_days = n_days
        self.seed = seed
        self.dates = pd.bdate_range(end=pd.Timestamp(asof), periods=n_days)

    # --------------------------------------------------------------- companies
    def build(self) -> None:
        rng = _rng(self.seed)
        curated = parse_curated()
        companies = []
        for i in range(len(curated)):
            c = curated[i]
            companies.append({"ticker": c["ticker"], "exchange": c["exchange"], "name": c["name"],
                              "country": c["country"], "gsector": c["gsector"], "mcap_bn": c["mcap_bn"],
                              "familiarity": c["familiarity"], "extras": c["extras"], "curated": True})
        weights = []
        countries = []
        for i in range(len(FILLER_COUNTRIES)):
            countries.append(FILLER_COUNTRIES[i][0])
            weights.append(FILLER_COUNTRIES[i][1])
        probs = np.array(weights) / np.sum(weights)
        sectors = list(SECTOR_VALUE.keys())
        sector_probs = np.array([0.05, 0.07, 0.15, 0.11, 0.07, 0.11, 0.15, 0.14, 0.06, 0.04, 0.05])
        sector_probs = sector_probs / sector_probs.sum()
        for k in range(self.n_filler):
            country = str(rng.choice(countries, p=probs))
            sector = str(rng.choice(sectors, p=sector_probs))
            mcap_bn = float(np.exp(rng.normal(np.log(9.0), 1.15)))
            mcap_bn = min(max(mcap_bn, 0.25), 400.0)
            word = FILLER_WORDS_A[k % len(FILLER_WORDS_A)]
            name = f"{word} {FILLER_WORDS_B[sector]} {k:04d} Holdings"
            exchange = COUNTRY_EXCHANGE.get(country, "XNYS")
            if country == "USA":
                exchange = "XNAS" if rng.random() < 0.45 else "XNYS"
            if country == "CHN" and rng.random() < 0.55:
                exchange = "XSHG" if rng.random() < 0.6 else "XSHE"
            if exchange in ("XHKG", "XTKS", "XTAI", "XKRX", "XSHG", "XSHE", "XSAU"):
                ticker = str(1000 + k) if exchange != "XSHG" else str(600000 + k)
                if exchange == "XSHE":
                    ticker = f"{2000 + k:06d}"
            else:
                letters = "ABCDEFGHJKLMNPRSTUVWXZ"
                ticker = letters[k % 22] + letters[(k // 22) % 22] + letters[(k // 484) % 22] + "Q"
            companies.append({"ticker": ticker, "exchange": exchange, "name": name, "country": country,
                              "gsector": sector, "mcap_bn": mcap_bn, "familiarity": 0.0, "extras": [],
                              "curated": False})
        n = len(companies)
        value_trait = rng.normal(0.0, 1.0, n)
        quality_trait = rng.normal(0.0, 1.0, n)
        beta = np.zeros(n)
        idio = np.zeros(n)
        div_yield = np.zeros(n)
        for i in range(n):
            s = companies[i]["gsector"]
            fam = companies[i]["familiarity"]
            value_trait[i] = value_trait[i] * 0.85 + SECTOR_VALUE.get(s, 0.0) - 0.5 * fam
            quality_trait[i] = quality_trait[i] * 0.85 + SECTOR_QUALITY.get(s, 0.0) + 0.9 * fam
            beta[i] = SECTOR_BETA.get(s, 1.0) + rng.normal(0.0, 0.2)
            size_bn = companies[i]["mcap_bn"]
            idio[i] = 0.013 * (size_bn / 40.0) ** -0.12 * np.exp(rng.normal(0.0, 0.25))
            div_yield[i] = max(0.0, 0.015 + 0.012 * value_trait[i] + rng.normal(0.0, 0.006))
        # Background drift regimes, then the story: celebrated names led until about ten months ago and
        # have lagged since; a different set of names has led the last seven months.
        n_days = self.n_days
        regime_len = 126
        n_regimes = int(np.ceil(n_days / regime_len))
        drift = rng.normal(0.0, 0.0007, size=(n, n_regimes))
        regime_of_day = (n_regimes - 1) - ((n_days - 1 - np.arange(n_days)) // regime_len)
        regime_of_day = np.clip(regime_of_day, 0, n_regimes - 1)
        base = drift[:, regime_of_day].T.copy()
        age = (n_days - 1) - np.arange(n_days)
        leading = (age >= 100) & (age <= 520)
        rolled = age < 100
        recent = age <= 150
        winners = rng.random(n) < 0.07
        for i in range(n):
            fam = companies[i]["familiarity"]
            if fam >= 0.45:
                base[leading, i] += 0.0011 * fam
                base[rolled, i] += -0.0042 * fam
                idio[i] = idio[i] * 0.6
            elif winners[i]:
                base[recent, i] += 0.0032
            base[:, i] += 0.00006 * quality_trait[i]
        market = rng.normal(0.00035, 0.0085, n_days)
        value_factor = rng.normal(0.0, 0.0025, n_days)
        noise = rng.standard_normal((n_days, n)) * idio[None, :]
        r_usd = beta[None, :] * market[:, None] + base + noise
        r_usd += 0.4 * value_trait[None, :] * value_factor[:, None]
        r_usd = np.clip(r_usd, -0.45, 0.6)
        self.r_usd = pd.DataFrame(r_usd, index=self.dates)
        self.traits = pd.DataFrame({
            "value_trait": value_trait, "quality_trait": quality_trait, "beta": beta, "idio": idio,
            "div_yield": div_yield, "winner": winners,
        })
        self.companies_list = companies
        self._build_fx(rng)
        self._build_listings(rng)
        self._build_fundamentals(rng)

    # ---------------------------------------------------------------------- FX
    def _build_fx(self, rng: np.random.Generator) -> None:
        currencies = list(FX_LEVEL_PER_GBP.keys())
        rows = []
        n_days = len(self.dates)
        self.fx_usd_per_unit: dict[str, np.ndarray] = {}
        per_gbp: dict[str, np.ndarray] = {}
        for i in range(len(currencies)):
            cur = currencies[i]
            if cur == "GBP":
                path = np.ones(n_days)
            else:
                steps = rng.normal(0.0, 0.004 if cur not in ("HKD", "SAR") else 0.0004, n_days)
                path = FX_LEVEL_PER_GBP[cur] * np.exp(np.cumsum(steps) - np.cumsum(steps)[-1])
            per_gbp[cur] = path
        for i in range(len(currencies)):
            self.fx_usd_per_unit[currencies[i]] = per_gbp["USD"] / per_gbp[currencies[i]]
        fx_dates = self.dates[self.dates <= pd.Timestamp(self.asof) - pd.Timedelta(days=1)]
        for i in range(len(currencies)):
            values = per_gbp[currencies[i]][: len(fx_dates)]
            frame = pd.DataFrame({"date": fx_dates, "from_currency": "GBP", "to_currency": currencies[i],
                                  "rate": values})
            rows.append(frame)
        self.fx_raw = pd.concat(rows, ignore_index=True)

    # ---------------------------------------------------------------- listings
    def _build_listings(self, rng: np.random.Generator) -> None:
        companies = self.companies_list
        n_days = len(self.dates)
        price_frames = []
        master_rows = []
        company_rows = []
        trading_item = 5_000_000
        for i in range(len(companies)):
            c = companies[i]
            gvkey = f"{100001 + i:06d}"
            cid = str(800000 + i)
            report_currency = "CNY" if c["country"] == "CHN" else COUNTRY_CURRENCY.get(c["country"], "USD")
            lines = [{"kind": "PRIMARY", "ticker": c["ticker"], "exchange": c["exchange"]}]
            extras = c["extras"]
            for j in range(len(extras)):
                lines.append(extras[j])
            non_adr = 0
            for j in range(len(lines)):
                if lines[j]["kind"] != "ADR":
                    non_adr += 1
            usd_tr = np.cumprod(1.0 + self.r_usd.iloc[:, i].to_numpy())
            usd_tr = usd_tr / usd_tr[-1]
            mcap_t_usd = c["mcap_bn"] * 1e9
            primary_iid = None
            for j in range(len(lines)):
                line = lines[j]
                exchange = line["exchange"]
                currency = EXCHANGE_CURRENCY.get(exchange, "USD")
                is_adr = line["kind"] == "ADR"
                iid = "01" if j == 0 else ("90" if is_adr else f"0{j + 1}")
                if j == 0:
                    primary_iid = iid
                fx_path = self.fx_usd_per_unit.get(currency, np.ones(n_days))
                local_tr = usd_tr / fx_path * fx_path[-1]
                q = self.traits["div_yield"].iat[i]
                trfd = np.power(1.0 + q, np.arange(n_days) / 252.0)
                price_index = local_tr / trfd * trfd[-1]
                target_price = float(np.exp(rng.normal(np.log(80.0), 0.9)))
                if line["ticker"] == "BRK.A":
                    target_price = 700000.0
                if is_adr:
                    share_fraction = 0.12
                elif non_adr == 1:
                    share_fraction = 1.0
                elif j == 0:
                    share_fraction = 0.6 if line["kind"] != "CLASS" else 0.5
                else:
                    share_fraction = (0.4 if lines[j]["kind"] != "CLASS" else 0.5) / max(1, non_adr - 1)
                premium = float(rng.uniform(0.95, 1.25)) if exchange in ("XSHG", "XSHE") and j > 0 else 1.0
                price = price_index * target_price
                mcap_local = mcap_t_usd / fx_path[-1] * share_fraction * premium
                shares = mcap_local / target_price / 1e6  # Compustat cshoc is in millions? keep units consistent
                adj = np.ones(n_days)
                if rng.random() < 0.01 and not is_adr:
                    split_day = int(rng.integers(100, n_days - 50))
                    price = price.copy()
                    price[:split_day] = price[:split_day] * 2.0
                    adj[:split_day] = 2.0
                frame = pd.DataFrame({
                    "gvkey": gvkey, "iid": iid, "date": self.dates, "price": price, "adj": adj,
                    "trfd": trfd if rng.random() > 0.03 else np.nan, "shares": shares * 1e6,
                    "currency": currency, "exchg": str(EXCHANGE_EXCHG.get(exchange, 999)),
                    "tpci": "F" if is_adr else "0", "region": "na" if exchange in ("XNYS", "XNAS", "XASE", "XTSE") else "global",
                })
                if rng.random() < 0.004:
                    spike = int(rng.integers(300, n_days - 10))
                    frame.loc[spike, "price"] = frame.loc[spike, "price"] * 9.0
                price_frames.append(frame)
                trading_item += 1
                master_rows.append({
                    "item_id": f"ciq:{trading_item}", "source": "synthetic", "ticker": line["ticker"],
                    "exchange_code": exchange, "company_name": c["name"], "ciq_companyid": cid,
                    "ciq_tradingitemid": str(trading_item), "gvkey": gvkey, "iid": iid,
                    "isin": f"XS{gvkey}{iid}0", "sedol": None, "cusip": None, "fic": c["country"],
                    "country": c["country"], "exchg": str(EXCHANGE_EXCHG.get(exchange, 999)),
                    "tpci": "F" if is_adr else "0", "is_adr": is_adr, "is_primary": j == 0, "active": True,
                    "gics_sector": c["gsector"], "issuer_id": f"ciq:{cid}",
                })
            loc = c["country"]
            company_rows.append({
                "gvkey": gvkey, "name": c["name"], "fic": loc, "loc": loc, "gsector": c["gsector"],
                "gics_sector": c["gsector"], "country": loc, "report_currency": report_currency,
                "priusa": primary_iid if loc == "USA" else None, "prican": primary_iid if loc == "CAN" else None,
                "prirow": primary_iid if loc not in ("USA", "CAN") else None, "ciq_companyid": cid,
                "familiarity": c["familiarity"], "mcap_bn": c["mcap_bn"], "curated": c["curated"],
            })
        prices = pd.concat(price_frames, ignore_index=True)
        drop = _rng(self.seed + 1).random(len(prices)) < 0.004
        prices = prices[~drop].reset_index(drop=True)
        bogus = prices.iloc[:2].copy()
        bogus["date"] = [pd.Timestamp("2027-11-12"), pd.Timestamp("2028-12-01")]
        bogus["region"] = ["na", "global"]
        self.prices = pd.concat([prices, bogus], ignore_index=True)
        self.master = pd.DataFrame(master_rows, columns=MASTER_COLUMNS)
        self.company_frame = pd.DataFrame(company_rows)

    # ------------------------------------------------------------ fundamentals
    def _build_fundamentals(self, rng: np.random.Generator) -> None:
        rows = []
        book_rows = []
        companies = self.company_frame.to_dict("records")
        tr = self.r_usd
        cum = np.cumprod(1.0 + tr.to_numpy(), axis=0)
        cum = cum / cum[-1:, :]
        for i in range(len(companies)):
            c = companies[i]
            q = float(self.traits["quality_trait"].iat[i])
            v = float(self.traits["value_trait"].iat[i])
            fy_month = 3 if c["country"] in ("JPN", "IND") else 12
            currency = c["report_currency"]
            fx_last = self.fx_usd_per_unit.get(currency, np.ones(len(self.dates)))[-1]
            earn_noise = 0.025 * (1.0 - 0.35 * np.tanh(q))
            roe_base = 0.11 + 0.045 * q
            for year in range(self.asof.year - 7, self.asof.year + 1):
                datadate = pd.Timestamp(year=year, month=fy_month, day=31 if fy_month == 12 else 31)
                available = datadate + pd.Timedelta(days=int(rng.integers(40, 100)))
                if available > pd.Timestamp(self.asof):
                    continue
                pos = int(np.searchsorted(self.dates, datadate))
                level = cum[min(max(pos, 0), len(self.dates) - 1), i] if pos < len(self.dates) else 1.0
                if pos <= 0:
                    level = cum[0, i] * float(np.exp(-0.08 * (self.dates[0] - datadate).days / 365.0))
                mcap_usd = c["mcap_bn"] * 1e9 * level
                btop = float(np.exp(0.5 * v - 0.95 + rng.normal(0.0, 0.12)))
                ceq = btop * mcap_usd / fx_last
                roe = roe_base + rng.normal(0.0, earn_noise * 3)
                ib = roe * ceq
                debt_assets = float(np.clip(0.28 - 0.09 * q + rng.normal(0.0, 0.06), 0.0, 0.75))
                if c["gsector"] == "40":
                    at = ceq * 9.0
                else:
                    at = ceq / max(0.15, 1.0 - debt_assets - 0.25)
                revt = at * float(np.clip(0.7 + rng.normal(0.0, 0.25), 0.1, 2.0))
                gm = float(np.clip(0.35 + 0.08 * q + rng.normal(0.0, 0.05), 0.03, 0.92))
                oancf = ib * (1.0 + 0.25 * np.tanh(q)) + rng.normal(0.0, 0.02) * at
                rows.append({
                    "gvkey": c["gvkey"], "datadate": datadate, "available_date": available, "currency": currency,
                    "ceq": ceq, "seq": ceq, "ib": ib, "at": at, "revt": revt, "cogs": revt * (1.0 - gm),
                    "dltt": 0.7 * debt_assets * at, "dlc": 0.3 * debt_assets * at, "oancf": oancf,
                })
                for quarter in range(4):
                    qdate = datadate + pd.DateOffset(months=3 * (quarter + 1))
                    qavail = qdate + pd.Timedelta(days=int(rng.integers(25, 60)))
                    if qavail > pd.Timestamp(self.asof):
                        continue
                    book_rows.append({"gvkey": c["gvkey"], "datadate": qdate, "available_date": qavail,
                                      "currency": currency, "ceq": ceq * (1.0 + 0.02 * (quarter + 1))})
        annual = pd.DataFrame(rows)
        self.annual_pit = fund_mod.standardise_annual(annual, 90, "synthetic_pit")
        restated = annual.copy()
        changed = rng.random(len(restated)) < 0.12
        restated.loc[changed, "ib"] = restated.loc[changed, "ib"] * (1.0 + rng.normal(0.0, 0.12, changed.sum()))
        restated.loc[changed, "ceq"] = restated.loc[changed, "ceq"] * (1.0 + rng.normal(0.0, 0.04, changed.sum()))
        restated["seq"] = restated["ceq"]
        self.annual_restated = fund_mod.standardise_annual(restated, 90, "synthetic_restated")
        book = pd.DataFrame(book_rows)
        self.book_pit = fund_mod.standardise_book(book, 90, "synthetic_pit")
        self.book_restated = self.book_pit.copy()
        frame = self.company_frame
        fam = frame["familiarity"].to_numpy()
        mcap = frame["mcap_bn"].to_numpy()
        numest = np.clip(np.round(2 + 26 * fam + 3.5 * np.log1p(mcap) + rng.normal(0, 2, len(frame))), 0, 60)
        news = rng.poisson(4 + 320 * fam ** 2 + 9 * np.log1p(mcap))
        latest = self.annual_pit.sort_values("datadate").drop_duplicates(subset=["gvkey"], keep="last")
        latest = latest.set_index("gvkey")
        primary_prices = self.prices[self.prices["iid"] == "01"]
        last_px = primary_prices[primary_prices["date"] <= pd.Timestamp(self.asof)].sort_values("date")
        last_px = last_px.drop_duplicates(subset=["gvkey"], keep="last").set_index("gvkey")
        ibes_rows = []
        gvkeys = frame["gvkey"].tolist()
        for i in range(len(gvkeys)):
            g = gvkeys[i]
            if rng.random() < 0.12 or g not in latest.index or g not in last_px.index:
                continue
            price_local = float(last_px.at[g, "price"])
            if price_local <= 0:
                continue
            ib = float(latest.at[g, "ib"])
            currency = str(latest.at[g, "currency"])
            fx_price = self.fx_usd_per_unit.get(str(last_px.at[g, "currency"]), np.ones(1))[-1]
            company_shares = mcap[i] * 1e9 / (price_local * fx_price)
            eps_report = ib * (1.0 + rng.normal(0.08, 0.1)) / company_shares
            ibes_rows.append({"gvkey": g, "fwd_eps": eps_report, "numest": float(numest[i]), "currency": currency})
        self.ibes = pd.DataFrame(ibes_rows, columns=["gvkey", "fwd_eps", "numest", "currency"])
        self.news = pd.DataFrame({"gvkey": frame["gvkey"], "news_count_30d": news.astype(float)})

    # ------------------------------------------------------------ persistence
    def save(self, folder: Path) -> None:
        folder.mkdir(parents=True, exist_ok=True)
        self.prices.to_parquet(folder / "prices.parquet", index=False)
        self.fx_raw.to_parquet(folder / "fx.parquet", index=False)
        self.master.to_parquet(folder / "master.parquet", index=False)
        self.company_frame.to_parquet(folder / "companies.parquet", index=False)
        self.annual_pit.to_parquet(folder / "annual_pit.parquet", index=False)
        self.annual_restated.to_parquet(folder / "annual_restated.parquet", index=False)
        self.book_pit.to_parquet(folder / "book_pit.parquet", index=False)
        self.ibes.to_parquet(folder / "ibes.parquet", index=False)
        self.news.to_parquet(folder / "news.parquet", index=False)
        self.r_usd.to_parquet(folder / "r_usd.parquet")
        self.traits.to_parquet(folder / "traits.parquet", index=False)


class LoadedWorld:
    """The saved world, read back from parquet (fast path for every later command)."""

    def __init__(self, folder: Path, asof: dt.date):
        self.folder = folder
        self.asof = asof
        self.prices = pd.read_parquet(folder / "prices.parquet")
        self.fx_raw = pd.read_parquet(folder / "fx.parquet")
        self.master = pd.read_parquet(folder / "master.parquet")
        self.company_frame = pd.read_parquet(folder / "companies.parquet")
        self.annual_pit = pd.read_parquet(folder / "annual_pit.parquet")
        self.annual_restated = pd.read_parquet(folder / "annual_restated.parquet")
        self.book_pit = pd.read_parquet(folder / "book_pit.parquet")
        self.ibes = pd.read_parquet(folder / "ibes.parquet")
        self.news = pd.read_parquet(folder / "news.parquet")
        self.r_usd = pd.read_parquet(folder / "r_usd.parquet")
        self.traits = pd.read_parquet(folder / "traits.parquet")
        self.r_usd.columns = range(self.r_usd.shape[1])

    def momentum_at(self, date: pd.Timestamp) -> pd.Series:
        """12-1 month USD total return per company index, as known on ``date``."""
        rows = self.r_usd.loc[:date]
        if len(rows) < 253:
            return pd.Series(0.0, index=self.r_usd.columns)
        block = rows.iloc[len(rows) - 252: len(rows) - 21]
        return (1.0 + block).prod(axis=0) - 1.0

    def reputation_at(self, date: pd.Timestamp, days: int = 504) -> pd.Series:
        """Two-year total return ending on ``date``: the 'story of a winner' a model may recall."""
        rows = self.r_usd.loc[:date]
        block = rows.iloc[max(0, len(rows) - days):]
        return (1.0 + block).prod(axis=0) - 1.0

    def mcap_at(self, date: pd.Timestamp) -> pd.Series:
        cum = (1.0 + self.r_usd).cumprod()
        cum = cum / cum.iloc[-1]
        row = cum.loc[:date].iloc[-1] if len(cum.loc[:date]) > 0 else cum.iloc[0]
        return self.company_frame["mcap_bn"].reset_index(drop=True) * row.reset_index(drop=True)


def world_folder(root: Path) -> Path:
    return root / "raw" / "synthetic_world"


def ensure_world(root: Path, asof: dt.date, n_filler: int = 2600) -> LoadedWorld:
    folder = world_folder(root)
    if not (folder / "prices.parquet").exists():
        log.info("generating synthetic world (%d filler issuers) ...", n_filler)
        world = SyntheticWorld(asof, n_filler=n_filler)
        world.build()
        world.save(folder)
    return LoadedWorld(folder, asof)


class SyntheticSource(DataSource):
    """DataSource over the synthetic world (demo workspace and tests)."""

    name = "synthetic"
    is_synthetic = True

    def __init__(self, world: LoadedWorld):
        super().__init__()
        self.world = world
        self.today = world.asof + dt.timedelta(days=1)

    def latest_dates(self) -> dict[str, dt.date | None]:
        out: dict[str, dt.date | None] = {}
        for name, region in (("prices_na", "na"), ("prices_global", "global")):
            frame = self.world.prices[self.world.prices["region"] == region]
            counts = frame.groupby("date").size().rename("n").reset_index()
            out[name] = effective_latest_date(counts, self.today).effective_latest_date
        fx = self.world.fx_raw
        out["fx"] = pd.Timestamp(fx["date"].max()).date() if len(fx) else None
        return out

    def freshness_counts(self, region: str) -> pd.DataFrame:
        frame = self.world.prices[self.world.prices["region"] == region]
        recent = frame[frame["date"] >= pd.Timestamp(self.today - dt.timedelta(days=75))]
        return recent.groupby("date").size().rename("n").reset_index()

    def security_master(self, asof: dt.date) -> pd.DataFrame:
        self.note("security_master", "synthetic_ciq", False, len(self.world.master))
        return self.world.master.copy()

    def companies(self) -> pd.DataFrame:
        return self.world.company_frame.copy()

    def price_snapshot(self, date: dt.date) -> pd.DataFrame:
        prices = self.world.prices
        return prices[prices["date"] == pd.Timestamp(date)].copy()

    def price_history(self, gvkeys: list[str], start: dt.date, end: dt.date) -> pd.DataFrame:
        prices = self.world.prices
        mask = prices["gvkey"].isin(set(gvkeys)) & (prices["date"] >= pd.Timestamp(start)) & (
            prices["date"] <= pd.Timestamp(end))
        frame = prices[mask].copy()
        self.note("prices", "synthetic_secd+g_secd", False, len(frame))
        return frame

    def fx_rates(self, start: dt.date, end: dt.date) -> pd.DataFrame:
        raw = self.world.fx_raw
        mask = (raw["date"] >= pd.Timestamp(start)) & (raw["date"] <= pd.Timestamp(end))
        rates = fx_mod.usd_per_unit(raw[mask])
        self.note("fx", "synthetic_g_exrt_dly", False, len(rates),
                  "last FX date is one day before the as-of date; forward-filled")
        return rates

    def rf_rates(self, start: dt.date, end: dt.date) -> pd.DataFrame:
        dates = pd.bdate_range(start=pd.Timestamp(start), end=pd.Timestamp("2026-09-30"))
        frame = pd.DataFrame({"date": dates, "rf": 0.00016})
        self.note("rf", "synthetic_ff_factors_daily", False, len(frame), "ends 2026-09-30; forward-filled to as-of")
        return frame

    def fundamentals_annual(self, gvkeys: list[str], asof: dt.date, years: int, pit: bool = True) -> pd.DataFrame:
        frame = self.world.annual_pit if pit else self.world.annual_restated
        frame = frame[frame["gvkey"].isin(set(gvkeys))]
        frame = frame[frame["datadate"] >= pd.Timestamp(dt.date(asof.year - years, 1, 1))]
        self.note("fundamentals_na" if pit else "fundamentals_restated",
                  "synthetic_snapshot" if pit else "synthetic_funda", not pit, len(frame))
        return fund_mod.as_known_at(frame, asof)

    def book_equity(self, gvkeys: list[str], asof: dt.date, pit: bool = True) -> pd.DataFrame:
        frame = self.world.book_pit if pit else self.world.book_restated
        return fund_mod.as_known_at(frame[frame["gvkey"].isin(set(gvkeys))], asof)

    def forward_eps(self, gvkeys: list[str], asof: dt.date) -> pd.DataFrame:
        frame = self.world.ibes[self.world.ibes["gvkey"].isin(set(gvkeys))]
        self.note("forward_earnings", "synthetic_ibes", False, len(frame))
        return frame

    def news_counts(self, gvkeys: list[str], asof: dt.date) -> pd.DataFrame:
        frame = self.world.news[self.world.news["gvkey"].isin(set(gvkeys))]
        self.note("news", "synthetic_ravenpack", False, len(frame))
        return frame

    def finratio(self, gvkeys: list[str], asof: dt.date) -> pd.DataFrame:
        annual = self.world.annual_pit
        latest = annual[annual["gvkey"].isin(set(gvkeys))].sort_values("datadate").drop_duplicates(
            subset=["gvkey"], keep="last")
        noise = _rng(7).normal(0.0, 0.01, len(latest))
        return pd.DataFrame({
            "gvkey": latest["gvkey"], "roa": latest["ib"] / latest["at"] + noise,
            "roe": latest["ib"] / latest["ceq"] + noise * 2,
            "debt_assets": (latest["dltt"] + latest["dlc"]) / latest["at"] + noise,
        })
