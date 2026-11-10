"""SCB consumer electricity prices (PxWeb POST, full table per request)."""
import sys
from datetime import date

from ingest.common import get_conn, run_requests

BASE = "https://api.scb.se/OV0104/v1/doris/sv/ssd/START/EN/EN0301/EN0301A"
TABLES = {"hushall": "SSDHalvarElHus", "elnat": "SSDArElnatspris",
          "elhandel": "SSDManadElhandelpris"}
BODY = '{"query":[],"response":{"format":"json"}}'
HEADERS = {"Content-Type": "application/json"}


def daily_requests():
    stamp = date.today().strftime("%Y%m")
    return [{"url": f"{BASE}/{path}", "method": "POST", "body": BODY, "headers": HEADERS,
             "input_file_name": f"scb/{name}/{name}_{stamp}.json"}
            for name, path in TABLES.items()]


def historical_requests():
    stamp = date.today().strftime("%Y%m%d")
    return [{"url": f"{BASE}/{path}", "method": "POST", "body": BODY, "headers": HEADERS,
             "input_file_name": f"scb_historical/{name}/{name}_history_{stamp}.json"}
            for name, path in TABLES.items()]


def run(historical=False):
    conn = get_conn()
    try:
        tier = "historical" if historical else "daily"
        reqs = historical_requests() if historical else daily_requests()
        print(f"[scb] storing {len(reqs)} payload(s)")
        print(f"[scb] stored {run_requests(conn, 'raw_scb', reqs, tier, pause=1.0)}")
    finally:
        conn.close()


if __name__ == "__main__":
    run(historical="--historical" in sys.argv)
