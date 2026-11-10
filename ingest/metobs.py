"""SMHI MetObs temperature (1), wind (4), precipitation (7) per zone.

Three source formats, matching the silver source_format contract:
  latest_day_json -> period/latest-day
  gap_json        -> period/latest-months   (fills gaps back through history)
  archive_csv     -> period/corrected-archive (QC'd CSV, pre-parsed to rows here)
"""
import sys
from datetime import date

from ingest.common import get_conn, run_requests, upsert_raw, fetch

BASE = "https://opendata-download-metobs.smhi.se/api/version/1.0/parameter"
PARAMS = {1: "temp", 4: "wind", 7: "precip"}
STATIONS = {"SE1": 162860, "SE2": 127310, "SE3": 98230, "SE4": 52350}
WIND_STATIONS = {"SE1": 162860, "SE2": 127310, "SE3": 97200, "SE4": 52350}
PRECIP_ZONES = {"SE1", "SE3", "SE4"}  # SE2 has no precipitation station


def _st(param, zone):
    return WIND_STATIONS[zone] if param == 4 else STATIONS[zone]


def daily_requests():
    stamp = date.today().strftime("%Y%m%d")
    out = []
    for zone in STATIONS:
        for param, name in PARAMS.items():
            if param == 7 and zone not in PRECIP_ZONES:
                continue
            out.append({"url": f"{BASE}/{param}/station/{_st(param, zone)}/period/latest-day/data.json",
                        "input_file_name": f"smhi_daily/{zone}/{name}_latest_day_{stamp}.json"})
    return out


def gap_requests():
    out = []
    for zone in STATIONS:
        for param, name in PARAMS.items():
            if param == 7 and zone not in PRECIP_ZONES:
                continue
            out.append({"url": f"{BASE}/{param}/station/{_st(param, zone)}/period/latest-months/data.json",
                        "input_file_name": f"weather/metobs_historical_archive/{zone}/gap_{name}.json"})
    return out


def parse_smhi_csv(text):
    """Split an SMHI corrected-archive CSV into header metadata + data rows."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    split = next((i for i, ln in enumerate(lines) if ln.lower().startswith("datum")), None)
    if split is None:
        return {"_raw_text": text, "rows": []}
    header = {}
    for ln in lines[:split]:
        if ";" in ln:
            k, v = ln.split(";", 1)
            header[k.strip()] = v.strip()
    cols = [c.strip() for c in lines[split].split(";")]
    rows = [dict(zip(cols, ln.split(";"))) for ln in lines[split + 1:]]
    return {"header": header, "columns": cols, "rows": rows}


def archive_requests(conn):
    out = []
    for zone in STATIONS:
        for param, name in PARAMS.items():
            if param == 7 and zone not in PRECIP_ZONES:
                continue
            url = f"{BASE}/{param}/station/{_st(param, zone)}/period/corrected-archive/data.json"
            text = fetch(url)
            fname = f"weather/metobs_historical_archive/{zone}/archive_{name}.csv"
            upsert_raw(conn, "raw_smhi_metobs", fname, "historical", parse_smhi_csv(text))
            out.append(fname)
            print(f"  + {fname}")
    return out


def run(historical=False):
    conn = get_conn()
    try:
        if historical:
            print(f"[metobs] parsing archive CSVs")
            n = len(archive_requests(conn))
            print(f"[metobs] stored {n} archive payload(s)")
        else:
            reqs = daily_requests() + gap_requests()
            print(f"[metobs] storing {len(reqs)} payload(s)")
            print(f"[metobs] stored {run_requests(conn, 'raw_smhi_metobs', reqs, 'daily')}")
    finally:
        conn.close()


if __name__ == "__main__":
    run(historical="--historical" in sys.argv)
