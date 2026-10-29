// The Conditions section: switch between days, and draw the chart for the chosen measure.

// 1. the day buttons: show the panel of the day that was clicked
document.querySelectorAll(".pick").forEach(function (button) {
  button.addEventListener("click", function () {
    document.querySelectorAll(".pick").forEach(function (other) { other.classList.remove("active"); });
    button.classList.add("active");
    document.querySelectorAll(".day-panel").forEach(function (panel) {
      panel.hidden = panel.dataset.day !== button.dataset.day;
    });
  });
});

// 2. the chart
var data = JSON.parse(document.getElementById("chart-data").textContent);
var colors = { ink: "#12304d", muted: "#8a99a8", line: "#d5e1ec", temp: "#eda100", forecast: "#e34948", real: "#12304d", rain: "#3f6fb5", other: "#2a78d6" };
var chart = null;
var view = "actual";

// a dashed vertical line where the known days end and the forecast starts
var todayLine = {
  id: "todayLine",
  afterDraw: function (c) {
    var x = c.scales.x.getPixelForValue(data.known - 1);
    var ctx = c.ctx;
    ctx.save();
    ctx.strokeStyle = colors.muted;
    ctx.setLineDash([4, 4]);
    ctx.beginPath();
    ctx.moveTo(x, c.chartArea.top);
    ctx.lineTo(x, c.chartArea.bottom);
    ctx.stroke();
    ctx.fillStyle = colors.muted;
    ctx.font = "12px Rubik, sans-serif";
    ctx.fillText("last known day", x + 6, c.chartArea.top + 12);
    ctx.restore();
  }
};

function line(label, values, color, extra) {
  return Object.assign({ type: "line", label: label, data: values, borderColor: color, backgroundColor: color, borderWidth: 2.5, pointRadius: 0, tension: 0.35, spanGaps: false }, extra || {});
}

function temperatureSets() {
  if (view === "feels") {
    return {
      sets: [
        line("Feels like", data.feels, colors.temp, { fill: "origin", backgroundColor: "rgba(237, 161, 0, 0.15)" }),
        line("Usual for the date", data.usual, colors.muted, { borderDash: [3, 4], borderWidth: 1.5 })
      ],
      unit: data.unit,
      note: "Feels like (apparent temperature) from the measured humidity and wind on known days, and the usual humidity and wind on forecast days."
    };
  }
  var sets = [
    line("Range (95 %)", data.high, "rgba(227, 73, 72, 0.15)", { fill: "+1", borderWidth: 0 }),
    line("", data.low, "rgba(227, 73, 72, 0.15)", { borderWidth: 0 }),
    line("Measured", data.temp, colors.temp, { fill: "origin", backgroundColor: "rgba(237, 161, 0, 0.15)" }),
    line("Forecast", data.forecast, colors.forecast, { borderDash: [6, 5] }),
    line("Usual for the date", data.usual, colors.muted, { borderDash: [3, 4], borderWidth: 1.5 })
  ];
  if (data.real) {
    sets.push(line("What really happened", data.real, colors.real, { pointRadius: 3 }));
  }
  return {
    sets: sets,
    unit: data.unit,
    note: "Daily average. The forecast (dashed) starts from the last known day and slides back toward the usual value for the date; the shaded band is its 95 % range."
  };
}

function measureSets(metric) {
  if (metric === "rain") {
    return {
      sets: [
        // a rain day starts at 1 mm (as in the notebooks); smaller amounts are light grey
        { type: "bar", label: "Rain", data: data.rain, backgroundColor: data.rain.map(function (v) { return v !== null && v >= 1 ? colors.rain : "#c9d6e3"; }), borderRadius: 4 },
        line("Rain day (1 mm)", data.rain.map(function (v) { return v === null ? null : 1; }), colors.forecast, { borderDash: [4, 4], borderWidth: 1.5 })
      ],
      unit: "mm",
      // the scale always goes up to at least 5 mm, so tiny amounts stay tiny
      yMin: 0,
      yMax: 5,
      note: "Daily rain on the known days. NASA's model often gives tiny amounts (under 1 mm) on dry days; the project counts a rain day only from 1 mm. The model does not forecast rain amounts; see the chance of rain for each day above."
    };
  }
  var names = { humidity: ["Humidity", "%"], wind: ["Wind", "km/h"], pressure: ["Pressure", "hPa"] };
  return {
    sets: [
      line(names[metric][0], data[metric], colors.other, { fill: "origin", backgroundColor: "rgba(42, 120, 214, 0.12)" }),
      line("Usual for the date", data[metric + "_usual"], colors.muted, { borderDash: [3, 4], borderWidth: 1.5 })
    ],
    unit: names[metric][1],
    note: names[metric][0] + " on the known days, next to the usual value for each date (1990–2019). The model forecasts temperature only."
  };
}

function draw() {
  var metric = document.getElementById("metric").value;
  document.getElementById("temp-toggle").hidden = metric !== "temp";
  var chosen = metric === "temp" ? temperatureSets() : measureSets(metric);
  document.getElementById("chart-note").textContent = chosen.note;

  if (chart) { chart.destroy(); }
  chart = new Chart(document.getElementById("conditions-chart"), {
    data: { labels: data.labels, datasets: chosen.sets },
    plugins: [todayLine],
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: {
        legend: { labels: { filter: function (item) { return item.text !== ""; }, color: colors.ink, usePointStyle: true, boxHeight: 6 } },
        tooltip: { callbacks: { label: function (item) { return item.raw === null ? null : item.dataset.label + ": " + item.raw + " " + chosen.unit; } } }
      },
      scales: {
        x: { grid: { display: false }, ticks: { color: colors.muted, maxRotation: 0, autoSkipPadding: 12 } },
        y: { position: "right", min: chosen.yMin, suggestedMax: chosen.yMax, grid: { color: colors.line }, ticks: { color: colors.muted, callback: function (v) { return v + " " + chosen.unit; } } }
      }
    }
  });
}

document.getElementById("metric").addEventListener("change", draw);
document.querySelectorAll("#temp-toggle button").forEach(function (button) {
  button.addEventListener("click", function () {
    view = button.dataset.view;
    document.querySelectorAll("#temp-toggle button").forEach(function (other) { other.classList.remove("active"); });
    button.classList.add("active");
    draw();
  });
});

draw();