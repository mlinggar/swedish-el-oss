"""SMHI snow1g point forecasts (temperature/wind/precip per bidding zone)."""
import sys
from datetime import date

from ingest.common import get_conn, run_requests

BASE = "https://opendata-download-metfcst.smhi.se/api/category/snow1g/version/1/geotype/point"
POINTS = {"SE1": (22.124, 65.543), "SE2": (17.443, 62.532),
          "SE3": (18.0686, 59.3293), "SE4": (13.0038, 55.6049)}


def daily_requests():
    stamp = date.today().strftime("%Y%m%d")
    return [{"url": f"{BASE}/lon/{lon}/lat/{lat}/data.json",
             "input_file_name": f"smhi_daily/{zone}/se{zone[2]}_forecast_{stamp}.json"}
            for zone, (lon, lat) in POINTS.items()]


def run(historical=False):
    if historical:
        raise SystemExit("forecast has no history (it is a forecast) - skip --historical")
    conn = get_conn()
    try:
        reqs = daily_requests()
        print(f"[forecast] storing {len(reqs)} payload(s)")
        print(f"[forecast] stored {run_requests(conn, 'raw_smhi_forecast', reqs, 'daily')}")
    finally:
        conn.close()


if __name__ == "__main__":
    run(historical="--historical" in sys.argv)
