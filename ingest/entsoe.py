"""ENTSO-E: day-ahead price (A44), load forecast (A65), actual generation (A75)."""
import os
import sys
from datetime import date, timedelta

from ingest.common import get_conn, load_env, run_requests

BASE = "https://web-api.tp.entsoe.eu/api"
ZONES = {"SE1": "10Y1001A1001A44P", "SE2": "10Y1001A1001A45N",
         "SE3": "10Y1001A1001A46L", "SE4": "10Y1001A1001A47J"}
HISTORY_START = date(2022, 1, 1)


def _price(t, dom, ps, pe):
    return f"{BASE}?securityToken={t}&documentType=A44&in_Domain={dom}&out_Domain={dom}&periodStart={ps}&periodEnd={pe}"


def _load(t, dom, ps, pe):
    return f"{BASE}?securityToken={t}&documentType=A65&processType=A01&outBiddingZone_Domain={dom}&periodStart={ps}&periodEnd={pe}"


def _gen(t, dom, ps, pe):
    return f"{BASE}?securityToken={t}&documentType=A75&processType=A16&in_Domain={dom}&out_Domain={dom}&periodStart={ps}&periodEnd={pe}"


def _window(start, end):
    return start.strftime("%Y%m%d") + "0000", (end + timedelta(days=1)).strftime("%Y%m%d") + "2300"


def daily_requests(t):
    today = date.today()
    ps, pe = _window(today, today)
    gps, gpe = _window(today - timedelta(days=2), today - timedelta(days=1))
    stamp = today.strftime("%Y%m%d")
    out = []
    for zone, dom in ZONES.items():
        out.append({"url": _price(t, dom, ps, pe),
                    "input_file_name": f"entsoe_daily/{zone}/day_ahead_price_{stamp}.json"})
        out.append({"url": _load(t, dom, ps, pe),
                    "input_file_name": f"entsoe_daily/{zone}/load_forecast_{stamp}.json"})
        out.append({"url": _gen(t, dom, gps, gpe),
                    "input_file_name": f"entsoe_daily/{zone}/actual_generation_{stamp}.json"})
    return out


def historical_requests(t, start=HISTORY_START):
    out, cursor = [], start
    today = date.today()
    while cursor <= today:
        nxt = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
        end = min(nxt - timedelta(days=1), today)
        ps, pe = _window(cursor, end)
        stamp = cursor.strftime("%Y%m")
        for zone, dom in ZONES.items():
            out.append({"url": _price(t, dom, ps, pe),
                        "input_file_name": f"entsoe_historical/{zone}/day_ahead_price_history_{stamp}.json"})
            out.append({"url": _load(t, dom, ps, pe),
                        "input_file_name": f"entsoe_historical/{zone}/load_forecast_history_{stamp}.json"})
            out.append({"url": _gen(t, dom, ps, pe),
                        "input_file_name": f"entsoe_historical/{zone}/actual_generation_history_{stamp}.json"})
        cursor = nxt
    return out


def run(historical=False):
    load_env()
    token = os.environ.get("ENTSOE_TOKEN")
    if not token:
        raise SystemExit("ENTSOE_TOKEN missing from .env")
    conn = get_conn()
    try:
        tier = "historical" if historical else "daily"
        reqs = historical_requests(token) if historical else daily_requests(token)
        print(f"[entsoe] storing {len(reqs)} payload(s)")
        print(f"[entsoe] stored {run_requests(conn, 'raw_entsoe', reqs, tier, pause=1.0)}")
    finally:
        conn.close()


if __name__ == "__main__":
    run(historical="--historical" in sys.argv)
