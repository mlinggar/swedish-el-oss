#!/usr/bin/env python3
"""Generate the public website: gold layer -> docs/data/data.json, site shell -> docs/.

Run (also wired into run_daily.sh):
    python site/build_site.py
"""
import datetime as dt
import json
import os
import shutil
import sys

import psycopg2

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(REPO, "docs")
STATIC = os.path.join(REPO, "site", "static")
HISTORY_DAYS = 365  # window shown behind the forecast on the trend chart


def get_conn():
    kw = {"dbname": os.environ.get("PGDATABASE", "swedish_el"),
          "user": os.environ.get("PGUSER", "mlinggar")}
    if os.environ.get("PGHOST"):
        kw["host"] = os.environ["PGHOST"]
    return psycopg2.connect(**kw)


def rows(cur, sql, args=None):
    cur.execute(sql, args or ())
    cols = [d.name for d in cur.description]
    return [dict(zip(cols, r)) for r in cur.fetchall()]


def f(x, n=4):
    return None if x is None else round(float(x), n)


def gather():
    conn = get_conn()
    cur = conn.cursor()
    out = {}

    # ---- meta ----
    latest = rows(cur, "SELECT max(date_local) AS d FROM gold.fact_daily")[0]["d"]
    fc_gen = rows(cur, "SELECT max(generated_at) AS g FROM gold.price_forecast")[0]["g"]
    out["meta"] = {
        "generated_at": dt.datetime.now().strftime("%Y-%m-%d %H:%M"),
        "latest_date": str(latest),
        "forecast_generated_at": str(fc_gen) if fc_gen else None,
        "zones": ["SE1", "SE2", "SE3", "SE4"],
        "unit": "SEK/kWh",
        "sources": ["ENTSO-E (Nord Pool spot)", "SCB (consumer prices)",
                    "ECB (EUR/SEK)", "EIA (gas)", "SMHI (weather + hydro)"],
        "disclaimer": "Forecasts are model estimates (p50 with a p10-p90 range), not a promise.",
    }
    zones = out["meta"]["zones"]

    # ---- now (latest day, per zone) ----
    out["now"] = {}
    for r in rows(cur, """SELECT zone_id, date_local, price_sek_kwh_avg, total_consumer_sek_kwh,
              cheapest_hour_local, price_peak_avg_sek_kwh, price_offpeak_avg_sek_kwh,
              energy_tax_sek_kwh, grid_fee_sek_kwh, vat_rate
       FROM gold.fact_daily WHERE date_local = %s ORDER BY zone_id""", (latest,)):
        out["now"][r["zone_id"]] = {
            "date": str(r["date_local"]), "spot": f(r["price_sek_kwh_avg"]),
            "bill": f(r["total_consumer_sek_kwh"]),
            "cheapest_hour": r["cheapest_hour_local"],
            "peak": f(r["price_peak_avg_sek_kwh"]), "offpeak": f(r["price_offpeak_avg_sek_kwh"]),
            "tax": f(r["energy_tax_sek_kwh"]), "grid_fee": f(r["grid_fee_sek_kwh"]),
            "vat_rate": f(r["vat_rate"], 3),
        }

    # ---- horizon (next day/week/month forecast, per zone) ----
    out["horizon"] = {z: {} for z in zones}
    hmap = {"next-day": "day", "next-week": "week", "next-month": "month"}
    for r in rows(cur, """SELECT zone, horizon, period_start, period_end,
              spot_sek_kwh, spot_p10_sek_kwh, spot_p90_sek_kwh,
              total_bill_sek_kwh, total_bill_p10_sek_kwh, total_bill_p90_sek_kwh
       FROM gold.price_forecast_summary"""):
        out["horizon"][r["zone"]][hmap.get(r["horizon"], r["horizon"])] = {
            "start": str(r["period_start"]), "end": str(r["period_end"]),
            "spot": f(r["spot_sek_kwh"]), "spot_p10": f(r["spot_p10_sek_kwh"]),
            "spot_p90": f(r["spot_p90_sek_kwh"]),
            "bill": f(r["total_bill_sek_kwh"]), "bill_p10": f(r["total_bill_p10_sek_kwh"]),
            "bill_p90": f(r["total_bill_p90_sek_kwh"]),
        }

    # ---- chart: recent history + forecast into one timeline ----
    hist = rows(cur, """SELECT date_local, zone_id, price_sek_kwh_avg, total_consumer_sek_kwh
       FROM gold.fact_daily
       WHERE date_local >= %s ORDER BY date_local""",
                (latest - dt.timedelta(days=HISTORY_DAYS),))
    fcast = rows(cur, """SELECT target_date, zone, spot_sek_kwh, spot_p10_sek_kwh, spot_p90_sek_kwh,
              total_bill_sek_kwh, total_bill_p10_sek_kwh, total_bill_p90_sek_kwh
       FROM gold.price_forecast WHERE is_forecast = true ORDER BY target_date""")
    dates = sorted({str(r["date_local"]) for r in hist} | {str(r["target_date"]) for r in fcast})
    idx = {d: i for i, d in enumerate(dates)}
    n = len(dates)
    series = {z: {k: [None] * n for k in (
        "actual_spot", "fc_spot", "fc_spot_p10", "fc_spot_p90",
        "actual_bill", "fc_bill", "fc_bill_p10", "fc_bill_p90")} for z in zones}
    for r in hist:
        i = idx[str(r["date_local"])]
        s = series[r["zone_id"]]
        s["actual_spot"][i] = f(r["price_sek_kwh_avg"])
        s["actual_bill"][i] = f(r["total_consumer_sek_kwh"])
    for r in fcast:
        i = idx[str(r["target_date"])]
        s = series[r["zone"]]
        s["fc_spot"][i] = f(r["spot_sek_kwh"])
        s["fc_spot_p10"][i] = f(r["spot_p10_sek_kwh"])
        s["fc_spot_p90"][i] = f(r["spot_p90_sek_kwh"])
        s["fc_bill"][i] = f(r["total_bill_sek_kwh"])
        s["fc_bill_p10"][i] = f(r["total_bill_p10_sek_kwh"])
        s["fc_bill_p90"][i] = f(r["total_bill_p90_sek_kwh"])
    out["chart"] = {"dates": dates, "series": series}

    # ---- bill composition (last 30d avg, per zone) ----
    out["bill"] = {}
    for r in rows(cur, """SELECT zone_id, avg(price_sek_kwh_avg) spot, avg(energy_tax_sek_kwh) tax,
              avg(grid_fee_sek_kwh) gf, avg(total_consumer_sek_kwh) total
       FROM gold.fact_daily
       WHERE date_local >= %s GROUP BY zone_id""", (latest - dt.timedelta(days=30),)):
        total = f(r["total"])
        parts = {"spot": f(r["spot"]), "tax": f(r["tax"]), "grid_fee": f(r["gf"])}
        parts["vat"] = f(total - sum(v for v in parts.values() if v))
        parts["total"] = total
        out["bill"][r["zone_id"]] = parts

    # ---- plan your use (per zone) ----
    out["plan"] = {z: {} for z in zones}
    win = latest - dt.timedelta(days=90)
    for r in rows(cur, """SELECT zone_id, avg(price_peak_avg_sek_kwh) peak,
              avg(price_offpeak_avg_sek_kwh) offpeak
       FROM gold.fact_daily WHERE date_local >= %s GROUP BY zone_id""", (win,)):
        out["plan"][r["zone_id"]]["peak"] = f(r["peak"])
        out["plan"][r["zone_id"]]["offpeak"] = f(r["offpeak"])
    dow_names = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    tmp = {z: {} for z in zones}
    for r in rows(cur, """SELECT zone_id, extract(dow from date_local)::int dow, avg(price_sek_kwh_avg) v
       FROM gold.fact_daily WHERE date_local >= %s GROUP BY zone_id, dow""", (win,)):
        tmp[r["zone_id"]][int(r["dow"])] = f(r["v"])
    for z in zones:
        out["plan"][z]["day_of_week"] = [tmp[z].get(i) for i in range(7)]
        out["plan"][z]["dow_names"] = dow_names
    tmp = {z: {} for z in zones}
    for r in rows(cur, """SELECT zone_id, extract(month from date_local)::int mon, avg(price_sek_kwh_avg) v
       FROM gold.fact_daily WHERE date_local >= %s GROUP BY zone_id, mon""",
                  (latest - dt.timedelta(days=365),)):
        tmp[r["zone_id"]][int(r["mon"])] = f(r["v"])
    for z in zones:
        out["plan"][z]["month_avg"] = [tmp[z].get(i) for i in range(1, 13)]
    # cheapest hour: the most common cheapest hour over the last month (mode)
    for r in rows(cur, """SELECT zone_id, mode() WITHIN GROUP (ORDER BY cheapest_hour_local) h
       FROM gold.fact_daily WHERE date_local >= %s GROUP BY zone_id""",
                  (latest - dt.timedelta(days=30),)):
        out["plan"][r["zone_id"]]["cheapest_hour"] = r["h"]

    # ---- drivers: weather / hydro / gas + correlation to spot price ----
    DRV = {
        "Temp Avg °C": ("temp_now", "Temperature", "weather", "deg C"),
        "Wind Avg m/s": ("wind_now", "Wind", "weather", "m/s"),
        "Precipitation mm": ("precip_now", "Precipitation", "weather", "mm"),
        "Discharge m3/s": ("discharge_now", "Hydro discharge", "hydro", "m3/s"),
        "Gas Price SEK/MMBtu": ("gas_asof", "Gas price", "gas", "SEK/MMBtu"),
    }
    fkeys = [v[0] for v in DRV.values()]
    drivers = {
        "meta": {v[0]: {"label": v[1], "group": v[2], "unit": v[3]} for v in DRV.values()},
        "correlation": {z: {} for z in zones},
        "latest": {z: {} for z in zones},
        "trend": {z: {} for z in zones},
    }
    for r in rows(cur, """SELECT name, zone, metric_value FROM gold.price_model_evidence
       WHERE analysis='correlation' AND metric_name='pearson_r_deseasoned' AND name = ANY(%s)""",
                  (fkeys,)):
        if r["zone"] in drivers["correlation"]:
            drivers["correlation"][r["zone"]][r["name"]] = f(r["metric_value"], 3)
    for r in rows(cur, """SELECT DISTINCT ON (driver_name, zone_id) driver_name, zone_id, date_local, driver_value
       FROM gold.driver_daily WHERE driver_value IS NOT NULL
       ORDER BY driver_name, zone_id, date_local DESC"""):
        if r["driver_name"] in DRV and r["zone_id"] in drivers["latest"]:
            fk = DRV[r["driver_name"]][0]
            drivers["latest"][r["zone_id"]][fk] = {"v": f(r["driver_value"], 2), "date": str(r["date_local"])}
    tdates = {z: set() for z in zones}
    tdata = {z: {} for z in zones}
    for r in rows(cur, """SELECT zone_id, date_local, driver_name, driver_value, spot_sek_kwh
       FROM gold.driver_daily WHERE date_local >= %s""", (latest - dt.timedelta(days=120),)):
        z = r["zone_id"]; fk = DRV[r["driver_name"]][0]; d = str(r["date_local"])
        tdates[z].add(d)
        tdata[z].setdefault(fk, {})[d] = f(r["driver_value"])
        tdata[z].setdefault("spot", {})[d] = f(r["spot_sek_kwh"])
    for z in zones:
        ds = sorted(tdates[z])
        drivers["trend"][z] = {"dates": ds, "spot": [tdata[z]["spot"].get(d) for d in ds]}
        for fk in fkeys:
            drivers["trend"][z][fk] = [tdata[z].get(fk, {}).get(d) for d in ds]
    out["drivers"] = drivers

    conn.close()
    return out


def main():
    data = gather()
    os.makedirs(os.path.join(DOCS, "data"), exist_ok=True)
    payload = json.dumps(data, separators=(",", ":"))
    with open(os.path.join(DOCS, "data", "data.json"), "w") as fh:
        fh.write(payload)
    with open(os.path.join(DOCS, "data.js"), "w") as fh:
        fh.write("window.__DATA__=" + payload + ";")
    kb = len(payload) / 1024
    print(f"[ok] docs/data/data.json + docs/data.js ({kb:.0f} KB)")
    for name in ("index.html", "styles.css", "app.js", "favicon.svg"):
        src = os.path.join(STATIC, name)
        if os.path.exists(src):
            shutil.copy(src, os.path.join(DOCS, name))
            print(f"[ok] docs/{name}")
    print("[done] site generated")


if __name__ == "__main__":
    main()
