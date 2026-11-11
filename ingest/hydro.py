"""SMHI HydroObs daily discharge (m3/s). Station 2357 = SE1/SE2, 2213 = SE3/SE4.

corrected-archive is CSV ONLY (the API 406s on data.json) - parsed at ingest into
the OBS_SCHEMA jsonb shape the bronze model already reads (payload->'value').
"""
import re
import sys
from datetime import datetime, timezone

from ingest.common import fetch, get_conn, run_requests, upsert_raw

BASE = "https://opendata-download-hydroobs.smhi.se/api/version/1.0/parameter/1/station"
STATIONS = {"SE1": "2357", "SE2": "2357", "SE3": "2213", "SE4": "2213"}
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def daily_requests():
    stamp = datetime.now().strftime("%Y%m%d")
    return [{"url": f"{BASE}/{st}/period/latest-day/data.json",
             "input_file_name": f"smhi_hydro_daily/{zone}/discharge_latest_{stamp}.json"}
            for zone, st in STATIONS.items()]


def parse_hydro_csv(text):
    """Hydro corrected-archive CSV -> OBS_SCHEMA dict (station/parameter/period/value[])."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    di = next((i for i, ln in enumerate(lines) if ln.strip().lower().startswith("datum")), None)
    if di is None:
        return {"station": {}, "parameter": {}, "period": {}, "value": []}
    header = {}
    for i in range(di):
        head = [c.strip() for c in lines[i].split(";")]
        if head and head[0] in ("Stationsnamn", "Parameternamn") and i + 1 < di:
            val = [c.strip() for c in lines[i + 1].split(";")]
            for k, v in zip(head, val):
                if k:
                    header[k] = v
    values = []
    for ln in lines[di + 1:]:
        p = [c.strip() for c in ln.split(";")]
        if not p or not DATE_RE.match(p[0]):
            continue
        ts = datetime.strptime(p[0], "%Y-%m-%d").replace(tzinfo=timezone.utc)
        values.append({"date": int(ts.timestamp() * 1000),
                       "value": p[1] if len(p) > 1 else None,
                       "quality": p[2] if len(p) > 2 else None})
    return {
        "station": {"key": header.get("StationsId"), "name": header.get("Stationsnamn"),
                    "owner": None, "measuringStations": None},
        "parameter": {"key": "1", "name": header.get("Parameternamn"), "unit": header.get("Enhet")},
        "period": {"key": "corrected-archive"},
        "value": values,
    }


def historical_requests(conn, timeout=300):
    """corrected-archive CSV -> parsed OBS_SCHEMA jsonb (per-file replace)."""
    n = 0
    for zone, st in STATIONS.items():
        url = f"{BASE}/{st}/period/corrected-archive/data.csv"
        fname = f"smhi_hydro_historical/{zone}/discharge_historical.json"
        text = fetch(url, timeout=timeout)
        parsed = parse_hydro_csv(text)
        upsert_raw(conn, "raw_smhi_hydro", fname, "historical", parsed)
        n += 1
        print(f"  + {fname} ({len(parsed['value'])} rows)")
    return n


def run(historical=False):
    conn = get_conn()
    try:
        if historical:
            print(f"[hydro] stored {historical_requests(conn)} historical payload(s)")
        else:
            reqs = daily_requests()
            print(f"[hydro] storing {len(reqs)} payload(s)")
            print(f"[hydro] stored {run_requests(conn, 'raw_smhi_hydro', reqs, 'daily', pause=1.0)}")
    finally:
        conn.close()


if __name__ == "__main__":
    run(historical="--historical" in sys.argv)
