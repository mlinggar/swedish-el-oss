"""SMHI MetObs temperature (1), wind (4), precipitation (7) per zone.

Three source formats (silver priority: archive_csv > gap_json > latest_day_json):
  latest_day_json -> period/latest-day        (last 24h, JSON)
  gap_json        -> period/latest-months     (rolling ~4 months, JSON)
  archive_csv     -> period/corrected-archive (full history to 1990, CSV ONLY
                       — the API 406s on the JSON form, so we use data.csv)
"""
import re
import sys
from datetime import date

from ingest.common import fetch, get_conn, run_requests, upsert_raw

BASE = "https://opendata-download-metobs.smhi.se/api/version/1.0/parameter"
PARAMS = {1: "temp", 4: "wind", 7: "precip"}
STATIONS = {"SE1": 162860, "SE2": 127310, "SE3": 98230, "SE4": 52350}
WIND_STATIONS = {"SE1": 162860, "SE2": 127310, "SE3": 97200, "SE4": 52350}
PRECIP_ZONES = {"SE1", "SE3", "SE4"}  # SE2 has no precipitation station
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


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
    """SMHI corrected-archive CSV -> {header:{...}, rows:[{obs_date,obs_time,value,quality}]}."""
    lines = [ln for ln in text.splitlines() if ln.strip()]
    di = next((i for i, ln in enumerate(lines) if ln.strip().lower().startswith("datum")), None)
    if di is None:
        return {"_raw_text": text, "rows": []}
    header = {}
    for i in range(di):
        head = [c.strip() for c in lines[i].split(";")]
        if head and head[0] in ("Stationsnamn", "Parameternamn") and i + 1 < di:
            val = [c.strip() for c in lines[i + 1].split(";")]
            for k, v in zip(head, val):
                if k:
                    header[k] = v
    rows = []
    for ln in lines[di + 1:]:
        p = [c.strip() for c in ln.split(";")]
        if not p or not DATE_RE.match(p[0]):
            continue
        rows.append({"obs_date": p[0],
                     "obs_time": p[1] if len(p) > 1 else None,
                     "value": p[2] if len(p) > 2 else None,
                     "quality": p[3] if len(p) > 3 else None})
    return {"header": header, "rows": rows}


def archive_requests(conn, timeout=300):
    """Full history via corrected-archive CSV (large responses). JSON form 406s."""
    n = 0
    for zone in STATIONS:
        for param, name in PARAMS.items():
            if param == 7 and zone not in PRECIP_ZONES:
                continue
            url = f"{BASE}/{param}/station/{_st(param, zone)}/period/corrected-archive/data.csv"
            fname = f"weather/metobs_historical_archive/{zone}/archive_{name}.csv"
            text = fetch(url, timeout=timeout)
            upsert_raw(conn, "raw_smhi_metobs", fname, "historical", parse_smhi_csv(text))
            n += 1
            print(f"  + {fname}")
    return n


def run(historical=False):
    conn = get_conn()
    try:
        if historical:
            n = archive_requests(conn)
            n += run_requests(conn, "raw_smhi_metobs", gap_requests(), "historical", pause=1.0)
            print(f"[metobs] stored {n} historical payload(s) (archive CSV + gap)")
        else:
            reqs = daily_requests() + gap_requests()
            print(f"[metobs] storing {len(reqs)} daily payload(s) (latest-day + gap)")
            print(f"[metobs] stored {run_requests(conn, 'raw_smhi_metobs', reqs, 'daily')}")
    finally:
        conn.close()


if __name__ == "__main__":
    run(historical="--historical" in sys.argv)
