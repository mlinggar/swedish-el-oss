"""SMHI HydroObs daily discharge (m3/s). Station 2357 serves SE1/SE2, 2213 serves SE3/SE4."""
import sys
from datetime import date

from ingest.common import get_conn, run_requests

BASE = "https://opendata-download-hydroobs.smhi.se/api/version/1.0/parameter/1/station"
STATIONS = {"SE1": "2357", "SE2": "2357", "SE3": "2213", "SE4": "2213"}


def daily_requests():
    stamp = date.today().strftime("%Y%m%d")
    return [{"url": f"{BASE}/{st}/period/latest-day/data.json",
             "input_file_name": f"smhi_hydro_daily/{zone}/discharge_latest_{stamp}.json"}
            for zone, st in STATIONS.items()]


def historical_requests():
    return [{"url": f"{BASE}/{st}/period/corrected-archive/data.json",
             "input_file_name": f"smhi_hydro_historical/{zone}/discharge_historical.json"}
            for zone, st in STATIONS.items()]


def run(historical=False):
    conn = get_conn()
    try:
        tier = "historical" if historical else "daily"
        reqs = historical_requests() if historical else daily_requests()
        print(f"[hydro] storing {len(reqs)} payload(s)")
        print(f"[hydro] stored {run_requests(conn, 'raw_smhi_hydro', reqs, tier, pause=1.0)}")
    finally:
        conn.close()


if __name__ == "__main__":
    run(historical="--historical" in sys.argv)
