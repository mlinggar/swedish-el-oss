#!/usr/bin/env python3
"""Generate a self-contained working demo of the "Warm Your Home for Less" feature.

Queries the real data platform (hourly prices, bill price, forecast) and writes a
single self-contained HTML file you can open in any browser.

    python proposals/build_warm_home_demo.py
    -> proposals/warm-your-home-for-less-demo.html
"""
import datetime as dt
import json
import os

import psycopg2

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(REPO, "proposals", "warm-your-home-for-less-demo.html")
ZONES = ["SE1", "SE2", "SE3", "SE4"]
MODEL = {"setpoint": 21, "balance": 15, "ua": 1.0, "cop": 3.0}  # assumed home + heat pump


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


def gather():
    conn = get_conn()
    cur = conn.cursor()
    data = {"zones": ZONES, "model": MODEL, "hourly": {}, "latest_bill": {}, "forecast": {}}
    for z in ZONES:
        # 24-hour typical price profile (the "when to heat" curve)
        hr = rows(cur, """SELECT extract(hour from ts_local)::int AS h,
                  round(avg(price_sek_kwh)::numeric, 3) AS p
           FROM silver.entsoe_timeseries
           WHERE bidding_zone = %s AND price_sek_kwh IS NOT NULL
           GROUP BY 1 ORDER BY 1""", (z,))
        prof = [None] * 24
        for r in hr:
            if r["h"] is not None and 0 <= int(r["h"]) < 24:
                prof[int(r["h"])] = float(r["p"])
        data["hourly"][z] = prof

        # current all-in bill price (what the household pays per kWh)
        lb = rows(cur, """SELECT total_consumer_sek_kwh AS v FROM gold.fact_daily
           WHERE zone_id = %s ORDER BY date_local DESC LIMIT 1""", (z,))
        data["latest_bill"][z] = float(lb[0]["v"]) if lb else 3.0

        # next-days forecast: bill price (price_forecast) + temp (weather forecast)
        bill = rows(cur, """SELECT to_char(target_date, 'YYYY-MM-DD') AS d,
                  round(total_bill_sek_kwh::numeric, 3) AS bill
           FROM gold.price_forecast
           WHERE zone = %s AND is_forecast ORDER BY target_date LIMIT 7""", (z,))
        temp = {r["d"]: float(r["t"]) for r in rows(cur, """
           SELECT to_char(date(ts_local), 'YYYY-MM-DD') AS d,
                  round(avg(air_temperature)::numeric, 1) AS t
           FROM silver.weather_forecast_hourly WHERE zone = %s
           GROUP BY 1 ORDER BY 1""", (z,))}
        data["forecast"][z] = [{"date": b["d"], "bill": float(b["bill"]),
                                "temp": temp.get(b["d"])} for b in bill]
    conn.close()
    return data


TEMPLATE = r"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Warm Your Home for Less — demo</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;500;600;700&family=Inter:wght@400;500;600&display=swap" rel="stylesheet">
<script src="https://cdn.jsdelivr.net/npm/echarts@5.5.0/dist/echarts.min.js"></script>
<style>
  :root{--ground:#eef1f5;--surface:#fff;--ink:#0c1217;--muted:#566172;--line:#e2e7ee;
        --accent:#ff5a25;--accent-text:#b03a0e;--r-card:12px;
        --f-display:"Space Grotesk",sans-serif;--f-body:"Inter",sans-serif;--ease:cubic-bezier(.22,.61,.36,1);}
  *{box-sizing:border-box} body{margin:0;background:var(--ground);color:var(--ink);
    font-family:var(--f-body);font-size:17px;line-height:1.5;-webkit-font-smoothing:antialiased}
  .frame{position:sticky;top:0;z-index:40;display:flex;align-items:center;justify-content:space-between;
    gap:16px;padding:16px clamp(20px,5vw,56px);background:rgba(238,241,245,.92);border-bottom:1px solid var(--line)}
  .wordmark{font-family:var(--f-display);font-weight:700;font-size:18px;letter-spacing:-.02em;
    display:flex;align-items:center;gap:9px}
  .wordmark .dot{width:10px;height:10px;border-radius:50%;background:var(--accent);box-shadow:0 0 0 4px rgba(255,90,37,.16)}
  .zone-nav{display:flex;gap:6px}
  .zone-nav button{font-family:var(--f-display);font-weight:500;font-size:13px;padding:8px 14px;min-width:48px;
    border:1px solid var(--line);border-radius:999px;background:var(--surface);color:var(--muted);cursor:pointer;
    transition:.2s var(--ease)}
  .zone-nav button:hover{transform:translateY(-1px);color:var(--ink)}
  .zone-nav button[aria-pressed="true"]{background:var(--ink);color:#fff;border-color:var(--ink)}
  .wrap{max-width:1180px;margin:0 auto;padding:0 clamp(20px,5vw,56px)}
  section{padding:clamp(44px,6vw,72px) 0}
  h1,h2{font-family:var(--f-display);letter-spacing:-.03em;margin:0}
  h1{font-size:clamp(34px,6vw,66px);line-height:1;font-weight:700}
  h2{font-size:clamp(24px,3.5vw,38px);font-weight:600}
  .lede{color:var(--muted);font-size:clamp(16px,1.6vw,20px);margin:16px 0 0;max-width:56ch}
  .eyebrow{font-family:var(--f-display);font-size:12px;font-weight:500;letter-spacing:.14em;
    text-transform:uppercase;color:var(--accent-text);margin:0 0 12px}
  .well{background:var(--surface);border:1px solid var(--line);border-radius:var(--r-card);
    padding:clamp(18px,2.5vw,28px);box-shadow:0 1px 2px rgba(12,18,23,.04)}
  .chart{width:100%;height:320px}
  .grid2{display:grid;grid-template-columns:1fr;gap:16px}
  @media(min-width:900px){.grid2{grid-template-columns:1.1fr .9fr}}
  .ctitle{font-family:var(--f-display);font-size:21px;font-weight:600;letter-spacing:-.02em;margin:0 0 4px}
  .small{font-size:13px;color:var(--muted);margin:0 0 12px}
  .note{margin:14px 0 0;color:var(--muted);font-size:14px;line-height:1.55}
  .note strong{color:var(--ink)}
  .field{margin:18px 0}
  .field label{display:block;font-size:13px;color:var(--muted);margin-bottom:8px}
  .field .row{display:flex;align-items:center;gap:14px}
  input[type=range]{flex:1;accent-color:var(--accent)}
  .val{font-family:var(--f-display);font-weight:600;font-size:18px;min-width:74px;text-align:right}
  .cost-out{background:var(--ground);border-radius:10px;padding:18px 20px;margin-top:6px}
  .cost-out .big{font-family:var(--f-display);font-weight:700;font-size:40px;letter-spacing:-.02em;margin:2px 0}
  .cost-out .big small{font-size:15px;color:var(--muted);font-weight:500;margin-left:5px}
  .cost-out .sub{font-size:13px;color:var(--muted);margin:6px 0 0}
  .win{display:flex;gap:10px;flex-wrap:wrap;margin-top:14px}
  .chip{font-family:var(--f-display);font-size:13px;font-weight:500;padding:7px 13px;border-radius:999px}
  .chip.good{background:rgba(46,139,111,.12);color:#1f6b52}
  .chip.bad{background:rgba(192,57,43,.1);color:#b02818}
  footer{border-top:1px solid var(--line);padding:36px 0 44px;color:var(--muted);font-size:13px}
</style>
</head>
<body>
<header class="frame">
  <div class="wordmark"><span class="dot"></span>Warm Your Home for Less</div>
  <nav class="zone-nav" aria-label="Bidding zone">
    <button data-zone="SE1" aria-pressed="false">SE1</button>
    <button data-zone="SE2" aria-pressed="false">SE2</button>
    <button data-zone="SE3" aria-pressed="false">SE3</button>
    <button data-zone="SE4" aria-pressed="true">SE4</button>
  </nav>
</header>

<main>
  <section class="wrap">
    <p class="eyebrow">Demo · smart heating load-shifting</p>
    <h1>Heat with cheap electricity.</h1>
    <p class="lede">Heating is your biggest winter cost, and Swedish prices swing through the day.
      Heat when power is cheap, coast when it is not, and plan ahead with the forecast.</p>
  </section>

  <section class="wrap">
    <div class="well">
      <p class="ctitle">When to heat</p>
      <p class="small">Typical day · spot price SEK/kWh · <span id="when-zone">SE4</span></p>
      <div id="when-chart" class="chart"></div>
      <div class="win" id="when-chips"></div>
      <p class="note" id="when-note"></p>
    </div>
  </section>

  <section class="wrap">
    <div class="grid2">
      <div class="well">
        <p class="ctitle">What heating costs</p>
        <p class="small">Adjust your comfort setpoint and the outdoor temperature.</p>
        <div class="field">
          <label for="setpoint">Comfort setpoint</label>
          <div class="row"><input id="setpoint" type="range" min="19" max="23" step="0.5" value="21">
            <span class="val" id="setpoint-val">21.0 °C</span></div>
        </div>
        <div class="field">
          <label for="outtemp">Outdoor temperature</label>
          <div class="row"><input id="outtemp" type="range" min="-15" max="15" step="0.5" value="-5">
            <span class="val" id="outtemp-val">-5.0 °C</span></div>
        </div>
        <div class="cost-out">
          <p class="small" style="margin:0">Heating adds about</p>
          <p class="big"><span id="cost-sek">—</span><small>SEK / day</small></p>
          <p class="sub"><span id="cost-kwh">—</span> kWh/day · at <span id="cost-price">—</span> SEK/kWh</p>
          <p class="sub" id="cost-save"></p>
        </div>
      </div>

      <div class="well">
        <p class="ctitle">Plan ahead</p>
        <p class="small">Next days · bill price and forecast temperature</p>
        <div id="plan-chart" class="chart"></div>
        <p class="note" id="plan-note"></p>
      </div>
    </div>
  </section>
</main>

<footer class="wrap">
  Demo built from the swedish-el-oss data platform (hourly Nord Pool prices, bill price,
  temperature forecast). Heating model uses clearly-labelled assumptions:
  heat-loss <strong>1.0 kWh/°C·day</strong> and heat-pump <strong>COP 3.0</strong>.
</footer>

<script>window.__DATA__ = __PAYLOAD__;</script>
<script>
(function () {
  var D = window.__DATA__, MODEL = D.model, zone = "SE4";
  var $ = function (s) { return document.querySelector(s); };
  function fmt(v, n) { n = n == null ? 1 : n; return v == null ? "—" : Number(v).toLocaleString("en-SE", { minimumFractionDigits: n, maximumFractionDigits: n }); }
  function pad(h) { return (h < 10 ? "0" : "") + h; }
  // cheap (green) -> dear (red) ramp
  function ramp(t) {
    t = Math.max(0, Math.min(1, t)); var stops = [[46,139,111],[228,161,27],[192,57,43]];
    var seg = t < 0.5 ? 0 : 1, lt = t < 0.5 ? t * 2 : (t - 0.5) * 2, a = stops[seg], b = stops[seg + 1];
    return "rgb(" + Math.round(a[0]+(b[0]-a[0])*lt) + "," + Math.round(a[1]+(b[1]-a[1])*lt) + "," + Math.round(a[2]+(b[2]-a[2])*lt) + ")";
  }
  var charts = {};
  function el(id) { if (charts[id]) return charts[id]; var d = document.getElementById(id); if (!d || !window.echarts) return null; charts[id] = echarts.init(d); return charts[id]; }

  // ---- heating model: degree-days x heat-loss / COP ----
  function heatKwh(tempC, setC) { return MODEL.ua * Math.max(0, setC - tempC) / MODEL.cop; }

  // ---- when to heat ----
  function heatWindow(prices) {
    var best = { sum: Infinity, from: 0, to: 0 };
    for (var s = 0; s < 24; s++) { var sum = 0; for (var k = 0; k < 6; k++) sum += prices[(s + k) % 24];
      if (sum < best.sum) best = { sum: sum, from: s, to: (s + 6) % 24 }; }
    return best;
  }
  function renderWhen() {
    var prices = D.hourly[zone] || [];
    var lo = Math.min.apply(null, prices), hi = Math.max.apply(null, prices);
    $("#when-zone").textContent = zone;
    var c = el("when-chart");
    if (c) c.setOption({
      animationDuration: 700,
      grid: { left: 6, right: 10, top: 12, bottom: 4, containLabel: true },
      tooltip: { valueFormatter: function (v) { return fmt(v, 3) + " SEK/kWh"; } },
      xAxis: { type: "category", data: prices.map(function (p, h) { return pad(h) + ":00"; }),
               axisLine: { lineStyle: { color: "#e2e7ee" } }, axisLabel: { color: "#566172", fontSize: 11 }, axisTick: { show: false } },
      yAxis: { type: "value", scale: true, splitLine: { lineStyle: { color: "#e2e7ee" } }, axisLabel: { color: "#566172", fontSize: 11 } },
      series: [{ type: "bar", barWidth: "68%",
        data: prices.map(function (p) { return { value: p, itemStyle: { color: ramp((p - lo) / (hi - lo)), borderRadius: [4,4,0,0] } }; }) }]
    }, true);
    var w = heatWindow(prices);
    $("#when-chips").innerHTML =
      '<span class="chip good">Best window to heat: ' + pad(w.from) + ':00 – ' + pad(w.to) + ':00</span>' +
      '<span class="chip bad">Most expensive: ' + pad(prices.indexOf(hi)) + ':00 (' + fmt(hi, 2) + ' SEK/kWh)</span>';
    $("#when-note").innerHTML = "Shift heating into the <strong>green overnight window</strong> and coast through the " +
      "expensive morning and evening peaks. The cheapest hours cost <strong>" + fmt(lo, 2) + " SEK/kWh</strong> against " +
      "<strong>" + fmt(hi, 2) + "</strong> at the peak — a <strong>" + (hi / lo).toFixed(1) + "x</strong> swing within one day.";
  }

  // ---- heating cost ----
  function renderCost() {
    var set = parseFloat($("#setpoint").value), t = parseFloat($("#outtemp").value);
    var price = D.latest_bill[zone];
    $("#setpoint-val").textContent = fmt(set, 1) + " °C";
    $("#outtemp-val").textContent = fmt(t, 1) + " °C";
    var kwh = heatKwh(t, set), cost = kwh * price;
    $("#cost-sek").textContent = fmt(cost, 0);
    $("#cost-kwh").textContent = fmt(kwh, 1);
    $("#cost-price").textContent = fmt(price, 2);
    var perDeg = MODEL.ua / MODEL.cop * price;
    $("#cost-save").textContent = "Each degree lower on the setpoint saves about " + fmt(perDeg, 1) + " SEK/day (" + fmt(perDeg * 30, 0) + " SEK/month).";
  }

  // ---- plan ahead ----
  function renderPlan() {
    var fc = D.forecast[zone] || [];
    var dates = fc.map(function (f) { return f.date.slice(5); });
    var bills = fc.map(function (f) { return f.bill; });
    var temps = fc.map(function (f) { return f.temp; });
    var c = el("plan-chart");
    if (c) c.setOption({
      animationDuration: 700,
      grid: { left: 6, right: 6, top: 22, bottom: 4, containLabel: true },
      tooltip: { trigger: "axis" },
      legend: { data: ["Bill price", "Temp (°C)"], textStyle: { color: "#566172", fontSize: 11 } },
      xAxis: { type: "category", data: dates, axisLine: { lineStyle: { color: "#e2e7ee" } }, axisLabel: { color: "#566172", fontSize: 11 }, axisTick: { show: false } },
      yAxis: [
        { type: "value", scale: true, splitLine: { lineStyle: { color: "#e2e7ee" } }, axisLabel: { color: "#566172", fontSize: 11 } },
        { type: "value", scale: true, splitLine: { show: false }, axisLabel: { color: "#566172", fontSize: 11 } }
      ],
      series: [
        { name: "Bill price", type: "bar", barWidth: "52%", data: bills, itemStyle: { color: "#ff5a25", borderRadius: [4,4,0,0] }, yAxisIndex: 0 },
        { name: "Temp (°C)", type: "line", data: temps, showSymbol: true, lineStyle: { color: "#0c1217", width: 2 }, yAxisIndex: 1 }
      ]
    }, true);
    // advice: cold + expensive -> pre-heat
    var cold = fc.filter(function (f) { return f.temp != null && f.temp < 2; }).length;
    var dear = fc.filter(function (f) { return f.bill >= 3.0; }).length;
    var msg;
    if (cold >= 3 && dear >= 3) msg = "<strong>Cold and expensive ahead.</strong> Pre-heat hard in the cheap overnight window and coast through the peaks to keep costs down.";
    else if (dear >= 3) msg = "<strong>Several pricey days ahead.</strong> Shift heating into the cheapest hours to soften the bill.";
    else if (cold >= 3) msg = "<strong>Cold days ahead.</strong> Heating load will rise, but prices are moderate — a good time to warm the house steadily.";
    else msg = "<strong>A mild, reasonably priced stretch.</strong> Normal heating is fine; keep an eye on the overnight window.";
    $("#plan-note").innerHTML = msg;
  }

  function renderAll() { renderWhen(); renderCost(); renderPlan();
    Object.keys(charts).forEach(function (k) { charts[k].resize(); }); }

  // zone selector
  document.querySelectorAll(".zone-nav button").forEach(function (b) {
    b.addEventListener("click", function () {
      zone = b.getAttribute("data-zone");
      document.querySelectorAll(".zone-nav button").forEach(function (x) { x.setAttribute("aria-pressed", String(x === b)); });
      renderAll();
    });
  });
  $("#setpoint").addEventListener("input", renderCost);
  $("#outtemp").addEventListener("input", renderCost);

  renderAll();
  window.addEventListener("resize", function () { Object.keys(charts).forEach(function (k) { charts[k].resize(); }); });
})();
</script>
</body>
</html>
"""


def main():
    data = gather()
    html = TEMPLATE.replace("__PAYLOAD__", json.dumps(data, separators=(",", ":")))
    with open(OUT, "w") as fh:
        fh.write(html)
    print(f"[ok] {OUT} ({os.path.getsize(OUT)/1024:.0f} KB)")
    for z in ZONES:
        h = data["hourly"][z]
        print(f"    {z}: {len([x for x in h if x is not None])}/24 hourly prices, "
              f"{len(data['forecast'][z])} forecast days, bill {data['latest_bill'][z]:.2f} SEK/kWh")


if __name__ == "__main__":
    main()
