#!/usr/bin/env python3
"""Add the ML Forecast tab (spot + total bill forecast) to an existing dashboard.

Appends to dashboard id 9 (or $DASHBOARD_ID) IN PLACE, preserving existing tabs/cards.

Tab panels:
  KPI  Next-Day Spot / Next-Day Bill / Next-Week Bill / Next-Month Bill
  P12  Spot price forecast (actual + p50 + p10-p90 band)
  P13  Total bill forecast (actual + p50 + p10-p90 band)
  P14  Spot forecast by horizon & zone
  P15  Bill forecast by horizon & zone

Run:
    export METABASE_API_KEY="..."
    python metabase/add_forecast_tab.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from build_dashboard import find_db, auth_headers, req  # noqa: E402

BASE = os.environ.get("METABASE_URL", "http://localhost:3000").rstrip("/")
DID = int(os.environ.get("DASHBOARD_ID", "9"))
TAB = "ML Forecast"

ZONE_TAG = {"zone": {"id": "zone", "name": "zone", "display-name": "zone", "type": "text"}}
FILT = "\n  [[AND zone = {{zone}}]]"


def _horizon_sql(metric, alias, extra_select=""):
    return f"""SELECT CASE horizon WHEN 'next-day' THEN '1. Next day' WHEN 'next-week' THEN '2. Next week'
                    WHEN 'next-month' THEN '3. Next month' END AS horizon,
       zone, {extra_select}round({metric}::numeric, 3) AS {alias}
FROM gold.price_forecast_summary WHERE 1=1{FILT}
ORDER BY 1, 2"""


FORECAST = [
    # ---------------- KPI strip: headline forecasts ----------------
    {"name": "KPI Next-Day Spot Forecast", "display": "scalar", "row": 0, "col": 0, "size_x": 6, "size_y": 3,
     "sql": f"""SELECT round(avg(spot_sek_kwh)::numeric, 3) AS "Next-Day Spot Forecast"
FROM gold.price_forecast_summary WHERE horizon = 'next-day'{FILT}""",
     "viz": {}},
    {"name": "KPI Next-Day Bill Forecast", "display": "scalar", "row": 0, "col": 6, "size_x": 6, "size_y": 3,
     "sql": f"""SELECT round(avg(total_bill_sek_kwh)::numeric, 3) AS "Next-Day Bill Forecast"
FROM gold.price_forecast_summary WHERE horizon = 'next-day'{FILT}""",
     "viz": {}},
    {"name": "KPI Next-Week Bill Forecast", "display": "scalar", "row": 0, "col": 12, "size_x": 6, "size_y": 3,
     "sql": f"""SELECT round(avg(total_bill_sek_kwh)::numeric, 3) AS "Next-Week Bill Forecast"
FROM gold.price_forecast_summary WHERE horizon = 'next-week'{FILT}""",
     "viz": {}},
    {"name": "KPI Next-Month Bill Forecast", "display": "scalar", "row": 0, "col": 18, "size_x": 6, "size_y": 3,
     "sql": f"""SELECT round(avg(total_bill_sek_kwh)::numeric, 3) AS "Next-Month Bill Forecast"
FROM gold.price_forecast_summary WHERE horizon = 'next-month'{FILT}""",
     "viz": {}},

    # ---------------- forecast curves (the core ask) ----------------
    {"name": "P12 Spot price forecast", "display": "line", "row": 3, "col": 0, "size_x": 12, "size_y": 8,
     "sql": f"""SELECT target_date,
  round(avg(actual_sek_kwh)::numeric, 4)   AS actual_sek_kwh,
  round(avg(spot_sek_kwh)::numeric, 4)     AS spot_p50_sek_kwh,
  round(avg(spot_p10_sek_kwh)::numeric, 4) AS spot_p10_sek_kwh,
  round(avg(spot_p90_sek_kwh)::numeric, 4) AS spot_p90_sek_kwh
FROM gold.price_forecast WHERE 1=1{FILT}
GROUP BY target_date ORDER BY target_date""",
     "viz": {"graph.dimensions": ["target_date"],
             "graph.metrics": ["actual_sek_kwh", "spot_p50_sek_kwh", "spot_p10_sek_kwh", "spot_p90_sek_kwh"],
             "series_settings": {"spot_p10_sek_kwh": {"color": "#C7C7C7"},
                                 "spot_p90_sek_kwh": {"color": "#C7C7C7"}}}},

    {"name": "P13 Total bill forecast", "display": "line", "row": 3, "col": 12, "size_x": 12, "size_y": 8,
     "sql": f"""SELECT target_date,
  round(avg((actual_sek_kwh + energy_tax_sek_kwh + grid_fee_sek_kwh) * 1.25)::numeric, 4) AS actual_bill_sek_kwh,
  round(avg(total_bill_sek_kwh)::numeric, 4)     AS bill_p50_sek_kwh,
  round(avg(total_bill_p10_sek_kwh)::numeric, 4) AS bill_p10_sek_kwh,
  round(avg(total_bill_p90_sek_kwh)::numeric, 4) AS bill_p90_sek_kwh
FROM gold.price_forecast WHERE 1=1{FILT}
GROUP BY target_date ORDER BY target_date""",
     "viz": {"graph.dimensions": ["target_date"],
             "graph.metrics": ["actual_bill_sek_kwh", "bill_p50_sek_kwh", "bill_p10_sek_kwh", "bill_p90_sek_kwh"],
             "series_settings": {"bill_p10_sek_kwh": {"color": "#C7C7C7"},
                                 "bill_p90_sek_kwh": {"color": "#C7C7C7"}}}},

    # ---------------- horizon summaries (spot + bill by zone) ----------------
    {"name": "P14 Spot forecast by horizon", "display": "bar", "row": 11, "col": 0, "size_x": 12, "size_y": 7,
     "sql": _horizon_sql("spot_sek_kwh", "spot_sek_kwh"),
     "viz": {"graph.dimensions": ["horizon", "zone"], "graph.metrics": ["spot_sek_kwh"]}},

    {"name": "P15 Bill forecast by horizon", "display": "bar", "row": 11, "col": 12, "size_x": 12, "size_y": 7,
     "sql": _horizon_sql("total_bill_sek_kwh", "bill_sek_kwh"),
     "viz": {"graph.dimensions": ["horizon", "zone"], "graph.metrics": ["bill_sek_kwh"]}},
]


def rt(dc):
    """Round-trip the writable fields of an existing dashcard (keep layout + filter wiring)."""
    out = {
        "id": dc["id"],
        "card_id": dc.get("card_id") or (dc.get("card") or {}).get("id"),
        "dashboard_tab_id": dc.get("dashboard_tab_id"),
        "row": dc.get("row", 0), "col": dc.get("col", 0),
        "size_x": dc.get("size_x", 6), "size_y": dc.get("size_y", 4),
        "parameter_mappings": dc.get("parameter_mappings", []),
        "visualization_settings": dc.get("visualization_settings", {}),
        "series": dc.get("series", []),
        "inline_parameters": dc.get("inline_parameters", []),
    }
    if dc.get("action_id") is not None:
        out["action_id"] = dc["action_id"]
    return out


def main():
    h = auth_headers()
    db_id = find_db(h)
    print(f"[ok] database id = {db_id}")

    # 1. create the forecast questions
    fids = []
    for c in FORECAST:
        r = req("POST", "/api/card", {
            "name": c["name"], "display": c["display"],
            "dataset_query": {"type": "native", "database": db_id,
                              "native": {"query": c["sql"], "template-tags": ZONE_TAG}},
            "visualization_settings": c["viz"],
            "collection_id": None, "description": "swedish-el ML forecast panel",
        }, h)
        fids.append(r["id"])
        print(f"[ok] question: {c['name']} (id={r['id']})")

    # 2. snapshot existing dashboard
    d = req("GET", f"/api/dashboard/{DID}", headers=h)
    ex_tabs, ex_cards, params = d.get("tabs", []), d.get("dashcards", []), d.get("parameters", [])
    print(f"[ok] dashboard {DID}: {len(ex_tabs)} tabs, {len(ex_cards)} cards, {len(params)} filters")

    # 3. add the ML Forecast tab (empty first) while preserving existing cards.
    #    Note: PUT only processes `tabs` when `dashcards` is present; re-sending the
    #    existing cards (by real id) keeps them intact.
    tabs_step1 = [{"id": t["id"], "name": t["name"]} for t in ex_tabs] + [{"id": -1, "name": TAB}]
    req("PUT", f"/api/dashboard/{DID}",
        {"tabs": tabs_step1, "dashcards": [rt(c) for c in ex_cards],
         "parameters": params, "auto_apply_filters": True}, h)
    d2 = req("GET", f"/api/dashboard/{DID}", headers=h)
    tab_id = {t["name"]: t["id"] for t in d2.get("tabs", [])}[TAB]
    ex_cards2 = d2.get("dashcards", [])
    if len(ex_cards2) != len(ex_cards):
        sys.exit(f"[abort] existing cards changed {len(ex_cards)} -> {len(ex_cards2)}; refusing to continue")
    print(f"[ok] tab '{TAB}' id = {tab_id}; {len(ex_cards2)} existing cards preserved")

    # 4. attach forecast cards to the new tab (two-step: negative tab ids fail in one shot)
    dashcards = [rt(c) for c in ex_cards2]
    neg = -1
    for c, cid in zip(FORECAST, fids):
        dashcards.append({
            "id": neg, "card_id": cid, "dashboard_tab_id": tab_id,
            "row": c["row"], "col": c["col"], "size_x": c["size_x"], "size_y": c["size_y"],
            "parameter_mappings": [{"parameter_id": "zone", "card_id": cid,
                                    "target": ["variable", ["template-tag", "zone"]]}],
        })
        neg -= 1
    req("PUT", f"/api/dashboard/{DID}",
        {"tabs": [{"id": t["id"], "name": t["name"]} for t in d2.get("tabs", [])],
         "dashcards": dashcards, "parameters": params, "auto_apply_filters": True}, h)
    print(f"[ok] wired: {len(FORECAST)} forecast cards onto tab '{TAB}'")

    # 5. verify
    d3 = req("GET", f"/api/dashboard/{DID}", headers=h)
    per_tab = {}
    for dc in d3.get("dashcards", []):
        per_tab[dc.get("dashboard_tab_id")] = per_tab.get(dc.get("dashboard_tab_id"), 0) + 1
    print(f"[ok] dashboard {DID} now: {len(d3.get('tabs', []))} tabs, {len(d3.get('dashcards', []))} cards")
    for t in d3.get("tabs", []):
        print(f"      tab '{t['name']}' (id={t['id']}): {per_tab.get(t['id'], 0)} cards")
    print(f"\n[done] open: {BASE}/dashboard/{DID}")


if __name__ == "__main__":
    main()
