/* Swedish EL — charts + interaction. Reads window.__DATA__ (see build_site.py).
   Concept "the honest line": solid ink = recorded, accent + soft band = forecast. */
(function () {
  "use strict";
  var D = window.__DATA__;
  var $ = function (s) { return document.querySelector(s); };
  var reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  if (!D) { document.getElementById("now-spot").textContent = "n/a"; return; }

  // ---- palette (must match styles.css) ----
  var C = {
    ink: "#0c1217", muted: "#566172", line: "#e2e7ee",
    accent: "#ff5a25", band: "rgba(255,90,37,0.16)",
    spot: "#ff5a25", tax: "#3d6fa6", grid: "#4e8c7a", vat: "#b9c2ce",
    cheap: "#2e8b6f", mid: "#e4a11b", dear: "#c0392b"
  };

  function fmt(v, n) { n = n == null ? 2 : n; return v == null ? "—" : Number(v).toLocaleString("en-SE", { minimumFractionDigits: n, maximumFractionDigits: n }); }
  function ramp(t) {
    t = Math.max(0, Math.min(1, t));
    var stops = [[46, 139, 111], [228, 161, 27], [192, 57, 43]];
    var seg = t < 0.5 ? 0 : 1, lt = t < 0.5 ? t * 2 : (t - 0.5) * 2;
    var a = stops[seg], b = stops[seg + 1];
    return "rgb(" + Math.round(a[0] + (b[0] - a[0]) * lt) + "," + Math.round(a[1] + (b[1] - a[1]) * lt) + "," + Math.round(a[2] + (b[2] - a[2]) * lt) + ")";
  }

  var zone = "SE4";
  var charts = {};

  function el(id) {
    if (charts[id]) return charts[id];
    var dom = document.getElementById(id);
    if (!dom || !window.echarts) return null;
    charts[id] = echarts.init(dom, null, { renderer: "canvas" });
    return charts[id];
  }

  // ---- the honest line (actual + forecast band). Used by hero + trend. ----
  function honestOption(z, windowDays) {
    var s = D.chart.series[z] || {};
    var dates = D.chart.dates, n = dates.length;
    // bridge the present so the line runs continuously into the forecast
    var aspot = s.actual_spot.slice(), fspot = s.fc_spot.slice(),
        fp10 = s.fc_spot_p10.slice(), fp90 = s.fc_spot_p90.slice();
    var k = -1;
    for (var i = 0; i < n; i++) if (aspot[i] != null) k = i;
    if (k >= 0 && fspot[k] == null) { fspot[k] = aspot[k]; fp10[k] = aspot[k]; fp90[k] = aspot[k]; }
    var band = fp10.map(function (v, i) { return (v == null || fp90[i] == null) ? null : fp90[i] - v; });

    var start = 0;
    if (windowDays && n > windowDays) start = n - windowDays;
    var cut = function (arr) { return arr.slice(start); };
    var xd = dates.slice(start);

    return {
      animation: !reduce, animationDuration: 900, animationEasing: "cubicOut",
      grid: { left: 6, right: 10, top: 14, bottom: 4, containLabel: true },
      tooltip: {
        trigger: "axis", backgroundColor: "#fff", borderColor: C.line, borderWidth: 1,
        textStyle: { color: C.ink, fontSize: 12 }, padding: [8, 12],
        valueFormatter: function (v) { return v == null ? "—" : fmt(v, 3) + " SEK/kWh"; }
      },
      xAxis: { type: "category", data: xd, boundaryGap: false, axisLine: { lineStyle: { color: C.line } }, axisLabel: { color: C.muted, fontSize: 11 }, axisTick: { show: false } },
      yAxis: { type: "value", scale: true, splitLine: { lineStyle: { color: C.line } }, axisLabel: { color: C.muted, fontSize: 11 } },
      series: [
        { name: "p10", type: "line", stack: "band", data: cut(fp10), lineStyle: { opacity: 0 }, areaStyle: { opacity: 0 }, symbol: "none", silent: true },
        { name: "range", type: "line", stack: "band", data: cut(band), lineStyle: { opacity: 0 }, areaStyle: { color: C.band }, symbol: "none", silent: true },
        { name: "Recorded", type: "line", data: cut(aspot), showSymbol: false, lineStyle: { color: C.ink, width: 2.2 }, emphasis: { disabled: true }, connectNulls: false },
        { name: "Forecast", type: "line", data: cut(fspot), showSymbol: false, lineStyle: { color: C.accent, width: 2.2, type: "dashed" }, connectNulls: true }
      ]
    };
  }

  function renderHero() {
    var c = el("hero-chart"); if (c) c.setOption(honestOption(zone, 120), true);
  }

  function renderTrend() {
    var c = el("trend-chart"); if (c) c.setOption(honestOption(zone, 0), true);
    $("#trend-title").textContent = "Spot price and forecast · " + zone;
  }

  // ---- hero now numbers ----
  function countUp(node, to, n) {
    if (to == null) { node.textContent = "—"; return; }
    if (reduce) { node.textContent = fmt(to, n); return; }
    var from = 0, t0 = performance.now(), dur = 750;
    (function step(t) {
      var p = Math.min(1, (t - t0) / dur), e = 1 - Math.pow(1 - p, 3);
      node.textContent = fmt(from + (to - from) * e, n);
      if (p < 1) requestAnimationFrame(step);
    })(t0);
  }
  function renderNow() {
    var w = D.now[zone] || {};
    $("#now-zone").textContent = zone;
    $("#hero-zone-label").textContent = zone + " · SEK/kWh";
    countUp($("#now-spot"), w.spot, 2);
    countUp($("#now-bill"), w.bill, 2);
    $("#now-date").textContent = w.date || "—";
  }

  // ---- horizon cards ----
  function renderHorizon() {
    var h = D.horizon[zone] || {}, order = [["day", "Next day"], ["week", "Next week"], ["month", "Next month"]];
    $("#horizon-grid").innerHTML = order.map(function (o) {
      var d = h[o[0]] || {};
      return '<article class="hcard" data-reveal>' +
        '<p class="h-when">' + o[1] + (d.start ? " · " + d.start : "") + '</p>' +
        '<div class="h-row"><span class="h-k">Spot price</span><span><span class="h-v tnum">' + fmt(d.spot) + '</span>' +
          '<div class="h-range">range ' + fmt(d.spot_p10) + ' - ' + fmt(d.spot_p90) + '</div></span></div>' +
        '<div class="h-row"><span class="h-k">All-in bill</span><span><span class="h-v tnum">' + fmt(d.bill) + '</span>' +
          '<div class="h-range">range ' + fmt(d.bill_p10) + ' - ' + fmt(d.bill_p90) + '</div></span></div>' +
        '</article>';
    }).join("");
  }

  // ---- bill breakdown ----
  function renderBill() {
    var b = D.bill[zone] || {};
    var comps = [["spot", "Spot price", "The market part. Moves every day.", C.spot],
                 ["tax", "Energy tax", "Fixed state tax on electricity.", C.tax],
                 ["grid_fee", "Grid fee", "Paying for the network to your home.", C.grid],
                 ["vat", "VAT", "25% on top of everything.", C.vat]];
    $("#bill-list").innerHTML = comps.map(function (c) {
      return '<li><span class="sw" style="background:' + c[3] + '"></span>' +
        '<span class="nm">' + c[1] + '<span class="desc">' + c[2] + '</span></span>' +
        '<span class="vv tnum">' + fmt(b[c[0]]) + '</span></li>';
    }).join("");
    $("#bill-total").textContent = fmt(b.total) + " SEK/kWh";

    var chart = el("bill-chart");
    if (chart) chart.setOption({
      animation: !reduce, grid: { left: 6, right: 10, top: 8, bottom: 4, containLabel: true },
      tooltip: { trigger: "axis", axisPointer: { type: "shadow" }, valueFormatter: function (v) { return fmt(v, 3); } },
      xAxis: { type: "value", splitLine: { lineStyle: { color: C.line } }, axisLabel: { color: C.muted, fontSize: 11 } },
      yAxis: { type: "category", data: [zone], axisLabel: { color: C.ink, fontSize: 13, fontWeight: 600 }, axisLine: { show: false }, axisTick: { show: false } },
      series: comps.map(function (c) {
        return { name: c[1], type: "bar", stack: "bill", barWidth: 46, itemStyle: { color: c[3] }, data: [b[c[0]] || 0] };
      })
    }, true);
  }

  // ---- plan your use ----
  function renderPlan() {
    var p = D.plan[zone] || {};
    $("#plan-hour").textContent = p.cheapest_hour != null ? ("0" + p.cheapest_hour).slice(-2) : "—";
    $("#plan-offpeak").textContent = fmt(p.offpeak);
    $("#plan-peak").textContent = fmt(p.peak);
    var dow = p.day_of_week || [], names = p.dow_names || [];
    var minI = -1, minV = Infinity;
    dow.forEach(function (v, i) { if (v != null && v < minV) { minV = v; minI = i; } });
    $("#plan-cheapday").textContent = minI >= 0 ? names[minI] : "—";

    var vals = dow.filter(function (v) { return v != null; });
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    var chart = el("dow-chart");
    if (chart) chart.setOption({
      animation: !reduce, grid: { left: 6, right: 10, top: 12, bottom: 4, containLabel: true },
      tooltip: { valueFormatter: function (v) { return fmt(v, 3) + " SEK/kWh"; } },
      xAxis: { type: "category", data: names, axisLine: { lineStyle: { color: C.line } }, axisLabel: { color: C.muted, fontSize: 11 }, axisTick: { show: false } },
      yAxis: { type: "value", scale: true, splitLine: { lineStyle: { color: C.line } }, axisLabel: { color: C.muted, fontSize: 11 } },
      series: [{
        name: "Avg spot", type: "bar", barWidth: "56%",
        data: dow.map(function (v, i) {
          var t = hi > lo ? (v - lo) / (hi - lo) : 0;
          return { value: v, itemStyle: { color: ramp(t), borderRadius: [6, 6, 0, 0] } };
        })
      }]
    }, true);
  }

  // ---- zone comparison bars (HTML) ----
  function renderZones() {
    var vals = D.meta.zones.map(function (z) { return (D.now[z] || {}).spot; });
    var lo = Math.min.apply(null, vals), hi = Math.max.apply(null, vals);
    $("#zone-bars").innerHTML = D.meta.zones.map(function (z, i) {
      var v = vals[i], t = hi > lo ? (v - lo) / (hi - lo) : 0.5;
      return '<div class="zone-row"><span class="z">' + z + '</span>' +
        '<div class="track"><div class="fill" data-w="' + Math.round(18 + (v / hi) * 82) + '" style="background:' + ramp(t) + '"></div></div>' +
        '<span class="val tnum">' + fmt(v) + '</span></div>';
    }).join("");
    requestAnimationFrame(function () {
      document.querySelectorAll(".zone-row .fill").forEach(function (f) {
        f.style.transform = "scaleX(" + parseFloat(f.getAttribute("data-w")) / 100 + ")";
      });
    });
  }

  function renderAll() {
    renderNow(); renderHero(); renderTrend(); renderHorizon();
    renderBill(); renderPlan(); renderZones();
    Object.keys(charts).forEach(function (k) { charts[k].resize(); });
  }

  // ---- zone selector ----
  document.querySelectorAll(".zone-nav button").forEach(function (btn) {
    btn.addEventListener("click", function () {
      zone = btn.getAttribute("data-zone");
      document.querySelectorAll(".zone-nav button").forEach(function (b) {
        b.setAttribute("aria-pressed", String(b === btn));
      });
      renderAll();
    });
  });

  // ---- footer ----
  $("#foot-sources").innerHTML = (D.meta.sources || []).map(function (s) { return "<li>" + s + "</li>"; }).join("");
  $("#foot-generated").textContent = D.meta.generated_at || "—";

  // ---- motion: a staggered entrance (native scroll; never leaves content hidden) ----
  function initMotion() {
    var els = Array.prototype.slice.call(document.querySelectorAll("[data-reveal]"));
    if (reduce) { els.forEach(function (e) { e.classList.add("is-in"); }); return; }
    function revealAll() {
      els.forEach(function (e, i) {
        e.style.transitionDelay = Math.min(i, 12) * 55 + "ms";
        e.classList.add("is-in");
      });
    }
    if (document.readyState === "complete") revealAll();
    else window.addEventListener("load", revealAll);
    setTimeout(revealAll, 1200); // safety: never leave content hidden
  }

  // ---- boot ----
  renderAll();
  initMotion();
  window.addEventListener("resize", function () {
    Object.keys(charts).forEach(function (k) { charts[k].resize(); });
  });
})();
