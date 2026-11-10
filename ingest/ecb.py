"""ECB FX rates (EUR base, SEK + USD daily)."""
import sys
from datetime import date

from ingest.common import get_conn, run_requests

EXR = "https://data-api.ecb.europa.eu/service/data/EXR/D.SEK+USD.EUR.SP00.A"
HISTORY_START = "2022-01-01"


def daily_requests(today):
    return [{"url": f"{EXR}?lastNObservations=1&format=jsondata",
             "input_file_name": f"ecb_daily/FX/ecb_fx_{today}.json"}]


def historical_requests():
    end = date.today().isoformat()
    return [{"url": f"{EXR}?startPeriod={HISTORY_START}&endPeriod={end}&format=jsondata",
             "input_file_name": f"ecb_historical/FX/ecb_fx_history_{end}.json"}]


def run(historical=False):
    conn = get_conn()
    try:
        tier = "historical" if historical else "daily"
        reqs = historical_requests() if historical else daily_requests(date.today().strftime("%Y%m%d"))
        print(f"[ecb] storing {len(reqs)} payload(s)")
        print(f"[ecb] stored {run_requests(conn, 'raw_ecb', reqs, tier)}")
    finally:
        conn.close()


if __name__ == "__main__":
    run(historical="--historical" in sys.argv)
