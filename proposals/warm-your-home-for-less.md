# Proposal — "Warm Your Home for Less"

### Smart heating load-shifting for the Swedish EL price tracker

| | |
|---|---|
| **Project** | `swedish-el-oss` — Swedish electricity price, bill & forecast platform |
| **Feature** | "Warm Your Home for Less" — a heating load-shifting assistant |
| **Date** | November 2026 |
| **Status** | Proposed |
| **Scope** | Public website (`docs/`), client-side, zero running cost |

---

## 1. Executive summary

Heating is the single largest driver of winter electricity use in Swedish homes, yet most homes heat on a fixed thermostat schedule — drawing the most power exactly when electricity is most expensive. Meanwhile Swedish day-ahead prices swing by up to **2x within a single day**: cheap overnight, and expensive at the morning and evening peaks.

**"Warm Your Home for Less"** turns that swing into savings. Using our real hourly price data, outdoor temperature and price forecast, the feature shows households exactly **when to heat**, **what heating costs** on a cold day, and **how to plan ahead**. By shifting heating into the low-price window and coasting through the expensive peaks, a typical household cuts its heating cost with no loss of comfort.

The feature is fully client-side (like the bill estimator and zone finder we already ship), privacy-preserving, and reuses the data platform that runs on the Mac each night. No new infrastructure is required.

---

## 2. The opportunity

Sweden's electricity price is set hourly on Nord Pool, and it follows a predictable daily shape: demand (and therefore price) rises as people wake up and again as they come home in the evening. Our own data shows the effect clearly. For the SE4 (southern Sweden) winter profile:

- **Cheapest hour:** around **03:00**, at roughly **0.65 SEK/kWh**.
- **Dearest hour:** around **17:00**, at roughly **1.39 SEK/kWh**.
- That is a **2x swing inside the same day**.

Space and water heating is the biggest household load in winter, and it is partly *shiftable* — a home stores heat in its structure and water tank. Heating harder during the cheap overnight window and easing off through the expensive peaks therefore reduces cost without reducing comfort. This is the classic "load-shifting" opportunity, and it is exactly what a price-tracking platform should enable.

The raw ingredients are already in our data platform:

| Need | Source (already built) |
|---|---|
| Hourly price curve | `silver.entsoe_timeseries` (`day_ahead_price`, `price_sek_kwh`) |
| Outdoor temperature (heating demand) | `gold.fact_daily` / `gold.thermostat_dataset_stockholm` |
| Price + temperature forecast | `gold.price_forecast`, `fact_daily.forecast_temp_c_avg` |
| Calendar / season context | `gold.thermostat_dataset_stockholm` (SE3/SE4 feature table) |

---

## 3. Proposed solution

A new website section, **"Warm Your Home for Less"**, built from three connected pieces:

### 3.1 When to heat *(the core — no assumptions needed)*
A 24-hour price curve for the selected zone. Cheap hours are shown in green, expensive hours in red (reusing the site's existing cheap-to-dear ramp), with the recommended heating windows called out — for example *"Heat 23:00–06:00, coast through the 07:00–09:00 and 16:00–18:00 peaks."* This is driven entirely by real hourly price data, so it needs no modelling assumptions.

### 3.2 Heating cost *(context — a small, transparent model)*
How much heating adds to the daily bill on a cold day. The model converts outdoor temperature into heating energy (via heating degree days), then into cost using the electricity price. It answers: *"on a −10 °C day, heating adds about X SEK."*

### 3.3 Plan ahead *(uses our forecast)*
The coming days' temperature and price forecast, phrased as advice: *"cold and expensive ahead — pre-heat tonight while it is cheap"* or *"a warm, cheap few days — a good time to run the heat pump hard."*

A **comfort-setpoint slider** (e.g. 19–23 °C) lets the user see how lowering the setpoint reduces heating cost.

---

## 4. How it works

### 4.1 Heating model
Heating demand scales with how far the outside temperature sits below the indoor setpoint. We use a simple, standard degree-day model:

```
heating_kwh_per_day = UA * max(0, setpoint_C - outdoor_C) / COP
heating_cost_sek    = heating_kwh_per_day * price_sek_per_kwh
```

Where:

- **`setpoint_C`** — the indoor comfort temperature (user-adjustable slider; default 21 °C).
- **`UA`** — the home's heat-loss factor, in kWh per degree-day (assumed **1.0** for a typical Swedish home; clearly labelled as an assumption).
- **`COP`** — the heating system's efficiency (assumed **3.0** for a heat pump; electric resistance would be 1.0).

> **Honest caveat:** the absolute cost depends on the home (size, insulation, heating system). The model uses clearly-labelled assumptions and the *shape* of the result (cold = expensive, cheap hours = cheap heat) is robust regardless. A full home-size/insulation input can be added later.

### 4.2 When-to-heat windows
The cheapest consecutive heating window is derived from the hourly price curve — the N lowest-priced contiguous hours — and the expensive peaks are the high-price clusters. This is pure data, no model.

---

## 5. Implementation (code)

The feature slots into the existing pipeline and static site exactly like the bill estimator and zone finder. All logic is client-side; the pipeline only exports data.

### 5.1 Data export — SQL (run in `site/build_site.py`)

**Hourly price profile (the "when to heat" curve):**

```sql
SELECT extract(hour from ts_local)::int              AS hour,
       round(avg(price_sek_kwh)::numeric, 3)         AS avg_sek_kwh
FROM silver.entsoe_timeseries
WHERE bidding_zone = :zone
  AND price_sek_kwh IS NOT NULL
GROUP BY 1
ORDER BY 1;
```

**Daily heating degree days, demand and cost:**

```sql
SELECT date_local,
       zone_id,
       temp_c_avg,
       greatest(0, 15 - temp_c_avg)                              AS hdd,
       greatest(0, 15 - temp_c_avg) * 1.0                        AS heat_loss_kwh,
       greatest(0, 15 - temp_c_avg) * 1.0 / 3.0                  AS heat_elec_kwh,
       round((greatest(0, 15 - temp_c_avg) * 1.0 / 3.0
              * total_consumer_sek_kwh)::numeric, 3)            AS heat_cost_sek
FROM gold.fact_daily
WHERE zone_id = :zone;
```

### 5.2 Data export — Python (added to `gather()` in `build_site.py`)

```python
# ---- heating: hourly price profile (when-to-heat) + daily demand ----
heating = {
    "hourly": {},   # zone -> [24 hourly avg prices]
    "demand": {},   # zone -> [{date, temp, hdd, heat_kwh, heat_cost}, ...]
    "model": {"setpoint_c": 21, "balance_c": 15,
              "ua_kwh_per_cday": 1.0, "cop": 3.0},
}
for z in zones:
    hr = rows(cur, """
        SELECT extract(hour from ts_local)::int AS h,
               round(avg(price_sek_kwh)::numeric, 3) AS p
        FROM silver.entsoe_timeseries
        WHERE bidding_zone = %s AND price_sek_kwh IS NOT NULL
        GROUP BY 1 ORDER BY 1""", (z,))
    heating["hourly"][z] = [r["p"] for r in hr]

    dm = rows(cur, """
        SELECT date_local, temp_c_avg, total_consumer_sek_kwh,
               greatest(0, %s - temp_c_avg) AS hdd
        FROM gold.fact_daily
        WHERE zone_id = %s AND date_local >= %s
        ORDER BY date_local""",
        (15, z, latest - dt.timedelta(days=365)))
    heating["demand"][z] = [
        {"date": str(r["date_local"]),
         "temp": f(r["temp_c_avg"], 1),
         "hdd": f(r["hdd"], 1),
         "heat_kwh": f(r["hdd"] * 1.0 / 3.0, 2),
         "heat_cost": f(r["hdd"] * 1.0 / 3.0 * r["total_consumer_sek_kwh"], 2)}
        for r in dm]
out["heating"] = heating
```

### 5.3 Heating model + when-to-heat chart — JavaScript (`app.js`)

```js
// Heating model: degree-days x heat-loss / COP x price
var HEAT = { ua: 1.0, cop: 3.0 };          // assumed home + heat pump
function heatKwh(tempC, setpointC) {
  return HEAT.ua * Math.max(0, setpointC - tempC) / HEAT.cop;
}
function heatCostSEK(tempC, price, setpointC) {
  return heatKwh(tempC, setpointC) * price;
}

// Recommended heat window = the cheapest consecutive hours
function heatWindow(prices) {
  var best = { sum: Infinity, from: 0, to: 0 };
  for (var start = 0; start < 24; start++) {
    var s = 0;
    for (var k = 0; k < 6; k++) s += prices[(start + k) % 24];   // 6-hour window
    if (s < best.sum) best = { sum: s, from: start, to: (start + 6) % 24 };
  }
  return best;
}

// When-to-heat chart: 24-hour price curve, green (cheap) -> red (dear)
function renderWhenToHeat() {
  var prices = DATA.heating.hourly[zone];
  var lo = Math.min.apply(null, prices), hi = Math.max.apply(null, prices);
  echarts.init(document.getElementById("when-chart")).setOption({
    xAxis: { type: "category",
             data: prices.map(function (p, h) { return h + ":00"; }) },
    yAxis: { type: "value", name: "SEK/kWh" },
    series: [{
      type: "bar", barWidth: "70%",
      data: prices.map(function (p) {
        return { value: p,
                 itemStyle: { color: ramp((p - lo) / (hi - lo)) } };  // green -> red
      })
    }]
  });
}
```

### 5.4 Page section — HTML (`index.html`)

```html
<section class="heating">
  <div class="wrap">
    <div class="section-head" data-reveal>
      <p class="eyebrow">Warm your home for less</p>
      <h2>Heat with cheap electricity</h2>
      <p class="lede">Heating is your biggest winter cost, and prices swing through the
        day. Heat when it is cheap and coast when it is not.</p>
    </div>

    <div class="heat-grid">
      <div class="well" data-reveal>
        <div class="well-head">
          <p class="ctitle">When to heat</p>
          <p class="small">typical day · SEK/kWh</p>
        </div>
        <div id="when-chart" class="chart"></div>
        <p class="chart-note" id="heat-window"></p>
      </div>

      <div class="well" data-reveal>
        <div class="well-head">
          <p class="ctitle">What heating costs</p>
          <p class="small">on a cold day</p>
        </div>
        <label for="setpoint">Comfort setpoint</label>
        <input id="setpoint" type="range" min="19" max="23" step="0.5" value="21">
        <div id="heat-cost"></div>
        <p class="chart-note">Assumes a typical home and a heat pump (COP 3). Adjusts with
          the setpoint: each degree lower saves energy.</p>
      </div>
    </div>
  </div>
</section>
```

---

## 6. Expected value

- **Direct savings for users.** Shifting heating from a ~1.39 SEK/kWh peak to a ~0.65 SEK/kWh trough roughly halves the cost of that heat. Even shifting part of the load saves real money over a Swedish winter.
- **Makes the platform actionable.** It turns "here is the price" into "here is what to do" — the natural next step for a site whose stated goal is to help people *plan when to use electricity*.
- **On-brand and differentiated.** Few price trackers connect the price to the household's biggest load (heating). It deepens the "plan your use" story already on the site.
- **Cheap to build and run.** Fully client-side, reuses the nightly pipeline and existing data, zero infrastructure cost.

---

## 7. Assumptions & next steps

**Assumptions (clearly labelled in the UI):**
- Typical home heat-loss factor (`UA = 1.0 kWh/°C·day`) and heat-pump efficiency (`COP = 3.0`). These are adjustable and shown as assumptions.
- Comfort setpoint defaults to 21 °C and is user-adjustable (19–23 °C).
- The heating model is indicative; the *shape* (cold = costly, cheap hours = cheap heat) is the robust, decision-relevant part.

**Open decisions (to confirm before build):**
1. Personalisation: setpoint slider + assumed home *(recommended)*, or full home inputs (size / insulation / heating type)?
2. Zone scope: all zones SE1–SE4 *(recommended — works with the zone selector, uses `fact_daily` temperature)*, or just SE3/SE4 (the `thermostat_dataset_stockholm` zones)?
3. Emphasis: lead with the **when-to-heat** curve *(recommended)*, with heating cost as supporting context.

**Roadmap:**
- **v1 (this proposal):** when-to-heat curve + heating-cost estimate + setpoint slider + plan-ahead advice.
- **v2 (optional):** full home profile inputs, hourly price for *today* (not just the typical day), and a "pre-heat schedule" recommendation driven by the day-ahead forecast.

---

*Prepared as a feature proposal for `swedish-el-oss`. All figures are derived from the project's own data platform (`silver.entsoe_timeseries`, `gold.fact_daily`, `gold.price_forecast`).*
