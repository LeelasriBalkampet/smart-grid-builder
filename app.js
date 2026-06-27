// ── Detect backend URL (same origin in production, localhost in dev) ──
const API_BASE = (window.location.hostname === "localhost" || window.location.hostname === "127.0.0.1" || window.location.protocol === "file:")
  ? "http://127.0.0.1:5000"
  : "";   

const COLORS = {
  load:     "#f8fafc",
  solar:    "#f59e0b",
  wind:     "#06b6d4",
  battery:  "#8b5cf6",
  grid:     "#ef4444",
  ren:      "#6366f1",
  spilled:  "#f97316",
  stored:   "#8b5cf6",
  used:     "#10b981",
  level:    "#6366f1",
  ai:       "#3b82f6",
  cost:     "#ef4444",
  price:    "#f59e0b"
};

const charts = {};
window.customLoadProfile = null;

function mkChart(id, cfg) {
  if (charts[id]) charts[id].destroy();
  charts[id] = new Chart(document.getElementById(id), cfg);
}


Chart.defaults.color         = "#8b949e";
Chart.defaults.borderColor   = "#30363d";
Chart.defaults.font.family   = "Inter, sans-serif";
Chart.defaults.font.size     = 12;

// ── Shared line options factory ──
function lineOpts(labels, datasets, yLabel = "kW") {
  return {
    type: "line",
    data: { labels, datasets: datasets.map(d => ({
      tension: 0.4,
      pointRadius: 2,
      borderWidth: 2,
      fill: false,
      ...d,
    })) },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      interaction: { mode: "index", intersect: false },
      plugins: { legend: { labels: { usePointStyle: true, padding: 14 } } },
      scales: {
        x: { ticks: { maxTicksLimit: 12 } },
        y: { title: { display: true, text: yLabel } },
      },
    },
  };
}


function getParams() {
  return {
    load_value:      +document.getElementById("load-slider").value,
    use_solar:       document.getElementById("solar-toggle").checked,
    use_wind:        document.getElementById("wind-toggle").checked,
    use_battery:     document.getElementById("battery-toggle").checked,
    use_grid:        document.getElementById("grid-toggle").checked,
    solar_intensity: +document.getElementById("solar-slider").value,
    wind_speed:      +document.getElementById("wind-slider").value,
    custom_load_profile: window.customLoadProfile,
  };
}

// ── Debounce helper ──
let _timer;
function debounce(fn, ms = 500) {
  clearTimeout(_timer);
  _timer = setTimeout(fn, ms);
}

// ── Render charts from API response ──
function renderCharts(d) {
  const labels = d.t.map(h => `${h}:00`);
  const labelsNN = d.t_nn.map(h => `${h}:00`);

  // 1) Main: Energy Source Distribution
  mkChart("chart-main", lineOpts(labels, [
    { label: "Load",    borderColor: COLORS.load,    data: d.P_load },
    { label: "Solar",   borderColor: COLORS.solar,   data: d.P_solar,   borderDash: [5,3] },
    { label: "Wind",    borderColor: COLORS.wind,    data: d.P_wind,    borderDash: [5,3] },
    { label: "Battery", borderColor: COLORS.battery, data: d.battery_used, borderDash: [5,3] },
    { label: "Grid",    borderColor: COLORS.grid,    data: d.P_from_grid, borderDash: [5,3] },
  ]));

  // 2) Load vs Renewable
  mkChart("chart-lvr", lineOpts(labels, [
    { label: "Load",      borderColor: COLORS.load, data: d.P_load },
    { label: "Renewable", borderColor: COLORS.ren,  data: d.P_ren },
  ]));

  // 3) Grid vs Wasted
  mkChart("chart-gvw", lineOpts(labels, [
    { label: "Grid Usage",    borderColor: COLORS.grid,    data: d.P_from_grid },
    { label: "Wasted Energy", borderColor: COLORS.spilled, data: d.P_spilled, borderDash: [5,3] },
  ]));

  // 4 & 5) Battery (shown / hidden based on toggle)
  const battSec = document.getElementById("battery-section");
  if (d.use_battery) {
    battSec.style.display = "";
    mkChart("chart-bat-behav", lineOpts(labels, [
      { label: "Stored", borderColor: COLORS.stored, data: d.battery_store },
      { label: "Used",   borderColor: COLORS.used,   data: d.battery_used },
    ]));
    mkChart("chart-bat-level", lineOpts(labels, [
      { label: "Battery Level", borderColor: COLORS.level, data: d.battery_levels },
    ]));
  } else {
    battSec.style.display = "none";
  }

  // 6) AI Forecast
  mkChart("chart-ai", lineOpts(
    labels,
    [
      { label: "Actual Load",    borderColor: COLORS.load, data: d.P_load },
      { label: "Predicted Load", borderColor: COLORS.ai,  data: [null, ...d.predicted_nn], borderDash: [5,3] },
    ]
  ));

  // 7) Time-of-Use Cost
  if (d.hourly_costs && d.prices) {
    mkChart("chart-cost", {
      type: "bar",
      data: {
        labels,
        datasets: [
          { type: "line", label: "Grid Price ($/kWh)", borderColor: COLORS.price, data: d.prices, yAxisID: "y1", borderDash: [2,2] },
          { type: "bar", label: "Hourly Grid Cost ($)", backgroundColor: COLORS.cost, data: d.hourly_costs, yAxisID: "y" }
        ]
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          y: { title: { display: true, text: "Cost ($)" }, position: "left" },
          y1: { title: { display: true, text: "Price ($)" }, position: "right", grid: { drawOnChartArea: false } }
        }
      }
    });
  }
}

function updateSummary(d) {
  document.getElementById("s-load").textContent    = d.load_value + " kW";
  document.getElementById("s-solar").textContent   = d.use_solar   ? "ON" : "OFF";
  document.getElementById("s-wind").textContent    = d.use_wind    ? "ON" : "OFF";
  document.getElementById("s-battery").textContent = d.use_battery ? "ON" : "OFF";
  document.getElementById("s-grid").textContent    = d.use_grid    ? "ON" : "OFF";
  document.getElementById("s-cost").textContent    = "$" + (d.total_cost || 0).toFixed(2);
  document.getElementById("s-savings").textContent = "$" + (d.total_savings || 0).toFixed(2);

  const banner = document.getElementById("status-banner");
  if (d.total_unmet > 0) {
    banner.className = "banner banner-error";
    banner.textContent = `POWER CUT! Unserved Energy = ${d.total_unmet.toFixed(2)} kW`;
  } else {
    banner.className = "banner banner-success";
    banner.textContent = "All demand successfully met";
  }

  const aiInsightText = document.getElementById("ai-insight-text");
  if (aiInsightText && d.ai_insight) {
    aiInsightText.textContent = d.ai_insight;
  }
}

async function runSimulation() {
  try {
    const res = await fetch(`${API_BASE}/api/simulate`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(getParams()),
    });
    if (!res.ok) throw new Error("Server error " + res.status);
    const data = await res.json();
    renderCharts(data);
    updateSummary(data);
  } catch (err) {
    console.error("Simulation error:", err);
  }
}

// ── Fetch & display weather ──
async function loadWeather() {
  try {
    const res  = await fetch(`${API_BASE}/api/weather`);
    const data = await res.json();
    document.getElementById("temp-val").textContent = `${data.temp} °C`;
    document.getElementById("hum-val").textContent  = `${data.humidity}%`;
    // We could also show cloud cover and wind speed here, but they affect simulation in the background
  } catch {
    document.getElementById("temp-val").textContent = "30 °C";
    document.getElementById("hum-val").textContent  = "60%";
  }
}

// ── History & CSV ──
async function loadHistory() {
  try {
    const res = await fetch(`${API_BASE}/api/history`);
    const data = await res.json();
    const tbody = document.querySelector("#history-table tbody");
    tbody.innerHTML = "";
    data.forEach(row => {
      // The database saves in UTC. Add 'Z' so JS knows it's UTC and converts to local time.
      const date = new Date(row.timestamp.replace(" ", "T") + "Z");
      const localTime = date.toLocaleString();
      const tr = document.createElement("tr");
      tr.innerHTML = `
        <td>${localTime}</td>
        <td>${row.load_value.toFixed(1)}</td>
        <td>${row.total_unmet.toFixed(1)}</td>
        <td>$${row.total_cost.toFixed(2)}</td>
        <td class="success">$${row.total_savings.toFixed(2)}</td>
      `;
      tbody.appendChild(tr);
    });
  } catch (err) {
    console.error("Failed to load history", err);
  }
}

async function uploadCSV() {
  const fileInput = document.getElementById("csv-file-input");
  const resultDiv = document.getElementById("csv-upload-result");
  if (!fileInput.files.length) {
    resultDiv.innerHTML = "<span class='banner-error'>Please select a CSV file</span>";
    return;
  }
  
  const formData = new FormData();
  formData.append("file", fileInput.files[0]);
  
  try {
    resultDiv.innerHTML = "Uploading...";
    const res = await fetch(`${API_BASE}/api/upload-csv`, {
      method: "POST",
      body: formData
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Upload failed");
    
    resultDiv.innerHTML = `<span class='banner-success'>${data.message}. Avg Load: ${data.average_load.toFixed(1)}kW. Updating simulation...</span>`;
    
    // Store the custom profile so the simulation uses exactly these values
    window.customLoadProfile = data.load_profile;
    
    // Update the slider to reflect the average, but the simulation will use the custom profile array
    const loadSlider = document.getElementById("load-slider");
    loadSlider.value = data.suggested_load_value;
    document.getElementById("load-display").textContent = data.suggested_load_value.toFixed(1) + " (Custom CSV)";
    
    runSimulation();
  } catch(err) {
    resultDiv.innerHTML = `<span class='banner-error'>${err.message}</span>`;
  }
}

// ── Wire up all controls ──
function wireControls() {
  const loadSlider  = document.getElementById("load-slider");
  const solarSlider = document.getElementById("solar-slider");
  const windSlider  = document.getElementById("wind-slider");

  loadSlider.addEventListener("input", () => {
    window.customLoadProfile = null; // Clear custom profile when user manually changes slider
    document.getElementById("load-display").textContent = loadSlider.value;
    debounce(runSimulation);
  });
  solarSlider.addEventListener("input", () => {
    document.getElementById("solar-display").textContent = solarSlider.value;
    debounce(runSimulation);
  });
  windSlider.addEventListener("input", () => {
    document.getElementById("wind-display").textContent = windSlider.value;
    debounce(runSimulation);
  });

  ["solar-toggle","wind-toggle","battery-toggle","grid-toggle"].forEach(id => {
    document.getElementById(id).addEventListener("change", () => debounce(runSimulation));
  });
}

document.addEventListener("DOMContentLoaded", () => {
  wireControls();
  loadWeather();
  runSimulation();
  loadHistory();
  
  document.getElementById("refresh-history-btn").addEventListener("click", loadHistory);
  document.getElementById("upload-csv-btn").addEventListener("click", uploadCSV);
});
