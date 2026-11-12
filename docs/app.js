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
  var dvKey = "wind_now";
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

  // ---- drivers: situation + correlation to the spot price ----
  function renderDrivers() {
    var dr = D.drivers; if (!dr) return;
    var groups = [
      { label: "Weather", items: ["temp_now", "wind_now", "precip_now"] },
      { label: "Hydro", items: ["discharge_now"] },
      { label: "Gas", items: ["gas_asof"] }
    ];
    $("#driver-cards").innerHTML = groups.map(function (g) {
      var rows = g.items.map(function (fk) {
        var meta = dr.meta[fk] || {}, latest = (dr.latest[zone] || {})[fk] || {}, r = (dr.correlation[zone] || {})[fk];
        var rTxt = (r == null ? "—" : "r " + (r >= 0 ? "+" : "") + fmt(r, 2));
        return '<li><span class="dc-nm">' + meta.label + '</span>' +
          '<span class="dc-v tnum">' + fmt(latest.v, 1) + ' <small>' + meta.unit + '</small></span>' +
          '<span class="dc-r ' + (r >= 0 ? "pos" : "neg") + '">' + rTxt + '</span></li>';
      }).join("");
      return '<article class="dcard" data-reveal><p class="dc-h">' + g.label + '</p><ul class="dc-list">' + rows + '</ul></article>';
    }).join("");
  }

  function renderCorr() {
    var c = el("corr-chart"); if (!c || !D.drivers) return;
    var dr = D.drivers;
    var corr = (dr.correlation || {})[zone] || {};
    var items = Object.keys(dr.meta).map(function (fk) {
      return { label: dr.meta[fk].label, r: corr[fk] || 0 };
    }).sort(function (a, b) { return a.r - b.r; });
    c.setOption({
      animation: !reduce,
      grid: { left: 6, right: 18, top: 8, bottom: 4, containLabel: true },
      tooltip: { valueFormatter: function (v) { return "r = " + fmt(v, 2); } },
      xAxis: { type: "value", min: -1, max: 1, splitLine: { lineStyle: { color: C.line } }, axisLabel: { color: C.muted, fontSize: 11 } },
      yAxis: { type: "category", data: items.map(function (i) { return i.label; }), axisLine: { show: false }, axisTick: { show: false }, axisLabel: { color: C.ink, fontSize: 12 } },
      series: [{
        type: "bar", barWidth: 15,
        data: items.map(function (i) {
          return { value: i.r, itemStyle: { color: i.r >= 0 ? C.dear : C.cheap, borderRadius: 3 } };
        })
      }]
    }, true);
  }

  function renderCorrNote() {
    var dr = D.drivers, note = $("#corr-take");
    if (!dr || !note) return;
    var corr = (dr.correlation || {})[zone] || {};
    var pos = null, neg = null;
    Object.keys(dr.meta).forEach(function (fk) {
      var r = corr[fk]; if (r == null) return;
      var lab = (dr.meta[fk].label || "").toLowerCase();
      if (r > 0 && (!pos || r > pos.r)) pos = { label: lab, r: r };
      if (r < 0 && (!neg || r < neg.r)) neg = { label: lab, r: r };
    });
    var s = "";
    if (pos && neg) s = "In " + zone + ", " + pos.label + " pushes electricity prices up the most, while " + neg.label + " pulls them down.";
    else if (pos) s = "In " + zone + ", " + pos.label + " pushes electricity prices up the most.";
    else if (neg) s = "In " + zone + ", " + neg.label + " pulls electricity prices down.";
    note.textContent = s;
  }

  function renderDriverChart() {
    var c = el("dv-chart"); if (!c || !D.drivers) return;
    var t = (D.drivers.trend || {})[zone] || {};
    var meta = D.drivers.meta[dvKey] || {};
    $("#dv-label").textContent = (meta.label || "").toLowerCase();
    c.setOption({
      animation: !reduce,
      grid: { left: 6, right: 6, top: 22, bottom: 4, containLabel: true },
      tooltip: { trigger: "axis" },
      legend: { data: ["Spot price", meta.label || ""], textStyle: { color: C.muted, fontSize: 11 } },
      xAxis: { type: "category", data: t.dates || [], boundaryGap: false, axisLabel: { color: C.muted, fontSize: 11 }, axisLine: { lineStyle: { color: C.line } }, axisTick: { show: false } },
      yAxis: [
        { type: "value", scale: true, splitLine: { lineStyle: { color: C.line } }, axisLabel: { color: C.muted, fontSize: 11 } },
        { type: "value", scale: true, splitLine: { show: false }, axisLabel: { color: C.muted, fontSize: 11 } }
      ],
      series: [
        { name: "Spot price", type: "line", data: t.spot || [], showSymbol: false, lineStyle: { color: C.accent, width: 2 }, yAxisIndex: 0 },
        { name: meta.label || "", type: "line", data: t[dvKey] || [], showSymbol: false, lineStyle: { color: C.ink, width: 1.8 }, yAxisIndex: 1 }
      ]
    }, true);
  }

  function renderDvSeg() {
    if (!D.drivers) return;
    $("#dv-seg").innerHTML = Object.keys(D.drivers.meta).map(function (fk) {
      return '<button type="button" data-dv="' + fk + '" aria-pressed="' + (fk === dvKey) + '">' + D.drivers.meta[fk].label + '</button>';
    }).join("");
    $("#dv-seg").querySelectorAll("button").forEach(function (b) {
      b.addEventListener("click", function () {
        dvKey = b.getAttribute("data-dv");
        $("#dv-seg").querySelectorAll("button").forEach(function (x) { x.setAttribute("aria-pressed", String(x === b)); });
        renderDriverChart();
      });
    });
  }

  function renderAll() {
    renderNow(); renderHero(); renderTrend(); renderHorizon();
    renderBill(); renderPlan(); renderZones();
    renderDrivers(); renderCorr(); renderCorrNote(); renderDriverChart();
    Object.keys(charts).forEach(function (k) { charts[k].resize(); });
  }

  // ---- postcode -> zone lookup (source: Svenska kraftnat natomraden / Ei) ----
  function inRanges(v, rs) { for (var i = 0; i < rs.length; i++) if (v >= rs[i][0] && v <= rs[i][1]) return true; return false; }
  var ZONE_MAIN = { SE1: [[94, 98]], SE2: [[82, 91]], SE3: [[10, 19], [40, 78], [80, 80]], SE4: [[20, 32], [34, 39]] };
  var ZONE_DEC3 = { SE1: [[931, 939]], SE2: [[816, 817], [921, 925]], SE3: [[332, 332], [790, 797], [811, 815], [818, 819]], SE4: [[331, 331], [333, 335]] };
  var ZONE_UNDEC3 = [[330, 330], [336, 339], [798, 799], [810, 810], [920, 920], [926, 930]];
  var ZONE_DESC = { SE1: "northern Sweden", SE2: "north-central Sweden", SE3: "central Sweden (Stockholm)", SE4: "southern Sweden (Malmö)" };
  function zoneForPostcode(pc) {
    var s = String(pc || "").replace(/\D/g, "");
    if (s.length < 4) return { error: "Enter a 4-digit Swedish postcode." };
    var p2 = parseInt(s.slice(0, 2), 10), p3 = parseInt(s.slice(0, 3), 10);
    for (var z in ZONE_DEC3) if (inRanges(p3, ZONE_DEC3[z])) return { zone: z };
    if (inRanges(p3, ZONE_UNDEC3)) return { boundary: true };
    for (var z2 in ZONE_MAIN) if (inRanges(p2, ZONE_MAIN[z2])) return { zone: z2 };
    return { error: "No zone match for this postcode. Check your electricity bill (elnätsfaktura)." };
  }

  function setZone(z) {
    zone = z;
    document.querySelectorAll(".zone-nav button").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.getAttribute("data-zone") === z));
    });
    renderAll();
    document.querySelectorAll("[data-reveal]").forEach(function (e) { e.classList.add("is-in"); });
    var ez = $("#est-zone"); if (ez) ez.textContent = z;
    runEstimate();
  }

  // ---- find-your-zone widget ----
  function initFinder() {
    var input = $("#pc-input"), btn = $("#pc-btn"), res = $("#pc-result");
    if (!input || !btn) return;
    function lookup() {
      var r = zoneForPostcode(input.value);
      if (r.error) { res.textContent = r.error; res.className = "finder-result is-bad"; }
      else if (r.boundary) {
        res.textContent = "This postcode is near a zone boundary. Confirm your zone on your electricity bill (elnätsfaktura).";
        res.className = "finder-result is-warn";
      } else {
        res.textContent = "You're in " + r.zone + " — " + ZONE_DESC[r.zone] + ". Charts updated below.";
        res.className = "finder-result is-ok";
        setZone(r.zone);
      }
    }
    btn.addEventListener("click", lookup);
    input.addEventListener("keydown", function (e) { if (e.key === "Enter") { e.preventDefault(); lookup(); } });
  }

  // ---- bill estimator ----
  function runEstimate() {
    var be = D.bill_est, out = $("#est-result"); if (!be || !out) return;
    var active = document.querySelector(".est-mode button[aria-pressed='true']");
    var mode = active ? active.getAttribute("data-mode") : "bill";
    var usage = 0;
    if (mode === "usage") {
      usage = parseFloat($("#est-usage").value) || 0;
    } else {
      var bill = parseFloat($("#est-bill").value) || 0;
      var period = parseInt($("#est-period").value, 10) || 1;
      var mp = (be.monthly || {})[zone] || {};
      var keys = Object.keys(mp).sort();
      var complete = keys.slice(0, -1);
      var refKeys = complete.slice(-period);
      var refPrice = refKeys.length ? refKeys.reduce(function (s, k) { return s + mp[k]; }, 0) / refKeys.length : 0;
      usage = refPrice ? (bill / period) / refPrice : 0;
    }
    if (!usage || usage <= 0) {
      out.innerHTML = '<p class="est-hint">Enter your ' + (mode === "usage" ? "monthly usage" : "last bill") + ' to see an estimate.</p>';
      return;
    }
    var fc = (be.forecast || {})[zone] || {}, cur = fc.current || {}, nxt = fc.next || {};
    out.innerHTML =
      '<div class="est-row"><div><p class="est-k">' + (cur.label || "This month") + '</p><p class="est-sub">at ' + fmt(cur.price, 2) + ' SEK/kWh</p></div>' +
      '<p class="est-v tnum">' + fmt(usage * (cur.price || 0), 0) + '<small>SEK</small></p></div>' +
      '<div class="est-row"><div><p class="est-k">' + (nxt.label || "Next month") + '</p><p class="est-sub">at ' + fmt(nxt.price, 2) + ' SEK/kWh · range ' + fmt(usage * (nxt.p10 || 0), 0) + '–' + fmt(usage * (nxt.p90 || 0), 0) + '</p></div>' +
      '<p class="est-v tnum">' + fmt(usage * (nxt.price || 0), 0) + '<small>SEK</small></p></div>' +
      '<p class="est-usage">Based on about ' + fmt(usage, 0) + ' kWh per month in ' + zone + '. Assumptions: steady usage, no fixed grid fee.</p>';
  }
  function initEstimator() {
    var go = $("#est-go"); if (!go) return;
    document.querySelectorAll(".est-mode button").forEach(function (b) {
      b.addEventListener("click", function () {
        var mode = b.getAttribute("data-mode");
        document.querySelectorAll(".est-mode button").forEach(function (x) { x.setAttribute("aria-pressed", String(x === b)); });
        $("#field-bill").hidden = (mode !== "bill");
        $("#field-period").hidden = (mode !== "bill");
        $("#field-usage").hidden = (mode !== "usage");
        runEstimate();
      });
    });
    go.addEventListener("click", runEstimate);
  }

  // ---- zone selector ----
  document.querySelectorAll(".zone-nav button").forEach(function (btn) {
    btn.addEventListener("click", function () { setZone(btn.getAttribute("data-zone")); });
  });

  // ---- footer ----
  $("#foot-sources").innerHTML = (D.meta.sources || []).map(function (s) { return "<li>" + s + "</li>"; }).join("");
  $("#foot-generated").textContent = D.meta.generated_at || "—";

  // ---- motion: a staggered entrance (native scroll; never leaves content hidden) ----
  function initMotion() {
    document.documentElement.classList.add("js-motion");
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
  renderDvSeg();
  initFinder();
  initEstimator();
  initMotion();
  window.addEventListener("resize", function () {
    Object.keys(charts).forEach(function (k) { charts[k].resize(); });
  });
})();
