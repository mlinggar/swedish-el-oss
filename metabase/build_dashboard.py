#!/usr/bin/env python3
"""Build the swedish-el Metabase dashboard: ONE dashboard, THREE tabs.

Tabs:
  1. Spot Price Analytics    - P1,P2,P3,P4,P7
  2. Spot vs Driver          - P5,P6
  3. Customer Electricity Bill - P8,P9,P10,P11 + 4 KPI scalars

Auth (choose one):
    export METABASE_API_KEY="..."
    export METABASE_USER="..." METABASE_PASSWORD="..."

Run:
    python metabase/build_dashboard.py
"""
import json
import os
import sys
import urllib.error
import urllib.request

BASE = os.environ.get("METABASE_URL", "http://localhost:3000").rstrip("/")


def req(method, path, body=None, headers=None):
    url = BASE + path
    h = {"Content-Type": "application/json"}
    if headers:
        h.update(headers)
    data = json.dumps(body).encode("utf-8") if body is not None else None
    r = urllib.request.Request(url, data=data, headers=h, method=method)
    try:
        with urllib.request.urlopen(r, timeout=120) as resp:
            raw = resp.read()
            return json.loads(raw) if raw else {}
    except urllib.error.HTTPError as e:
        sys.exit(f"[error] {method} {path} -> HTTP {e.code}\n"
                 + e.read().decode("utf-8", "replace")[:1500])


def auth_headers():
    key = os.environ.get("METABASE_API_KEY")
    if key:
        return {"X-Api-Key": key}
    u, p = os.environ.get("METABASE_USER"), os.environ.get("METABASE_PASSWORD")
    if u and p:
        s = req("POST", "/api/session", {"username": u, "password": p})
        return {"X-Metabase-Session": s["id"]}
    sys.exit("Set METABASE_API_KEY or METABASE_USER + METABASE_PASSWORD.")


def find_db(headers):
    data = req("GET", "/api/database", headers=headers)
    dbs = data.get("data", []) if isinstance(data, dict) else data
    for d in dbs:
        if d.get("engine") == "postgres":
            return d["id"]
    sys.exit("No postgres Metabase DB found (connect swedish_el first).")


# ---------------------------------------------------------------- template tags
def tags(*names):
    t = {}
    for n in names:
        t[n] = {
            "id": n, "name": n,
            "display-name": {"year": "Year", "quarter": "Quarter", "month": "Month",
                             "zone": "zone_id", "driver": "driver"}[n],
            "type": "number" if n in ("year", "quarter", "month") else "text",
        }
    return t


YQM = """
  [[AND extract(year from date_local)    = {{year}}]]
  [[AND extract(quarter from date_local) = {{quarter}}]]
  [[AND extract(month from date_local)   = {{month}}]]
  [[AND zone_id = {{zone}}]]"""
YQMD = YQM + """
  [[AND driver_name = {{driver}}]]"""

TAG_YQMZ = ["year", "quarter", "month", "zone"]
TAG_YQMZD = ["year", "quarter", "month", "zone", "driver"]


# ---------------------------------------------------------------- panels
CARDS = [
    # ---------------- Tab 1: Spot Price Analytics ----------------
    {"name": "P1 Spot price line", "display": "line", "tab_name": "Spot Price Analytics",
     "tag_names": TAG_YQMZ, "row": 0, "col": 0, "size_x": 16, "size_y": 8,
     "sql": f"""SELECT date_local, zone_id AS zone,
       round(avg(price_sek_kwh_avg)::numeric, 4) AS spot_sek_kwh
FROM gold.fact_daily
WHERE 1=1 {YQM}
GROUP BY date_local, zone_id
ORDER BY date_local""",
     "viz": {"graph.dimensions": ["date_local", "zone"], "graph.metrics": ["spot_sek_kwh"]}},

    {"name": "P2 Avg spot by zone", "display": "bar", "tab_name": "Spot Price Analytics",
     "tag_names": TAG_YQMZ, "row": 0, "col": 16, "size_x": 8, "size_y": 8,
     "sql": f"""SELECT zone_id AS zone, round(avg(price_sek_kwh_avg)::numeric, 4) AS avg_spot_sek_kwh
FROM gold.fact_daily
WHERE 1=1 {YQM}
GROUP BY zone_id
ORDER BY avg_spot_sek_kwh DESC""",
     "viz": {"graph.dimensions": ["zone"], "graph.metrics": ["avg_spot_sek_kwh"]}},

    {"name": "P3 Peak vs off-peak", "display": "bar", "tab_name": "Spot Price Analytics",
     "tag_names": TAG_YQMZ, "row": 8, "col": 0, "size_x": 12, "size_y": 6,
     "sql": f"""SELECT date_local,
       round(avg(price_peak_avg_sek_kwh)::numeric, 4)    AS peak_sek_kwh,
       round(avg(price_offpeak_avg_sek_kwh)::numeric, 4) AS offpeak_sek_kwh,
       round(avg((price_peak_avg_sek_kwh - price_offpeak_avg_sek_kwh)
                 / nullif(price_offpeak_avg_sek_kwh, 0) * 100)::numeric, 2) AS peak_premium_pct
FROM gold.fact_daily
WHERE 1=1 {YQM}
GROUP BY date_local
ORDER BY date_local""",
     "viz": {"graph.dimensions": ["date_local"],
             "graph.metrics": ["peak_sek_kwh", "offpeak_sek_kwh", "peak_premium_pct"],
             "series_settings": {"peak_premium_pct": {"display": "line"}}}},

    {"name": "P4 Cheapest hour", "display": "bar", "tab_name": "Spot Price Analytics",
     "tag_names": TAG_YQMZ, "row": 8, "col": 12, "size_x": 12, "size_y": 6,
     "sql": f"""SELECT cheapest_hour_local AS hour_of_day, count(*) AS days
FROM gold.fact_daily
WHERE 1=1 {YQM}
GROUP BY cheapest_hour_local
ORDER BY cheapest_hour_local""",
     "viz": {"graph.dimensions": ["hour_of_day"], "graph.metrics": ["days"]}},

    {"name": "P7 Bill breakdown", "display": "bar", "tab_name": "Spot Price Analytics",
     "tag_names": TAG_YQMZ, "row": 14, "col": 0, "size_x": 24, "size_y": 6,
     "sql": f"""SELECT date_trunc('month', date_local)::date AS month, zone_id AS zone,
       round(avg(price_sek_kwh_avg)::numeric, 4)   AS spot_sek_kwh,
       round(avg(energy_tax_sek_kwh)::numeric, 4)  AS energy_tax_sek_kwh,
       round(avg(grid_fee_sek_kwh)::numeric, 4)    AS grid_fee_sek_kwh,
       round(avg(total_consumer_sek_kwh - price_sek_kwh_avg
                 - energy_tax_sek_kwh - grid_fee_sek_kwh)::numeric, 4) AS vat_sek_kwh,
       round(avg(total_consumer_sek_kwh)::numeric, 4) AS bill_sek_kwh
FROM gold.fact_daily
WHERE 1=1 {YQM}
GROUP BY 1, 2
ORDER BY 1, 2""",
     "viz": {"graph.dimensions": ["month", "zone"],
             "graph.metrics": ["spot_sek_kwh", "energy_tax_sek_kwh", "grid_fee_sek_kwh", "vat_sek_kwh"],
             "stackable.stack_type": "stacked"}},

    # ---------------- Tab 2: Spot vs Driver ----------------
    {"name": "P5 Spot vs Driver", "display": "line", "tab_name": "Spot vs Driver",
     "tag_names": TAG_YQMZD, "row": 0, "col": 0, "size_x": 24, "size_y": 8,
     "sql": f"""SELECT date_local,
       round(avg(spot_sek_kwh)::numeric, 4) AS spot_sek_kwh,
       round(avg(driver_value)::numeric, 4) AS driver_value
FROM gold.driver_daily
WHERE 1=1 {YQMD}
GROUP BY date_local
ORDER BY date_local""",
     "viz": {"graph.dimensions": ["date_local"],
             "graph.metrics": ["spot_sek_kwh", "driver_value"],
             "series_settings": {"driver_value": {"axis": "right"}}}},

    {"name": "P6 Spot vs Driver scatter", "display": "scatter", "tab_name": "Spot vs Driver",
     "tag_names": TAG_YQMZD, "row": 8, "col": 0, "size_x": 24, "size_y": 8,
     "sql": f"""SELECT round(driver_value::numeric, 4) AS driver_value,
       round(spot_sek_kwh::numeric, 4) AS spot_sek_kwh
FROM gold.driver_daily
WHERE 1=1 {YQMD}""",
     "viz": {"graph.dimensions": ["driver_value"], "graph.metrics": ["spot_sek_kwh"]}},

    # ---------------- Tab 3: Customer Electricity Bill ----------------
    {"name": "P8 Customer Daily Electricity Bill", "display": "line",
     "tab_name": "Customer Electricity Bill", "tag_names": TAG_YQMZ,
     "row": 0, "col": 0, "size_x": 14, "size_y": 8,
     "sql": f"""SELECT date_local, zone_id AS zone,
       round(avg(total_consumer_sek_kwh)::numeric, 4) AS bill_sek_kwh
FROM gold.fact_daily
WHERE 1=1 {YQM}
GROUP BY date_local, zone_id
ORDER BY date_local""",
     "viz": {"graph.dimensions": ["date_local", "zone"], "graph.metrics": ["bill_sek_kwh"]}},

    {"name": "KPI Latest Month Bill", "display": "scalar",
     "tab_name": "Customer Electricity Bill", "tag_names": TAG_YQMZ,
     "row": 0, "col": 14, "size_x": 5, "size_y": 3,
     "sql": f"""WITH m AS (
  SELECT date_trunc('month', date_local)::date AS mon, avg(total_consumer_sek_kwh) AS v
  FROM gold.fact_daily WHERE 1=1 {YQM} GROUP BY 1
)
SELECT round(v::numeric, 3) AS "Latest Month Bill" FROM m ORDER BY mon DESC LIMIT 1""",
     "viz": {}},

    {"name": "KPI Latest Month Hushall Price", "display": "scalar",
     "tab_name": "Customer Electricity Bill", "tag_names": ["year", "quarter", "month"],
     "row": 0, "col": 19, "size_x": 5, "size_y": 3,
     "sql": """SELECT round(natpris_med_elskatt_sek_kwh::numeric, 3) AS "Latest Month Hushall Price"
FROM silver.consumer_prices
WHERE table_name = 'hushall' AND customer_category = 'DA'
  [[AND extract(year from period_start)    = {{year}}]]
  [[AND extract(quarter from period_start) = {{quarter}}]]
  [[AND extract(month from period_start)   = {{month}}]]
ORDER BY period_start DESC LIMIT 1""",
     "viz": {}},

    {"name": "KPI Total Bill", "display": "scalar",
     "tab_name": "Customer Electricity Bill", "tag_names": TAG_YQMZ,
     "row": 3, "col": 14, "size_x": 5, "size_y": 3,
     "sql": f"""SELECT round(avg(total_consumer_sek_kwh)::numeric, 3) AS "Total Bill"
FROM gold.fact_daily
WHERE 1=1 {YQM}""",
     "viz": {}},

    {"name": "KPI Consumer Premium", "display": "scalar",
     "tab_name": "Customer Electricity Bill", "tag_names": TAG_YQMZ,
     "row": 3, "col": 19, "size_x": 5, "size_y": 3,
     "sql": f"""SELECT round((avg(total_consumer_sek_kwh)
       / nullif(avg(price_sek_kwh_avg), 0))::numeric, 3) AS "Consumer Premium"
FROM gold.fact_daily
WHERE 1=1 {YQM}""",
     "viz": {}},

    {"name": "P9 Bill by Zone", "display": "row", "tab_name": "Customer Electricity Bill",
     "tag_names": TAG_YQMZ, "row": 6, "col": 14, "size_x": 10, "size_y": 4,
     "sql": f"""SELECT zone_id AS zone, round(avg(total_consumer_sek_kwh)::numeric, 4) AS avg_bill_sek_kwh
FROM gold.fact_daily
WHERE 1=1 {YQM}
GROUP BY zone_id
ORDER BY avg_bill_sek_kwh DESC""",
     "viz": {"graph.dimensions": ["zone"], "graph.metrics": ["avg_bill_sek_kwh"]}},

    {"name": "P10 Distribution of Bill", "display": "bar",
     "tab_name": "Customer Electricity Bill", "tag_names": TAG_YQMZ,
     "row": 10, "col": 0, "size_x": 12, "size_y": 8,
     "sql": f"""SELECT date_trunc('month', date_local)::date AS month,
       round(avg(price_sek_kwh_avg)::numeric, 4)   AS spot_sek_kwh,
       round(avg(energy_tax_sek_kwh)::numeric, 4)  AS energy_tax_sek_kwh,
       round(avg(grid_fee_sek_kwh)::numeric, 4)    AS grid_fee_sek_kwh,
       round(avg(total_consumer_sek_kwh - price_sek_kwh_avg
                 - energy_tax_sek_kwh - grid_fee_sek_kwh)::numeric, 4) AS vat_sek_kwh
FROM gold.fact_daily
WHERE 1=1 {YQM}
GROUP BY 1
ORDER BY 1""",
     "viz": {"graph.dimensions": ["month"],
             "graph.metrics": ["spot_sek_kwh", "energy_tax_sek_kwh", "grid_fee_sek_kwh", "vat_sek_kwh"],
             "stackable.stack_type": "normalized"}},

    {"name": "P11 Bill vs Hushall Price", "display": "bar",
     "tab_name": "Customer Electricity Bill", "tag_names": TAG_YQMZ,
     "row": 10, "col": 12, "size_x": 12, "size_y": 8,
     "sql": f"""SELECT f.date_local,
       round(avg(f.total_consumer_sek_kwh)::numeric, 4)      AS customer_bill_sek_kwh,
       round(max(h.natpris_med_elskatt_sek_kwh)::numeric, 4) AS hushall_price_sek_kwh
FROM gold.fact_daily f
LEFT JOIN LATERAL (
  SELECT natpris_med_elskatt_sek_kwh
  FROM silver.consumer_prices
  WHERE table_name = 'hushall' AND customer_category = 'DA'
    AND period_start <= f.date_local
  ORDER BY period_start DESC LIMIT 1
) h ON true
WHERE 1=1 {YQM}
GROUP BY f.date_local
ORDER BY f.date_local""",
     "viz": {"graph.dimensions": ["date_local"],
             "graph.metrics": ["customer_bill_sek_kwh", "hushall_price_sek_kwh"],
             "series_settings": {"hushall_price_sek_kwh": {"display": "line"}}}},
]


PARAMS = [
    {"id": "year", "name": "Year", "type": "number", "sectionId": "number",
     "values_source_type": "static-list",
     "values_source_config": {"values": ["2022", "2023", "2024", "2025", "2026"]},
     "default": "2026"},
    {"id": "quarter", "name": "Quarter", "type": "number", "sectionId": "number",
     "values_source_type": "static-list",
     "values_source_config": {"values": ["1", "2", "3", "4"]}},
    {"id": "month", "name": "Month", "type": "number", "sectionId": "number",
     "values_source_type": "static-list",
     "values_source_config": {"values": [str(i) for i in range(1, 13)]}},
    {"id": "zone", "name": "zone_id", "type": "string/=", "sectionId": "text",
     "values_source_type": "static-list",
     "values_source_config": {"values": ["SE1", "SE2", "SE3", "SE4"]}},
    {"id": "driver", "name": "driver", "type": "string/=", "sectionId": "text",
     "values_source_type": "static-list",
     "values_source_config": {"values": [
         "Temp Avg °C", "Wind Avg m/s", "Precipitation mm",
         "Discharge m3/s", "Gas Price SEK/MMBtu"]}},
]

TAB_NAMES = ["Spot Price Analytics", "Spot vs Driver", "Customer Electricity Bill"]


def main():
    h = auth_headers()
    db_id = find_db(h)
    print(f"[ok] database id = {db_id}")

    # 1. create the 15 questions
    card_ids = {}
    for c in CARDS:
        payload = {
            "name": c["name"],
            "display": c["display"],
            "dataset_query": {
                "type": "native", "database": db_id,
                "native": {"query": c["sql"], "template-tags": tags(*c["tag_names"])},
            },
            "visualization_settings": c["viz"],
            "collection_id": None,
            "description": "swedish-el dashboard panel",
        }
        r = req("POST", "/api/card", payload, h)
        card_ids[c["name"]] = r["id"]
        print(f"[ok] question: {c['name']} (id={r['id']})")

    # 2. create the dashboard
    d = req("POST", "/api/dashboard",
            {"name": "Swedish EL - Prices, Drivers & Bill", "collection_id": None}, h)
    did = d["id"]
    print(f"[ok] dashboard id = {did}")

    # 3. create tabs first (two-step: tabs, then cards reference real tab ids)
    tab_specs = [{"id": -(i + 1), "name": n} for i, n in enumerate(TAB_NAMES)]
    req("PUT", f"/api/dashboard/{did}", {"tabs": tab_specs, "dashcards": []}, h)
    d2 = req("GET", f"/api/dashboard/{did}", headers=h)
    real_tabs = d2.get("tabs", [])
    tab_ids = {t["name"]: t["id"] for t in real_tabs}
    print(f"[ok] tabs: {tab_ids}")

    # 4. attach cards + filter mappings
    dashcards, neg = [], -1
    for c in CARDS:
        cid = card_ids[c["name"]]
        tid = tab_ids[c["tab_name"]]
        mappings = [
            {"parameter_id": p, "card_id": cid, "target": ["variable", ["template-tag", p]]}
            for p in c["tag_names"]
        ]
        dashcards.append({
            "id": neg, "card_id": cid, "dashboard_tab_id": tid,
            "row": c["row"], "col": c["col"],
            "size_x": c["size_x"], "size_y": c["size_y"],
            "parameter_mappings": mappings,
        })
        neg -= 1
    req("PUT", f"/api/dashboard/{did}",
        {"tabs": real_tabs, "dashcards": dashcards, "parameters": PARAMS, "auto_apply_filters": True}, h)
    print(f"[ok] wired: 3 tabs, {len(CARDS)} cards, {len(PARAMS)} filters")
    print(f"\n[done] open: {BASE}/dashboard/{did}")


if __name__ == "__main__":
    main()
