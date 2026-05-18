"""Rebuild ``data/nasdaq100_membership.csv`` from a hard-coded changelog.

The changelog was extracted once from the "Annual changes" section of the
Nasdaq-100 Wikipedia page. To refresh after future reconstitutions, edit
``CHANGES`` below (or re-fetch the page) and re-run::

    python scripts/build_membership.py

Output schema (matches what ``src/membership.py`` expects):

    ticker,start_date,end_date
    AAPL,2000-01-01,
    NVDA,2001-11-15,
    MSTR,2024-12-23,
    ILMN,2008-12-22,2024-12-23
    SMCI,2024-07-22,2024-12-23
    ...

An empty ``end_date`` means "still a constituent today."

Algorithm
---------
1. Walk ``CHANGES`` oldest → newest.
2. Maintain a dict ``active[ticker] = start_date`` of currently-open spans.
3. On ``added``: open a new span starting at ``effective``.
4. On ``removed``: close the active span at ``effective`` and emit a row.
5. At the end, every ticker still in ``active`` becomes an open-ended row.
6. Reconcile against the current ``CURRENT_NASDAQ100`` list:
   * Tickers in ``active`` but not currently constituents → close them
     with end_date "?" so they're treated as historical.
   * Tickers in current but not seen in ``active`` → they joined before
     the changelog window; emit an open-ended row starting at
     ``DEFAULT_HISTORY_START``.

The output is a best-effort point-in-time membership file. For names that
joined before 2007 (where our changelog begins), ``start_date`` is the
``DEFAULT_HISTORY_START`` placeholder, which only matters if you backtest
that far back.
"""

from __future__ import annotations

import csv
import os
import sys
from typing import Dict, List, Tuple

HERE = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.abspath(os.path.join(HERE, ".."))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from src.config import CURRENT_NASDAQ100, MEMBERSHIP_CSV


DEFAULT_HISTORY_START = "2000-01-01"


# Sourced from the Wikipedia "Nasdaq-100 § Annual changes" tables.
# Sorted ascending by ``effective`` at runtime. Ticker variants kept as-is
# (e.g. share-class splits: FOX/FOXA, LBTYA/LBTYK, GOOG/GOOGL).
CHANGES: List[Dict] = [
    {"effective": "2007-02-01", "added": ["LOGI"], "removed": ["CMVT"]},
    {"effective": "2007-02-14", "added": ["RYAAY"], "removed": ["APCC"]},
    {"effective": "2007-03-08", "added": ["UAUA"], "removed": ["AEOS"]},
    {"effective": "2007-06-01", "added": ["CEPH"], "removed": ["MEDI"]},
    {"effective": "2007-07-12", "added": ["FWLT"], "removed": ["BMET"]},
    {"effective": "2007-08-27", "added": ["VMED"], "removed": ["NLTI"]},
    {"effective": "2007-10-08", "added": ["LEAP"], "removed": ["CDWC"]},
    {"effective": "2007-12-04", "added": ["BIDU"], "removed": ["CKFR"]},
    {"effective": "2007-12-24", "added": ["HOLX", "FMCN", "HANS", "STLD", "SRCL"],
        "removed": ["ERIC", "PTEN", "ROST", "SEPR", "XMSR"]},
    {"effective": "2008-04-30", "added": ["DTV"], "removed": ["BEAS"]},
    {"effective": "2008-05-19", "added": ["CA"], "removed": ["TLAB"]},
    {"effective": "2008-07-21", "added": ["FLIR"], "removed": ["UAUA"]},
    {"effective": "2008-11-10", "added": ["STX"], "removed": ["MNST"]},
    {"effective": "2008-12-22",
        "added": ["ADP", "FSLR", "LIFE", "ROST", "MXIM", "ILMN", "PPDI", "ORLY", "URBN", "JBHT", "WCRX"],
        "removed": ["AMLN", "CDNS", "DISCA", "LAMR", "LEAP", "LVLT", "PETM", "SIRI", "SNDK", "VMED", "WFMI"]},
    {"effective": "2009-01-20", "added": ["NWSA"], "removed": ["FMCN"]},
    {"effective": "2009-07-17", "added": ["CERN"], "removed": ["JAVA"]},
    {"effective": "2009-10-29", "added": ["PCLN"], "removed": ["JNPR"]},
    {"effective": "2009-12-21", "added": ["VOD", "MAT", "BMC", "MYL", "QGEN", "SNDK", "VMED"],
        "removed": ["AKAM", "HANS", "IACI", "LBTYA", "PPDI", "RYAAY", "STLD"]},
    {"effective": "2010-12-20", "added": ["AKAM", "CTRP", "DLTR", "FFIV", "MU", "NFLX", "WFMI"],
        "removed": ["CTAS", "DISH", "FWLT", "HOLX", "JBHT", "LOGI", "PDCO"]},
    {"effective": "2011-04-04", "added": ["ALXN"], "removed": ["GENZ"]},
    {"effective": "2011-05-27", "added": ["GMCR"], "removed": ["MICC"]},
    {"effective": "2011-07-15", "added": ["SIRI"], "removed": ["CEPH"]},
    {"effective": "2011-12-06", "added": ["PRGO"], "removed": ["JOYG"]},
    {"effective": "2011-12-19", "added": ["AVGO", "FOSL", "HANS", "NUAN", "GOLD"],
        "removed": ["FLIR", "ILMN", "NIHD", "QGEN", "URBN"]},
    {"effective": "2012-04-23", "added": ["TXN"], "removed": ["FSLR"]},
    {"effective": "2012-05-30", "added": ["VIAB"], "removed": ["TEVA"]},
    {"effective": "2012-07-23", "added": ["KFT"], "removed": ["CTRP"]},
    {"effective": "2012-12-12", "added": ["FB"], "removed": ["INFY"]},
    {"effective": "2012-12-24",
        "added": ["ADI", "CTRX", "DISCA", "EQIX", "LBTYA", "LMCA", "REGN", "SBAC", "VRSK", "WDC"],
        "removed": ["APOL", "EA", "FLEX", "GMCR", "LRCX", "MRVL", "NFLX", "RIMM", "VRSN", "WCRX"]},
    {"effective": "2013-01-15", "added": ["STRZA"], "removed": ["LMCA"]},
    {"effective": "2013-03-18", "added": ["KRFT"], "removed": ["STRZA"]},
    {"effective": "2013-06-05", "added": ["LMCA"], "removed": ["VMED"]},
    {"effective": "2013-06-06", "added": ["NFLX"], "removed": ["PRGO"]},
    {"effective": "2013-07-15", "added": ["TSLA"], "removed": ["ORCL"]},
    {"effective": "2013-07-25", "added": ["CHTR"], "removed": ["BMC"]},
    {"effective": "2013-08-22", "added": ["GMCR"], "removed": ["LIFE"]},
    {"effective": "2013-10-29", "added": ["VIP"], "removed": ["DELL"]},
    {"effective": "2013-11-18", "added": ["MAR"], "removed": ["GOLD"]},
    {"effective": "2013-12-23", "added": ["DISH", "ILMN", "NXPI", "TRIP", "TSCO"],
        "removed": ["FOSL", "MCHP", "NUAN", "SHLD", "XRAY"]},
    {"effective": "2014-04-03", "added": ["GOOG"], "removed": []},
    {"effective": "2014-12-22", "added": ["AAL", "EA", "LRCX", "CMCSK", "FOX", "LBTYK"],
        "removed": ["EXPE", "FFIV", "MXIM"]},
    {"effective": "2015-03-23", "added": ["WBA"], "removed": ["EQIX"]},
    {"effective": "2015-07-02", "added": ["KHC", "LILA", "LILAK"], "removed": ["KRFT"]},
    {"effective": "2015-07-24", "added": [], "removed": ["DTV", "CTRX"]},
    {"effective": "2015-07-27", "added": ["BMRN"], "removed": ["DTV"]},
    {"effective": "2015-07-29", "added": ["JD"], "removed": ["CTRX"]},
    {"effective": "2015-08-03", "added": ["SWKS"], "removed": ["SIAL"]},
    {"effective": "2015-10-07", "added": ["INCY"], "removed": ["ALTR"]},
    {"effective": "2015-11-11", "added": ["PYPL"], "removed": ["BRCM"]},
    {"effective": "2015-12-21",
        "added": ["CTRP", "ENDP", "EXPE", "MXIM", "NCLH", "TMUS", "ULTA", "LILA", "LILAK"],
        "removed": ["CHRW", "EXPD", "GMCR", "GRMN", "SPLS", "VIP", "WYNN"]},
    {"effective": "2016-02-01", "added": ["AVGO"], "removed": []},
    {"effective": "2016-02-16", "added": ["CSX"], "removed": ["KLAC"]},
    {"effective": "2016-03-16", "added": ["NTES"], "removed": ["SNDK"]},
    {"effective": "2016-07-18", "added": ["MCHP"], "removed": ["NDOI"]},
    {"effective": "2016-10-19", "added": ["SHPG"], "removed": ["LLTC"]},
    {"effective": "2016-12-19", "added": ["CTAS", "HAS", "HOLX", "KLAC"],
        "removed": ["BBBY", "NTAP", "SRCL", "WFM"]},
    {"effective": "2017-02-07", "added": ["JBHT"], "removed": ["NXPI"]},
    {"effective": "2017-03-20", "added": ["IDXX"], "removed": ["SBAC"]},
    {"effective": "2017-04-24", "added": ["WYNN"], "removed": ["TRIP"]},
    {"effective": "2017-06-19", "added": ["MELI"], "removed": ["YHOO"]},
    {"effective": "2017-10-23", "added": ["ALGN"], "removed": ["MAT"]},
    {"effective": "2017-12-18", "added": ["ASML", "CDNS", "DISCK", "SNPS", "TTWO", "WDAY"],
        "removed": ["AKAM", "DISCA", "NCLH", "TSCO", "VIAB"]},
    {"effective": "2018-07-23", "added": ["PEP"], "removed": ["DISH"]},
    {"effective": "2018-11-05", "added": ["NXPI"], "removed": ["CA"]},
    {"effective": "2018-11-19", "added": ["XEL"], "removed": ["XRAY"]},
    {"effective": "2018-12-24", "added": ["AMD", "LULU", "NTAP", "UAL", "VRSN", "WLTW"],
        "removed": ["ESRX", "HOLX", "QRTEA", "SHPG", "STX", "VOD"]},
    {"effective": "2019-03-19", "added": ["FOXA", "FOX"], "removed": ["TCFCA", "TCFCB"]},
    {"effective": "2019-11-21", "added": ["EXC"], "removed": ["CELG"]},
    {"effective": "2019-12-23", "added": ["ANSS", "CDW", "CPRT", "CSGP", "SGEN", "SPLK"],
        "removed": ["HAS", "HSIC", "JBHT", "MYL", "NLOK", "WYNN"]},
    {"effective": "2020-04-20", "added": ["DXCM"], "removed": ["AAL"]},
    {"effective": "2020-04-30", "added": ["ZM"], "removed": ["WTW"]},
    {"effective": "2020-06-22", "added": ["DOCU"], "removed": ["UAL"]},
    {"effective": "2020-07-20", "added": ["MRNA"], "removed": ["CSGP"]},
    {"effective": "2020-08-24", "added": ["PDD"], "removed": ["NTAP"]},
    {"effective": "2020-10-19", "added": ["KDP"], "removed": ["WDC"]},
    {"effective": "2020-12-21", "added": ["AEP", "MRVL", "MTCH", "OKTA", "PTON", "TEAM"],
        "removed": ["BMRN", "CTXS", "EXPE", "LBTYA", "LBTYK", "ULTA"]},
    {"effective": "2021-07-21", "added": ["HON"], "removed": ["ALXN"]},
    {"effective": "2021-08-26", "added": ["CRWD"], "removed": ["MXIM"]},
    {"effective": "2021-12-20", "added": ["ABNB", "FTNT", "PANW", "LCID", "ZS", "DDOG"],
        "removed": ["CDW", "FOXA", "CERN", "CHKP", "TCOM", "INCY"]},
    {"effective": "2022-01-24", "added": ["ODFL"], "removed": ["PTON"]},
    {"effective": "2022-02-02", "added": ["CEG"], "removed": []},
    {"effective": "2022-02-22", "added": ["AZN"], "removed": ["XLNX"]},
    {"effective": "2022-11-21", "added": ["ENPH"], "removed": ["OKTA"]},
    {"effective": "2022-12-19", "added": ["CSGP", "RIVN", "NTES", "WBD", "GFS", "BKR", "FANG"],
        "removed": ["VRSN", "SWKS", "SPLK", "BIDU", "MTCH", "DOCU"]},
    {"effective": "2023-06-07", "added": ["GEHC"], "removed": ["FI"]},
    {"effective": "2023-06-20", "added": ["ON"], "removed": ["RIVN"]},
    {"effective": "2023-07-17", "added": ["TTD"], "removed": ["ATVI"]},
    {"effective": "2023-12-14", "added": ["TTWO"], "removed": ["SGEN"]},
    {"effective": "2023-12-18", "added": ["CDW", "CCEP", "DASH", "MDB", "ROP"],
        "removed": ["ALGN", "EBAY", "ENPH", "JD", "LCID", "ZM"]},
    {"effective": "2024-03-18", "added": ["LIN"], "removed": ["SPLK"]},
    {"effective": "2024-06-24", "added": ["ARM"], "removed": ["SIRI"]},
    {"effective": "2024-07-22", "added": ["SMCI"], "removed": ["WBA"]},
    {"effective": "2024-11-18", "added": ["APP"], "removed": ["DLTR"]},
    {"effective": "2024-12-23", "added": ["PLTR", "MSTR", "AXON"],
        "removed": ["ILMN", "MRNA", "SMCI"]},
    {"effective": "2025-05-19", "added": ["SHOP"], "removed": ["MDB"]},
    {"effective": "2025-07-17", "added": [], "removed": ["ANSS"]},
    {"effective": "2025-07-28", "added": ["TRI"], "removed": []},
    {"effective": "2025-12-22", "added": ["ALNY", "FER", "INSM", "MPWR", "STX", "WDC"],
        "removed": ["BIIB", "CDW", "GFS", "LULU", "ON", "TTD"]},
    {"effective": "2026-01-20", "added": ["WMT"], "removed": ["AZN"]},
    {"effective": "2026-04-20", "added": ["SNDK"], "removed": ["TEAM"]},
]


def build_spans() -> List[Tuple[str, str, str]]:
    """Walk the changelog forward, returning (ticker, start, end) tuples.

    ``end == ""`` means the ticker is still a constituent at the end of
    the changelog window. Tickers that left before the changelog ends
    get a concrete end date.
    """
    changes_sorted = sorted(CHANGES, key=lambda c: c["effective"])

    active: Dict[str, str] = {}             # ticker -> open-span start
    closed: List[Tuple[str, str, str]] = [] # (ticker, start, end)

    for change in changes_sorted:
        date = change["effective"]
        for ticker in change.get("added", []):
            if ticker in active:
                # Already-active ticker re-added in the same record — close
                # the existing span first so we don't lose history.
                closed.append((ticker, active[ticker], date))
            active[ticker] = date
        for ticker in change.get("removed", []):
            start = active.pop(ticker, DEFAULT_HISTORY_START)
            closed.append((ticker, start, date))

    open_spans = [(t, s, "") for t, s in active.items()]

    # Reconcile against the canonical current list.
    open_set = {t for t, _, _ in open_spans}
    current_set = set(CURRENT_NASDAQ100)

    missing_from_open = current_set - open_set
    for ticker in sorted(missing_from_open):
        # Currently a member but never appeared in the changelog window:
        # they joined before our data starts.
        open_spans.append((ticker, DEFAULT_HISTORY_START, ""))

    # Anything we think is "active" but isn't in current_set means we
    # missed a remove event somewhere. Drop them from open_spans and
    # do *not* add to closed: we don't know the end date.
    extra_open = open_set - current_set
    if extra_open:
        sys.stderr.write(
            f"Note: {len(extra_open)} ticker(s) appear open but aren't in "
            f"CURRENT_NASDAQ100 — likely missing remove events:\n"
            f"  {sorted(extra_open)}\n"
            f"They are excluded from the output; add a 'removed' entry to "
            f"CHANGES to capture their end date.\n"
        )
        open_spans = [(t, s, e) for t, s, e in open_spans if t not in extra_open]

    all_spans = closed + open_spans
    # Stable sort: by ticker, then start_date.
    return sorted(all_spans, key=lambda r: (r[0], r[1]))


def write_csv(spans: List[Tuple[str, str, str]], path: str) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["ticker", "start_date", "end_date"])
        for ticker, start, end in spans:
            writer.writerow([ticker, start, end])


def main() -> int:
    spans = build_spans()
    write_csv(spans, MEMBERSHIP_CSV)
    n_total = len(spans)
    n_open = sum(1 for _, _, end in spans if not end)
    n_closed = n_total - n_open
    print(f"Wrote {MEMBERSHIP_CSV}")
    print(f"  {n_total} total spans  ({n_open} currently open, {n_closed} historical)")
    print(f"  current Nasdaq-100 from src/config.py has {len(CURRENT_NASDAQ100)} tickers")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
