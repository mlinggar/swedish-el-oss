#!/usr/bin/env python3
"""Build the swedish-el Metabase dashboard via the REST API (Metabase v0.65).

Creates 7 questions (native SQL), a dashboard with 2 tabs, and 5 filters
(Year / Quarter / Month / zone_id / driver) connected to the questions.

Auth (choose one):
    export METABASE_API_KEY="..."                    # preferred
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
                 + e.read().decode("utf-8", "replace")[:1000])


def auth_headers():
    key = os.environ.get("METABASE_API_KEY")
    if key:
        return {"X-Api-Key": key}
    user, pw = os.environ.get("METABASE_USER"), os.environ.get("METABASE_PASSWORD")
    if user and pw:
        sess = req("POST", "/api/session", {"username": user, "password": pw})
        return {"X-Metabase-Session": sess["id"]}
    sys.exit("Set METABASE_API_KEY (preferred) or METABASE_USER + METABASE_PASSWORD.")


def find_db(headers, name="swedish_el"):
    data = req("GET", "/api/database", headers=headers)
    dbs = data.get("data", []) if isinstance(data, dict) else data
    # Prefer the postgres connection (the one holding gold.*); fall back to name match.
    for d in dbs:
        if d.get("engine") == "postgres":
            return d["id"]
    for d in dbs:
        if d.get("name") == name:
            return d["id"]
    sys.exit(f"Metabase database '{name}' (or any postgres) not found - connect it first (Admin > Databases).")


# ---------------------------------------------------------------- template tags
def tags(*names):
    t = {}
    for n in names:
        t[n] = {
            "id": n,
            "name": n,
            "display-name": {"year": "Year", "quarter": "Quarter", "month": "Month",
                             "zone": "zone_id", "driver": "driver"}[n],
            "type": "number" if n in ("year", "quarter", "month") else "text",
        }
    return t


# Shared optional-filter clause block (reused per panel).
YQM = """
  [[AND extract(year from date_local)    = {{year}}]]
  [[AND extract(quarter from date_local) = {{quarter}}]]
  [[AND extract(month from date_local)   = {{month}}]]
  [[AND zone_id = {{zone}}]]"""
YQMD = YQM + """
  [[AND driver_name = {{driver}}]]"""


# ---------------------------------------------------------------- panels
CARDS = [
    {
        "name": "P1 Spot price line",
        "display": "line",
        "tag_names": ["year", "quarter", "month", "zone"],
        "sql": f"""SELECT date_local, zone_id AS zone,
       round(avg(price_sek_kwh_avg)::numeric, 4) AS spot_sek_kwh
FROM gold.fact_daily
WHERE 1=1 {YQM}
GROUP BY date_local, zone_id
ORDER BY date_local""",
        "viz": {"graph.dimensions": ["date_local", "zone"], "graph.metrics": ["spot_sek_kwh"]},
        "tab": 1, "row": 0, "col": 0, "size_x": 24, "size_y": 6,
    },
    {
        "name": "P2 Avg spot by zone",
        "display": "bar",
        "tag_names": ["year", "quarter", "month", "zone"],
        "sql": f"""SELECT zone_id AS zone,
       round(avg(price_sek_kwh_avg)::numeric, 4) AS avg_spot_sek_kwh
FROM gold.fact_daily
WHERE 1=1 {YQM}
GROUP BY zone_id
ORDER BY avg_spot_sek_kwh DESC""",
        "viz": {"graph.dimensions": ["zone"], "graph.metrics": ["avg_spot_sek_kwh"]},
        "tab": 1, "row": 6, "col": 0, "size_x": 12, "size_y": 5,
    },
    {
        "name": "P3 Peak vs off-peak",
        "display": "bar",
        "tag_names": ["year", "quarter", "month", "zone"],
        "sql": f"""SELECT date_local,
       round(avg(price_peak_avg_sek_kwh)::numeric, 4)    AS peak_sek_kwh,
       round(avg(price_offpeak_avg_sek_kwh)::numeric, 4) AS offpeak_sek_kwh,
       round(avg((price_peak_avg_sek_kwh - price_offpeak_avg_sek_kwh)
                 / nullif(price_offpeak_avg_sek_kwh, 0) * 100)::numeric, 2) AS peak_premium_pct
FROM gold.fact_daily
WHERE 1=1 {YQM}
GROUP BY date_local
ORDER BY date_local""",
        "viz": {
            "graph.dimensions": ["date_local"],
            "graph.metrics": ["peak_sek_kwh", "offpeak_sek_kwh", "peak_premium_pct"],
            "series_settings": {"peak_premium_pct": {"display": "line"}},
        },
        "tab": 1, "row": 6, "col": 12, "size_x": 12, "size_y": 5,
    },
    {
        "name": "P4 Cheapest hour",
        "display": "bar",
        "tag_names": ["year", "quarter", "month", "zone"],
        "sql": f"""SELECT cheapest_hour_local AS hour_of_day, count(*) AS days
FROM gold.fact_daily
WHERE 1=1 {YQM}
GROUP BY cheapest_hour_local
ORDER BY cheapest_hour_local""",
        "viz": {"graph.dimensions": ["hour_of_day"], "graph.metrics": ["days"]},
        "tab": 1, "row": 11, "col": 0, "size_x": 12, "size_y": 5,
    },
    {
        "name": "P7 Bill breakdown",
        "display": "bar",
        "tag_names": ["year", "quarter", "month", "zone"],
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
        "viz": {
            "graph.dimensions": ["month", "zone"],
            "graph.metrics": ["spot_sek_kwh", "energy_tax_sek_kwh", "grid_fee_sek_kwh", "vat_sek_kwh"],
            "stackable.stack_type": "stacked",
        },
        "tab": 1, "row": 11, "col": 12, "size_x": 12, "size_y": 5,
    },
    {
        "name": "P5 Spot vs Driver",
        "display": "line",
        "tag_names": ["year", "quarter", "month", "zone", "driver"],
        "sql": f"""SELECT date_local,
       round(avg(spot_sek_kwh)::numeric, 4)  AS spot_sek_kwh,
       round(avg(driver_value)::numeric, 4)  AS driver_value
FROM gold.driver_daily
WHERE 1=1 {YQMD}
GROUP BY date_local
ORDER BY date_local""",
        "viz": {
            "graph.dimensions": ["date_local"],
            "graph.metrics": ["spot_sek_kwh", "driver_value"],
            "series_settings": {"driver_value": {"axis": "right"}},
        },
        "tab": 2, "row": 0, "col": 0, "size_x": 24, "size_y": 6,
    },
    {
        "name": "P6 Spot vs Driver scatter",
        "display": "scatter",
        "tag_names": ["year", "quarter", "month", "zone", "driver"],
        "sql": f"""SELECT round(driver_value::numeric, 4) AS driver_value,
       round(spot_sek_kwh::numeric, 4) AS spot_sek_kwh
FROM gold.driver_daily
WHERE 1=1 {YQMD}""",
        "viz": {"graph.dimensions": ["driver_value"], "graph.metrics": ["spot_sek_kwh"]},
        "tab": 2, "row": 6, "col": 0, "size_x": 24, "size_y": 6,
    },
]

# ------------------------------------------------------------- dashboard params
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

DASHBOARDS = [
    {"name": "Swedish EL - Spot Price Analytics",
     "cards": ["P1 Spot price line", "P2 Avg spot by zone", "P3 Peak vs off-peak",
               "P4 Cheapest hour", "P7 Bill breakdown"],
     "params": ["year", "quarter", "month", "zone"]},
    {"name": "Swedish EL - Spot vs Driver",
     "cards": ["P5 Spot vs Driver", "P6 Spot vs Driver scatter"],
     "params": ["year", "quarter", "month", "zone", "driver"]},
]


def main():
    h = auth_headers()
    db_id = find_db(h)
    print(f"[ok] database id = {db_id}")

    # 1. create the 7 questions
    card_ids = {}
    for c in CARDS:
        payload = {
            "name": c["name"],
            "display": c["display"],
            "dataset_query": {
                "type": "native",
                "database": db_id,
                "native": {"query": c["sql"], "template-tags": tags(*c["tag_names"])},
            },
            "visualization_settings": c["viz"],
            "collection_id": None,
            "description": "swedish-el dashboard panel",
        }
        r = req("POST", "/api/card", payload, h)
        card_ids[c["name"]] = r["id"]
        print(f"[ok] question: {c['name']} (id={r['id']})")

    # 2. build the two dashboards (matches the mock's two pages)
    for dash in DASHBOARDS:
        d = req("POST", "/api/dashboard", {"name": dash["name"], "collection_id": None}, h)
        did = d["id"]
        dashcards, neg = [], -1
        for name in dash["cards"]:
            c = next(x for x in CARDS if x["name"] == name)
            cid = card_ids[name]
            mappings = [
                {"parameter_id": p, "card_id": cid, "target": ["variable", ["template-tag", p]]}
                for p in dash["params"] if p in c["tag_names"]
            ]
            dashcards.append({
                "id": neg, "card_id": cid, "row": c["row"], "col": c["col"],
                "size_x": c["size_x"], "size_y": c["size_y"],
                "parameter_mappings": mappings,
            })
            neg -= 1
        params = [p for p in PARAMS if p["id"] in dash["params"]]
        req("PUT", f"/api/dashboard/{did}",
            {"dashcards": dashcards, "parameters": params, "auto_apply_filters": True}, h)
        print(f"[ok] dashboard: {dash['name']} (id={did})")
        print(f"     open: {BASE}/dashboard/{did}")


if __name__ == "__main__":
    main()
