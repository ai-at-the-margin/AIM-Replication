"""
check_wrds_access.py

Checks which WRDS datasets you can reach and how current they are, for the
"AI at the Margin" replication project.

What it does
------------
1. Connects to WRDS (prompts for username/password the first time and can
   create ~/.pgpass so you are not asked again).
2. Lists every library your account can see and flags the ones that matter
   for this project (CRSP, Compustat, Compustat Snapshot, IBES, Datastream,
   Worldscope, Capital IQ, MSCI/Barra/Axioma, FactSet, RavenPack, Fama-French,
   WRDS apps, ...).
3. For the core tables the build brief depends on, checks:
   - whether you can actually read the table (not just see it),
   - the most recent date available,
   - the number of rows on that most recent date (where cheap to compute).
4. Writes everything to wrds_access_report.md and wrds_libraries.csv so you
   can paste it back into the chat.

Usage
-----
    pip install wrds pandas sqlalchemy
    python check_wrds_access.py --username YOUR_WRDS_USERNAME

Every check is wrapped so that a missing library, a permission error or a
slow query never stops the run; failures are recorded in the report.
"""

import argparse
import datetime
import sys
import time

import pandas as pd

try:
    import wrds
except ImportError:
    print("The 'wrds' package is not installed. Run: pip install wrds")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

# Keywords used to flag potentially useful libraries in the full listing.
INTEREST_KEYWORDS = [
    "crsp", "comp", "snapshot", "ibes", "tr_", "datastream", "worldscope",
    "ciq", "capiq", "msci", "barra", "axioma", "factset", "ravenpack", "rpna",
    "ff", "wrdsapps", "markit", "bloomberg", "morningstar", "sp_", "audit",
    "boardex", "taq", "optionm", "mfl", "tfn", "thomson", "lseg", "refinitiv",
]

# Only look for dates after this cutoff (keeps queries on huge tables fast).
RECENT_CUTOFF = "2025-06-01"

# Candidate date columns, in order of preference.
DATE_COLUMN_CANDIDATES = [
    "datadate", "dlycaldt", "date", "caldt", "mthcaldt", "statpers",
    "anndats", "rdq", "from_date", "timestamp_utc", "rpna_date_utc",
]

# Core tables from the build brief: (library, table, purpose, count_latest_rows)
CORE_TABLES = [
    ("comp", "secd", "NA daily prices/returns (primary price source)", True),
    ("comp", "g_secd", "Global daily prices/returns (primary price source)", True),
    ("comp", "g_exrt_dly", "Daily FX rates (GBP-based)", True),
    ("comp", "security", "NA security master (tickers, exchanges)", False),
    ("comp", "g_security", "Global security master (tickers, ISIN)", False),
    ("comp", "company", "NA company master, GICS", False),
    ("comp", "g_company", "Global company master, GICS", False),
    ("comp", "funda", "NA annual fundamentals", False),
    ("comp", "fundq", "NA quarterly fundamentals (rdq)", False),
    ("comp", "g_funda", "Global annual fundamentals", False),
    ("comp", "g_fundq", "Global quarterly fundamentals", False),
    ("comp", "idxcst_his", "S&P index constituents history", False),
    ("ff", "factors_daily", "Fama-French daily factors incl. risk-free rate", False),
    ("crsp", "dsf_v2", "CRSP daily stock file, CIZ format (US cross-check)", True),
    ("crsp", "dsf", "CRSP daily stock file, legacy SIZ format", False),
    ("crsp", "msf_v2", "CRSP monthly stock file, CIZ format", False),
    ("crsp", "ccmxpf_lnkhist", "CRSP-Compustat link table", False),
]

# Optional datasets that could upgrade the design. For these we only check
# that the library exists and list its tables; we do not guess table schemas.
OPTIONAL_LIBRARIES = [
    ("comp_snapshot", "Compustat Snapshot: true point-in-time fundamentals"),
    ("ibes", "I/B/E/S analyst forecasts: forward earnings yield, coverage"),
    ("tr_ds_equities", "Datastream equities: global total-return index (RI)"),
    ("tr_worldscope", "Worldscope: alternative global fundamentals"),
    ("ciq", "Capital IQ: company/security identifiers for cross-listings"),
    ("msci", "MSCI data (indices / constituents / GICS) if licensed"),
    ("barra", "MSCI Barra risk model exposures (exact replication)"),
    ("axioma", "Axioma risk model exposures (alternative to Barra)"),
    ("factset", "FactSet (fundamentals / ownership) if licensed"),
    ("ravenpack_dj", "RavenPack news analytics (future news-check extension)"),
    ("wrdsapps_finratio", "WRDS Financial Ratios Suite (US)"),
    ("wrdsapps_beta", "WRDS Beta Suite"),
    ("ff_all", "Fama-French full library"),
    ("crsp_a_stock", "CRSP stock, ANNUAL update"),
    ("crsp_q_stock", "CRSP stock, QUARTERLY update"),
    ("crsp_m_stock", "CRSP stock, MONTHLY update"),
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def log(message):
    stamp = datetime.datetime.now().strftime("%H:%M:%S")
    print(f"[{stamp}] {message}", flush=True)


def safe_sql(db, sql):
    """Run a query; return (DataFrame or None, error string or None)."""
    try:
        result = db.raw_sql(sql)
        return result, None
    except Exception as exc:  # permission errors, timeouts, missing tables...
        text = str(exc).strip().split("\n")[0]
        return None, text[:300]


def set_statement_timeout(db, seconds):
    """Ask Postgres to cancel any single query that runs too long."""
    try:
        from sqlalchemy import text
        db.connection.execute(text(f"SET statement_timeout = {int(seconds * 1000)}"))
        return True
    except Exception as exc:
        log(f"Could not set statement timeout (continuing without it): {exc}")
        return False


def get_columns(db, library, table):
    """Return the list of column names for a table, or an empty list."""
    try:
        description = db.describe_table(library=library, table=table)
    except Exception:
        return []
    if description is None or "name" not in description.columns:
        return []
    names = []
    values = description["name"].tolist()
    for i in range(len(values)):
        names.append(str(values[i]).lower())
    return names


def pick_date_column(columns):
    for i in range(len(DATE_COLUMN_CANDIDATES)):
        candidate = DATE_COLUMN_CANDIDATES[i]
        if candidate in columns:
            return candidate
    return None


def check_core_table(db, library, table, purpose, count_latest):
    """Check readability, latest date and latest-day row count for one table."""
    row = {
        "library": library,
        "table": table,
        "purpose": purpose,
        "readable": False,
        "date_column": None,
        "latest_date": None,
        "rows_on_latest_date": None,
        "query_seconds": None,
        "note": "",
    }

    started = time.time()

    # 1. Can we read at least one row?
    probe, error = safe_sql(db, f"SELECT * FROM {library}.{table} LIMIT 1")
    if error is not None:
        row["note"] = f"not readable: {error}"
        row["query_seconds"] = round(time.time() - started, 1)
        return row
    row["readable"] = True

    # 2. Find a date column.
    columns = get_columns(db, library, table)
    if len(columns) == 0 and probe is not None:
        probe_columns = probe.columns.tolist()
        for i in range(len(probe_columns)):
            columns.append(str(probe_columns[i]).lower())
    date_column = pick_date_column(columns)
    row["date_column"] = date_column

    if date_column is None:
        row["note"] = "readable; no recognised date column (master/static table)"
        row["query_seconds"] = round(time.time() - started, 1)
        return row

    # 3. Latest date (restricted to recent rows to keep it fast).
    sql = (
        f"SELECT MAX({date_column}) AS latest FROM {library}.{table} "
        f"WHERE {date_column} >= '{RECENT_CUTOFF}'"
    )
    latest_df, error = safe_sql(db, sql)
    if error is not None:
        row["note"] = f"max-date query failed: {error}"
    elif latest_df is not None and len(latest_df) > 0:
        latest_value = latest_df.iloc[0]["latest"]
        if pd.isna(latest_value):
            row["note"] = f"no rows after {RECENT_CUTOFF} (data may be stale)"
        else:
            row["latest_date"] = str(latest_value)[:10]

    # 4. Rows on the latest date (only for daily price-type tables).
    if count_latest and row["latest_date"] is not None:
        sql = (
            f"SELECT COUNT(*) AS n FROM {library}.{table} "
            f"WHERE {date_column} = '{row['latest_date']}'"
        )
        count_df, error = safe_sql(db, sql)
        if error is None and count_df is not None and len(count_df) > 0:
            row["rows_on_latest_date"] = int(count_df.iloc[0]["n"])

    row["query_seconds"] = round(time.time() - started, 1)
    return row


def check_optional_library(db, library, purpose, accessible_set):
    row = {
        "library": library,
        "purpose": purpose,
        "visible": library in accessible_set,
        "n_tables": None,
        "sample_tables": "",
        "readable_sample": None,
        "note": "",
    }
    if not row["visible"]:
        row["note"] = "not in your library list"
        return row

    try:
        tables = db.list_tables(library=library)
    except Exception as exc:
        row["note"] = f"could not list tables: {str(exc)[:200]}"
        return row

    if tables is None:
        tables = []
    row["n_tables"] = len(tables)

    sample = []
    limit = min(12, len(tables))
    for i in range(limit):
        sample.append(str(tables[i]))
    row["sample_tables"] = ", ".join(sample)

    # Try to read one row from the first table to confirm real access.
    if len(tables) > 0:
        _, error = safe_sql(db, f"SELECT * FROM {library}.{tables[0]} LIMIT 1")
        row["readable_sample"] = error is None
        if error is not None:
            row["note"] = f"listed but not readable: {error}"
    return row


def flag_interesting(libraries):
    flagged = []
    for i in range(len(libraries)):
        name = str(libraries[i]).lower()
        for j in range(len(INTEREST_KEYWORDS)):
            if INTEREST_KEYWORDS[j] in name:
                flagged.append(libraries[i])
                break
    return flagged


def frame_to_markdown(frame):
    """Markdown table without requiring the optional 'tabulate' package."""
    if frame is None or len(frame) == 0:
        return "_(empty)_\n"
    columns = frame.columns.tolist()
    lines = []
    lines.append("| " + " | ".join(str(c) for c in columns) + " |")
    separators = []
    for i in range(len(columns)):
        separators.append("---")
    lines.append("| " + " | ".join(separators) + " |")
    for r in range(len(frame)):
        cells = []
        for c in range(len(columns)):
            value = frame.iloc[r, c]
            if value is None or (isinstance(value, float) and pd.isna(value)):
                cells.append("")
            else:
                cells.append(str(value).replace("|", "/"))
        lines.append("| " + " | ".join(cells) + " |")
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Check WRDS dataset access.")
    parser.add_argument("--username", default=None, help="WRDS username")
    parser.add_argument("--timeout", type=int, default=180,
                        help="Per-query timeout in seconds (default 180)")
    parser.add_argument("--output", default="wrds_access_report.md")
    args = parser.parse_args()

    log("Connecting to WRDS ...")
    try:
        if args.username:
            db = wrds.Connection(wrds_username=args.username)
        else:
            db = wrds.Connection()
    except Exception as exc:
        log(f"Connection failed: {exc}")
        sys.exit(1)
    log("Connected.")

    set_statement_timeout(db, args.timeout)

    # 1. All libraries -------------------------------------------------------
    try:
        libraries = sorted(db.list_libraries())
    except Exception as exc:
        log(f"Could not list libraries: {exc}")
        libraries = []
    log(f"Your account can see {len(libraries)} libraries.")

    accessible_set = set()
    for i in range(len(libraries)):
        accessible_set.add(libraries[i])

    flagged = flag_interesting(libraries)
    library_rows = []
    for i in range(len(libraries)):
        is_flagged = libraries[i] in flagged
        library_rows.append({"library": libraries[i], "flagged": is_flagged})
    pd.DataFrame(library_rows).to_csv("wrds_libraries.csv", index=False)

    # 2. Core tables ---------------------------------------------------------
    core_rows = []
    for i in range(len(CORE_TABLES)):
        library, table, purpose, count_latest = CORE_TABLES[i]
        log(f"Checking core table {library}.{table} ...")
        result = check_core_table(db, library, table, purpose, count_latest)
        core_rows.append(result)
        log(f"  readable={result['readable']} latest={result['latest_date']} "
            f"{result['note']}")
    core_frame = pd.DataFrame(core_rows)

    # 3. Optional libraries --------------------------------------------------
    optional_rows = []
    for i in range(len(OPTIONAL_LIBRARIES)):
        library, purpose = OPTIONAL_LIBRARIES[i]
        log(f"Checking optional library {library} ...")
        optional_rows.append(check_optional_library(db, library, purpose, accessible_set))
    optional_frame = pd.DataFrame(optional_rows)

    # 4. Report --------------------------------------------------------------
    lines = []
    lines.append("# WRDS access report\n")
    lines.append(f"Generated: {datetime.datetime.now().isoformat(timespec='seconds')}\n")
    lines.append(f"Libraries visible to this account: {len(libraries)}\n")
    lines.append("\n## Core tables (from the build brief)\n")
    lines.append(frame_to_markdown(core_frame))
    lines.append("\n## Optional datasets that could upgrade the design\n")
    lines.append(frame_to_markdown(optional_frame))
    lines.append("\n## All flagged libraries (keyword match)\n")
    if len(flagged) == 0:
        lines.append("_(none)_\n")
    else:
        lines.append(", ".join(flagged) + "\n")
    lines.append("\nFull library list saved to wrds_libraries.csv\n")

    with open(args.output, "w", encoding="utf-8") as handle:
        handle.write("\n".join(lines))

    try:
        db.close()
    except Exception:
        pass

    log(f"Done. Report written to {args.output} and wrds_libraries.csv")
    log("Paste the report back into the chat so the brief can be updated.")


if __name__ == "__main__":
    main()