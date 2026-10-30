"""Curated large-cap names for the demo world.

Columns: ticker | exchange | name | HQ country | GICS sector | approx cap ($bn) |
familiarity (0-1, how often a language model reaches for the name) | extra listings.

Extra listings use ``KIND:TICKER:EXCHANGE`` with KIND in ADR (depositary receipt),
CLASS (another share class), LINE (another local line, e.g. an A- or H-share).
Caps and familiarity are rough, illustrative inputs to a simulation only.
"""

CURATED = """
AAPL|XNAS|Apple Inc.|USA|45|3500|1.00|
MSFT|XNAS|Microsoft Corporation|USA|45|3800|1.00|
NVDA|XNAS|NVIDIA Corporation|USA|45|4500|1.00|
AMZN|XNAS|Amazon.com, Inc.|USA|25|2400|1.00|
GOOGL|XNAS|Alphabet Inc.|USA|50|2600|0.97|CLASS:GOOG:XNAS
META|XNAS|Meta Platforms, Inc.|USA|50|1800|0.90|
TSLA|XNAS|Tesla, Inc.|USA|25|1100|0.80|
BRK.B|XNYS|Berkshire Hathaway Inc.|USA|40|1000|0.85|CLASS:BRK.A:XNYS
JPM|XNYS|JPMorgan Chase & Co.|USA|40|750|0.90|
V|XNYS|Visa Inc.|USA|40|650|0.85|
MA|XNYS|Mastercard Incorporated|USA|40|520|0.70|
UNH|XNYS|UnitedHealth Group Incorporated|USA|35|400|0.55|
JNJ|XNYS|Johnson & Johnson|USA|35|420|0.70|
LLY|XNYS|Eli Lilly and Company|USA|35|850|0.80|
PG|XNYS|The Procter & Gamble Company|USA|30|380|0.60|
HD|XNYS|The Home Depot, Inc.|USA|25|400|0.55|
XOM|XNYS|Exxon Mobil Corporation|USA|10|480|0.60|
CVX|XNYS|Chevron Corporation|USA|10|290|0.40|
KO|XNYS|The Coca-Cola Company|USA|30|300|0.60|
PEP|XNAS|PepsiCo, Inc.|USA|30|210|0.40|
COST|XNAS|Costco Wholesale Corporation|USA|30|430|0.65|
WMT|XNYS|Walmart Inc.|USA|30|800|0.55|
AVGO|XNAS|Broadcom Inc.|USA|45|1500|0.80|
ORCL|XNYS|Oracle Corporation|USA|45|700|0.50|
ADBE|XNAS|Adobe Inc.|USA|45|180|0.45|
CRM|XNYS|Salesforce, Inc.|USA|45|260|0.45|
AMD|XNAS|Advanced Micro Devices, Inc.|USA|45|380|0.65|
INTC|XNAS|Intel Corporation|USA|45|150|0.30|
NFLX|XNAS|Netflix, Inc.|USA|50|500|0.55|
DIS|XNYS|The Walt Disney Company|USA|50|200|0.40|
BAC|XNYS|Bank of America Corporation|USA|40|340|0.45|
WFC|XNYS|Wells Fargo & Company|USA|40|260|0.30|
GS|XNYS|The Goldman Sachs Group, Inc.|USA|40|220|0.35|
MS|XNYS|Morgan Stanley|USA|40|230|0.30|
ABBV|XNYS|AbbVie Inc.|USA|35|380|0.45|
MRK|XNYS|Merck & Co., Inc.|USA|35|260|0.40|
PFE|XNYS|Pfizer Inc.|USA|35|150|0.35|
TMO|XNYS|Thermo Fisher Scientific Inc.|USA|35|200|0.35|
ABT|XNYS|Abbott Laboratories|USA|35|220|0.30|
ISRG|XNAS|Intuitive Surgical, Inc.|USA|35|200|0.40|
CAT|XNYS|Caterpillar Inc.|USA|20|220|0.35|
GE|XNYS|GE Aerospace|USA|20|300|0.40|
HON|XNAS|Honeywell International Inc.|USA|20|140|0.30|
UNP|XNYS|Union Pacific Corporation|USA|20|140|0.25|
RTX|XNYS|RTX Corporation|USA|20|200|0.25|
LMT|XNYS|Lockheed Martin Corporation|USA|20|110|0.25|
NEE|XNYS|NextEra Energy, Inc.|USA|55|160|0.35|
DUK|XNYS|Duke Energy Corporation|USA|55|90|0.15|
SO|XNYS|The Southern Company|USA|55|100|0.15|
PLD|XNYS|Prologis, Inc.|USA|60|110|0.20|
AMT|XNYS|American Tower Corporation|USA|60|95|0.20|
LIN|XNAS|Linde plc|USA|15|220|0.30|
NKE|XNYS|NIKE, Inc.|USA|25|110|0.30|
MCD|XNYS|McDonald's Corporation|USA|25|220|0.35|
SBUX|XNAS|Starbucks Corporation|USA|25|100|0.25|
PLTR|XNAS|Palantir Technologies Inc.|USA|45|400|0.50|
UBER|XNYS|Uber Technologies, Inc.|USA|20|200|0.35|
NOW|XNYS|ServiceNow, Inc.|USA|45|210|0.30|
INTU|XNAS|Intuit Inc.|USA|45|190|0.25|
QCOM|XNAS|QUALCOMM Incorporated|USA|45|180|0.30|
TXN|XNAS|Texas Instruments Incorporated|USA|45|170|0.25|
MU|XNAS|Micron Technology, Inc.|USA|45|200|0.35|
AMAT|XNAS|Applied Materials, Inc.|USA|45|170|0.30|
BKNG|XNAS|Booking Holdings Inc.|USA|25|170|0.25|
SPGI|XNYS|S&P Global Inc.|USA|40|160|0.25|
BLK|XNYS|BlackRock, Inc.|USA|40|160|0.30|
SCHW|XNYS|The Charles Schwab Corporation|USA|40|150|0.20|
CB|XNYS|Chubb Limited|USA|40|115|0.20|
T|XNYS|AT&T Inc.|USA|50|190|0.25|
VZ|XNYS|Verizon Communications Inc.|USA|50|180|0.25|
CMCSA|XNAS|Comcast Corporation|USA|50|140|0.20|
COP|XNYS|ConocoPhillips|USA|10|120|0.20|
DE|XNYS|Deere & Company|USA|20|130|0.25|
MO|XNYS|Altria Group, Inc.|USA|30|100|0.20|
PM|XNYS|Philip Morris International Inc.|USA|30|250|0.25|
ARM|XNAS|Arm Holdings plc|GBR|45|160|0.40|
SPOT|XNYS|Spotify Technology S.A.|SWE|50|130|0.30|
SE|XNYS|Sea Limited|SGP|25|90|0.25|
MELI|XNAS|MercadoLibre, Inc.|ARG|25|120|0.40|
NU|XNYS|Nu Holdings Ltd.|BRA|40|70|0.25|
SHOP|XTSE|Shopify Inc.|CAN|45|200|0.40|LINE:SHOP:XNYS
RY|XTSE|Royal Bank of Canada|CAN|40|190|0.25|LINE:RY:XNYS
TD|XTSE|The Toronto-Dominion Bank|CAN|40|120|0.20|LINE:TD:XNYS
ENB|XTSE|Enbridge Inc.|CAN|10|100|0.20|LINE:ENB:XNYS
CNR|XTSE|Canadian National Railway Company|CAN|20|75|0.15|LINE:CNI:XNYS
ASML|XAMS|ASML Holding N.V.|NLD|45|320|0.85|LINE:ASML:XNAS
ADYEN|XAMS|Adyen N.V.|NLD|40|55|0.30|
PRX|XAMS|Prosus N.V.|NLD|25|120|0.25|
NOVO.B|XCSE|Novo Nordisk A/S|DNK|35|300|0.75|ADR:NVO:XNYS
NESN|XSWX|Nestle S.A.|CHE|30|260|0.60|
ROG|XSWX|Roche Holding AG|CHE|35|250|0.45|
NOVN|XSWX|Novartis AG|CHE|35|230|0.45|ADR:NVS:XNYS
ABBN|XSWX|ABB Ltd|CHE|20|110|0.30|
UBSG|XSWX|UBS Group AG|CHE|40|110|0.30|ADR:UBS:XNYS
ZURN|XSWX|Zurich Insurance Group AG|CHE|40|95|0.20|
MC|XPAR|LVMH Moet Hennessy Louis Vuitton SE|FRA|25|350|0.65|
OR|XPAR|L'Oreal S.A.|FRA|30|220|0.40|
RMS|XPAR|Hermes International|FRA|25|260|0.45|
TTE|XPAR|TotalEnergies SE|FRA|10|140|0.35|ADR:TTE:XNYS
AIR|XPAR|Airbus SE|FRA|20|150|0.35|
SU|XPAR|Schneider Electric SE|FRA|20|150|0.35|
SAN|XPAR|Sanofi|FRA|35|130|0.30|ADR:SNY:XNAS
SAP|XETR|SAP SE|DEU|45|330|0.65|ADR:SAP:XNYS
SIE|XETR|Siemens AG|DEU|20|170|0.45|
ALV|XETR|Allianz SE|DEU|40|150|0.35|
DTE|XETR|Deutsche Telekom AG|DEU|50|170|0.30|
RHM|XETR|Rheinmetall AG|DEU|20|90|0.35|
AZN|XLON|AstraZeneca PLC|GBR|35|250|0.55|ADR:AZN:XNAS
SHEL|XLON|Shell plc|GBR|10|220|0.50|ADR:SHEL:XNYS
HSBA|XLON|HSBC Holdings plc|GBR|40|220|0.45|ADR:HSBC:XNYS
ULVR|XLON|Unilever PLC|GBR|30|150|0.40|ADR:UL:XNYS
RIO|XLON|Rio Tinto plc|GBR|15|110|0.30|ADR:RIO:XNYS
BP.|XLON|BP p.l.c.|GBR|10|85|0.30|ADR:BP:XNYS
GSK|XLON|GSK plc|GBR|35|80|0.20|ADR:GSK:XNYS
LSEG|XLON|London Stock Exchange Group plc|GBR|40|70|0.20|
REL|XLON|RELX PLC|GBR|20|95|0.25|ADR:RELX:XNYS
BARC|XLON|Barclays PLC|GBR|40|60|0.20|
ITX|XMAD|Industria de Diseno Textil S.A.|ESP|25|170|0.35|
SAN|XMAD|Banco Santander S.A.|ESP|40|120|0.25|ADR:SAN:XNYS
IBE|XMAD|Iberdrola S.A.|ESP|55|110|0.30|
ENEL|XMIL|Enel S.p.A.|ITA|55|85|0.25|
UCG|XMIL|UniCredit S.p.A.|ITA|40|90|0.30|
RACE|XMIL|Ferrari N.V.|ITA|25|90|0.40|LINE:RACE:XNYS
ATCO.A|XSTO|Atlas Copco AB|SWE|20|85|0.20|
INVE.B|XSTO|Investor AB|SWE|40|90|0.15|
NOKIA|XHEL|Nokia Oyj|FIN|45|30|0.15|
EQNR|XOSL|Equinor ASA|NOR|10|70|0.20|
7203|XTKS|Toyota Motor Corporation|JPN|25|280|0.55|ADR:TM:XNYS
6758|XTKS|Sony Group Corporation|JPN|25|170|0.45|ADR:SONY:XNYS
8306|XTKS|Mitsubishi UFJ Financial Group, Inc.|JPN|40|160|0.25|ADR:MUFG:XNYS
6861|XTKS|Keyence Corporation|JPN|45|110|0.30|
9984|XTKS|SoftBank Group Corp.|JPN|50|120|0.35|
8035|XTKS|Tokyo Electron Limited|JPN|45|100|0.30|
6501|XTKS|Hitachi, Ltd.|JPN|20|130|0.30|
9983|XTKS|Fast Retailing Co., Ltd.|JPN|25|110|0.25|
4063|XTKS|Shin-Etsu Chemical Co., Ltd.|JPN|15|75|0.20|
7974|XTKS|Nintendo Co., Ltd.|JPN|50|90|0.30|
0700|XHKG|Tencent Holdings Limited|CHN|50|650|0.75|
9988|XHKG|Alibaba Group Holding Limited|CHN|25|330|0.60|ADR:BABA:XNYS
3690|XHKG|Meituan|CHN|25|110|0.30|
1299|XHKG|AIA Group Limited|HKG|40|95|0.30|
0939|XHKG|China Construction Bank Corporation|CHN|40|230|0.20|LINE:601939:XSHG
1398|XHKG|Industrial and Commercial Bank of China Limited|CHN|40|300|0.20|LINE:601398:XSHG
2318|XHKG|Ping An Insurance (Group) Company of China, Ltd.|CHN|40|120|0.25|LINE:601318:XSHG
1211|XHKG|BYD Company Limited|CHN|25|140|0.45|LINE:002594:XSHE
9618|XHKG|JD.com, Inc.|CHN|25|50|0.20|ADR:JD:XNAS
0941|XHKG|China Mobile Limited|CHN|50|230|0.25|LINE:600941:XSHG
1810|XHKG|Xiaomi Corporation|CHN|45|180|0.35|
0388|XHKG|Hong Kong Exchanges and Clearing Limited|HKG|40|65|0.20|
600519|XSHG|Kweichow Moutai Co., Ltd.|CHN|30|260|0.50|
300750|XSHE|Contemporary Amperex Technology Co., Limited|CHN|20|220|0.45|LINE:3750:XHKG
600036|XSHG|China Merchants Bank Co., Ltd.|CHN|40|140|0.25|LINE:3968:XHKG
000858|XSHE|Wuliangye Yibin Co., Ltd.|CHN|30|75|0.30|
000333|XSHE|Midea Group Co., Ltd.|CHN|25|80|0.25|LINE:0300:XHKG
601899|XSHG|Zijin Mining Group Co., Ltd.|CHN|15|90|0.20|LINE:2899:XHKG
600900|XSHG|China Yangtze Power Co., Ltd.|CHN|55|100|0.20|
688981|XSHG|Semiconductor Manufacturing International Corporation|CHN|45|90|0.25|LINE:0981:XHKG
2330|XTAI|Taiwan Semiconductor Manufacturing Company Limited|TWN|45|1300|0.90|ADR:TSM:XNYS
2317|XTAI|Hon Hai Precision Industry Co., Ltd.|TWN|45|100|0.30|
2454|XTAI|MediaTek Inc.|TWN|45|75|0.30|
005930|XKRX|Samsung Electronics Co., Ltd.|KOR|45|420|0.65|
000660|XKRX|SK hynix Inc.|KOR|45|180|0.45|
035420|XKRX|NAVER Corporation|KOR|50|25|0.15|
RELIANCE|XNSE|Reliance Industries Limited|IND|10|230|0.45|
TCS|XNSE|Tata Consultancy Services Limited|IND|45|150|0.30|
HDFCBANK|XNSE|HDFC Bank Limited|IND|40|170|0.35|ADR:HDB:XNYS
INFY|XNSE|Infosys Limited|IND|45|80|0.35|ADR:INFY:XNYS
ICICIBANK|XNSE|ICICI Bank Limited|IND|40|110|0.25|ADR:IBN:XNYS
BHP|XASX|BHP Group Limited|AUS|15|150|0.40|ADR:BHP:XNYS
CBA|XASX|Commonwealth Bank of Australia|AUS|40|190|0.30|
CSL|XASX|CSL Limited|AUS|35|80|0.20|
VALE3|BVMF|Vale S.A.|BRA|15|50|0.20|ADR:VALE:XNYS
PETR4|BVMF|Petroleo Brasileiro S.A. - Petrobras|BRA|10|80|0.20|ADR:PBR:XNYS
2222|XSAU|Saudi Arabian Oil Company|SAU|10|1700|0.35|
D05|XSES|DBS Group Holdings Ltd|SGP|40|110|0.20|
NPN|XJSE|Naspers Limited|ZAF|25|50|0.15|
"""

# Weights used to place the synthetic filler companies (roughly ACWI-like).
FILLER_COUNTRIES = [
    ("USA", 0.44), ("JPN", 0.08), ("GBR", 0.05), ("CAN", 0.04), ("FRA", 0.03), ("DEU", 0.03), ("CHE", 0.025),
    ("CHN", 0.07), ("TWN", 0.03), ("IND", 0.05), ("KOR", 0.025), ("AUS", 0.03), ("NLD", 0.01), ("SWE", 0.015),
    ("HKG", 0.015), ("ITA", 0.01), ("ESP", 0.01), ("BRA", 0.015), ("ZAF", 0.01), ("SAU", 0.01), ("DNK", 0.006),
    ("SGP", 0.006), ("MEX", 0.008), ("NOR", 0.005),
]

COUNTRY_EXCHANGE = {
    "USA": "XNYS", "JPN": "XTKS", "GBR": "XLON", "CAN": "XTSE", "FRA": "XPAR", "DEU": "XETR", "CHE": "XSWX",
    "CHN": "XHKG", "TWN": "XTAI", "IND": "XNSE", "KOR": "XKRX", "AUS": "XASX", "NLD": "XAMS", "SWE": "XSTO",
    "HKG": "XHKG", "ITA": "XMIL", "ESP": "XMAD", "BRA": "BVMF", "ZAF": "XJSE", "SAU": "XSAU", "DNK": "XCSE",
    "SGP": "XSES", "MEX": "XMEX", "NOR": "XOSL", "FIN": "XHEL", "ARG": "XNAS",
}

COUNTRY_CURRENCY = {
    "USA": "USD", "JPN": "JPY", "GBR": "GBP", "CAN": "CAD", "FRA": "EUR", "DEU": "EUR", "CHE": "CHF",
    "CHN": "HKD", "TWN": "TWD", "IND": "INR", "KOR": "KRW", "AUS": "AUD", "NLD": "EUR", "SWE": "SEK",
    "HKG": "HKD", "ITA": "EUR", "ESP": "EUR", "BRA": "BRL", "ZAF": "ZAR", "SAU": "SAR", "DNK": "DKK",
    "SGP": "SGD", "MEX": "MXN", "NOR": "NOK", "FIN": "EUR", "ARG": "USD",
}

EXCHANGE_CURRENCY = {
    "XNAS": "USD", "XNYS": "USD", "XASE": "USD", "XTSE": "CAD", "XLON": "GBP", "XETR": "EUR", "XPAR": "EUR",
    "XAMS": "EUR", "XMIL": "EUR", "XMAD": "EUR", "XSWX": "CHF", "XCSE": "DKK", "XSTO": "SEK", "XHEL": "EUR",
    "XOSL": "NOK", "XTKS": "JPY", "XHKG": "HKD", "XSHG": "CNY", "XSHE": "CNY", "XTAI": "TWD", "XKRX": "KRW",
    "XNSE": "INR", "XASX": "AUD", "XSES": "SGD", "XJSE": "ZAR", "BVMF": "BRL", "XMEX": "MXN", "XSAU": "SAR",
}

# Synthetic Compustat exchg codes (US codes are the real ones).
EXCHANGE_EXCHG = {
    "XNYS": 11, "XASE": 12, "XNAS": 14, "XTSE": 7, "XLON": 194, "XETR": 171, "XPAR": 121, "XAMS": 104,
    "XMIL": 152, "XMAD": 112, "XSWX": 151, "XCSE": 144, "XSTO": 256, "XHEL": 172, "XOSL": 228, "XTKS": 280,
    "XHKG": 170, "XSHG": 249, "XSHE": 250, "XTAI": 245, "XKRX": 298, "XNSE": 286, "XASX": 106, "XSES": 251,
    "XJSE": 154, "BVMF": 248, "XMEX": 208, "XSAU": 300,
}

GICS_SECTORS = {
    "10": "Energy", "15": "Materials", "20": "Industrials", "25": "Consumer Discretionary",
    "30": "Consumer Staples", "35": "Health Care", "40": "Financials", "45": "Information Technology",
    "50": "Communication Services", "55": "Utilities", "60": "Real Estate",
}


def parse_curated() -> list[dict]:
    rows = []
    lines = CURATED.strip().splitlines()
    for i in range(len(lines)):
        parts = lines[i].split("|")
        if len(parts) < 7:
            continue
        extras = []
        if len(parts) > 7 and parts[7].strip():
            chunks = parts[7].split(",")
            for j in range(len(chunks)):
                kind, ticker, exchange = chunks[j].strip().split(":")
                extras.append({"kind": kind, "ticker": ticker, "exchange": exchange})
        rows.append({
            "ticker": parts[0].strip(), "exchange": parts[1].strip(), "name": parts[2].strip(),
            "country": parts[3].strip(), "gsector": parts[4].strip(), "mcap_bn": float(parts[5]),
            "familiarity": float(parts[6]), "extras": extras,
        })
    return rows
