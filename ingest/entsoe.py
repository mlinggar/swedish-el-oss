"""ENTSO-E: day-ahead price (A44), load forecast (A65), actual generation (A75).

The API returns XML, parsed at ingest into flat rows (non-JSON payloads are
pre-parsed in Python). Two document types:
  A44 price          -> Publication_MarketDocument
  A65 load / A75 gen -> GL_MarketDocument
parse_entsoe_xml strips namespaces so both parse the same way. The bronze model
unnests rows and derives point_ts_utc.
"""
import os
import sys
import xml.etree.ElementTree as ET
from datetime import date, timedelta

from ingest.common import fetch, get_conn, load_env, upsert_raw

BASE = "https://web-api.tp.entsoe.eu/api"
ZONES = {"SE1": "10Y1001A1001A44P", "SE2": "10Y1001A1001A45N",
         "SE3": "10Y1001A1001A46L", "SE4": "10Y1001A1001A47J"}
CODES = {"A44": "ENERGY_PRICES",
         "A65": "DAY_AHEAD_TOTAL_LOAD_FORECAST_R3",
         "A75": "AGGREGATED_GENERATION_PER_TYPE_R3"}
HISTORY_START = date(2022, 1, 1)


def parse_entsoe_xml(text):
    root = ET.fromstring(text)
    for elem in root.iter():
        if '}' in elem.tag:
            elem.tag = elem.tag.split('}', 1)[1]
        elem.attrib = {k.split('}', 1)[-1]: v for k, v in elem.attrib.items()}
    doc_type = root.findtext('type') or ''
    code = CODES.get(doc_type, 'unknown')
    rows = []
    for ts in root.iter('TimeSeries'):
        biz = {}
        area = (ts.findtext('in_Domain.mRID') or ts.findtext('out_Domain.mRID')
                or ts.findtext('outBiddingZone_Domain.mRID')
                or ts.findtext('inBiddingZone_Domain.mRID'))
        if area:
            biz['AREA'] = area
        psr = ts.findtext('PSRType/psrType')
        if psr:
            biz['PRODUCTION_TYPE'] = psr
        contract = ts.findtext('contract_MarketAgreement.type')
        if contract:
            biz['CONTRACT_TYPE'] = contract
        inst = {}
        cur = ts.findtext('currency_Unit.name')
        if cur:
            inst['CURRENCY'] = cur
        unit = (ts.findtext('price_Measure_Unit.name')
                or ts.findtext('quantity_Measure_Unit.name')
                or ts.findtext('quantity_Unit.name'))
        if unit:
            inst['MEASURE_UNIT'] = unit
        for period in ts.iter('Period'):
            pfrom = period.findtext('timeInterval/start')
            pto = period.findtext('timeInterval/end')
            resolution = period.findtext('resolution') or ''
            for pt in period.iter('Point'):
                pos = pt.findtext('position')
                price = pt.findtext('price.amount')
                qty = pt.findtext('quantity')
                rows.append({'data_item_code': code, 'business_dim': biz, 'instance_attr': inst,
                             'period_from': pfrom, 'period_to': pto, 'resolution': resolution,
                             'point_index': int(pos) if pos else None,
                             'value_1': price if price is not None else qty, 'value_2': None})
    return {'rows': rows}


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
        print(f"[entsoe] fetching + parsing {len(reqs)} request(s)")
        n = 0
        for r in reqs:
            text = fetch(r["url"])
            upsert_raw(conn, "raw_entsoe", r["input_file_name"], tier, parse_entsoe_xml(text))
            n += 1
            print(f"  + {r['input_file_name']}")
        print(f"[entsoe] stored {n} payload(s)")
    finally:
        conn.close()


if __name__ == "__main__":
    run(historical="--historical" in sys.argv)
