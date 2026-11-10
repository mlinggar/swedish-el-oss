"""EIA Henry Hub natural gas spot price (USD/MMBtu)."""
import os
import sys
from datetime import date, timedelta

from ingest.common import get_conn, load_env, run_requests

BASE = "https://api.eia.gov/v2/natural-gas/pri/fut/data/"
HISTORY_START = date(2022, 1, 1)


def _url(key, start, end):
    return (f"{BASE}?api_key={key}&frequency=daily&data[0]=value"
            f"&start={start.isoformat()}&end={end.isoformat()}")


def daily_requests(key):
    today = date.today()
    return [{"url": _url(key, today - timedelta(days=7), today),
             "input_file_name": f"eia_daily/GAS/eia_gas_{today.strftime('%Y%m%d')}.json"}]


def historical_requests(key):
    out, year = [], HISTORY_START.year
    today = date.today()
    while year <= today.year:
        end = min(date(year, 12, 31), today)
        out.append({"url": _url(key, date(year, 1, 1), end),
                    "input_file_name": f"eia_historical/GAS/eia_gas_history_{year}.json"})
        year += 1
    return out


def run(historical=False):
    load_env()
    key = os.environ.get("EIA_API_KEY")
    if not key:
        raise SystemExit("EIA_API_KEY missing from .env")
    conn = get_conn()
    try:
        tier = "historical" if historical else "daily"
        reqs = historical_requests(key) if historical else daily_requests(key)
        print(f"[eia] storing {len(reqs)} payload(s)")
        print(f"[eia] stored {run_requests(conn, 'raw_eia', reqs, tier)}")
    finally:
        conn.close()


if __name__ == "__main__":
    run(historical="--historical" in sys.argv)
