const map = L.map("map").setView([37.7749, -122.4194], 13);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap",
}).addTo(map);

const cameraLayer = L.layerGroup().addTo(map);
let youMarker = null;
let lastCoords = null;
let presets = [];
let activePreset = null;

const colors = {
  openstreetmap: "#5ee0a0",
  flock: "#ff8a5b",
  news: "#7ab8ff",
  seed: "#9aa4b2",
  user_report: "#d4a5ff",
};

function $(id) {
  return document.getElementById(id);
}

function setBusy(on, label) {
  const busy = $("busy");
  busy.textContent = label || "Working…";
  busy.classList.toggle("hidden", !on);
  document.querySelectorAll("button").forEach((button) => {
    button.disabled = on;
  });
}

function markerColor(camera) {
  const manufacturer = (camera.manufacturer || "").toLowerCase();
  if (manufacturer.startsWith("flock")) return colors.flock;
  return colors[camera.source] || colors.openstreetmap;
}

function markerFor(camera) {
  return L.circleMarker([camera.lat, camera.lon], {
    radius: 7,
    color: markerColor(camera),
    fillColor: markerColor(camera),
    fillOpacity: 0.9,
    weight: 1,
  }).bindPopup(
    `<strong>${escapeHtml(camera.manufacturer || "ALPR")}</strong><br/>` +
      `${escapeHtml(camera.street || camera.city || "Mapped location")}<br/>` +
      `source: ${escapeHtml(camera.source)} · confidence: ${escapeHtml(camera.confidence || "n/a")}` +
      (camera.source_url
        ? `<br/><a href="${camera.source_url}" target="_blank" rel="noopener">OpenStreetMap</a>`
        : "")
  );
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;");
}

function drawCameras(cameras) {
  cameraLayer.clearLayers();
  cameras.forEach((camera) => markerFor(camera).addTo(cameraLayer));
  if (cameras.length) {
    const bounds = L.latLngBounds(cameras.map((camera) => [camera.lat, camera.lon]));
    map.fitBounds(bounds.pad(0.15));
  }
}

function standAt(lat, lon, label) {
  lastCoords = { lat, lon };
  if (youMarker) {
    youMarker.setLatLng([lat, lon]);
  } else {
    youMarker = L.circleMarker([lat, lon], {
      radius: 9,
      color: "#f2c14e",
      fillColor: "#f2c14e",
      fillOpacity: 1,
      weight: 2,
    }).addTo(map);
  }
  youMarker.bindPopup(label || "You (opt-in, not stored)").openPopup();
  map.setView([lat, lon], Math.max(map.getZoom(), 15));
}

function radiusMeters() {
  return Number($("radius").value);
}

function renderAlerts(alerts) {
  const list = $("alerts");
  list.innerHTML = "";
  (alerts || []).forEach((alert) => {
    const camera = alert.camera || {};
    const item = document.createElement("li");
    item.innerHTML =
      `<strong>${escapeHtml(Math.round(alert.distance_meters))} m ${escapeHtml(alert.bearing || "")}</strong> ` +
      `${escapeHtml(camera.manufacturer || "ALPR")}` +
      `<div>${escapeHtml(alert.message)}</div>`;
    list.appendChild(item);
  });
}

function renderSources(items) {
  const sources = $("sources");
  sources.innerHTML = "";
  (items || []).forEach((item) => {
    if (!item.url) return;
    const li = document.createElement("li");
    li.innerHTML = `<a href="${item.url}" target="_blank" rel="noopener">${escapeHtml(item.title || item.url)}</a>`;
    sources.appendChild(li);
  });
}

async function fetchJson(url, options) {
  const res = await fetch(url, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || res.statusText || "Request failed");
  }
  return data;
}

async function scan(body) {
  setBusy(true, "Scanning public OSM tags…");
  try {
    const data = await fetchJson("/api/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    drawCameras(data.cameras || []);
    $("stats").textContent =
      `${data.count} publicly mapped ALPR nodes` +
      (data.flock_count ? ` · ${data.flock_count} tagged Flock Safety` : "") +
      (data.place ? ` · ${data.place}` : "");
    $("response").textContent =
      `Scout/map scan complete. ${data.count} OpenStreetMap ALPR tags in range. ` +
      "Click the map or use a demo spot, then Check this spot.";
    $("trace").textContent = "Direct OSM scan (no LLM)";
    if (data.lat && data.lon) {
      map.setView([data.lat, data.lon], 13);
    }
    return data;
  } finally {
    setBusy(false);
  }
}

async function checkSpot(coords) {
  if (!coords) {
    $("response").textContent = "Stand somewhere first: click the map, a demo city, or Use my GPS.";
    return;
  }
  standAt(coords.lat, coords.lon);
  setBusy(true, "Checking nearby cameras…");
  try {
    const data = await fetchJson("/api/nearby", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        lat: coords.lat,
        lon: coords.lon,
        radius_meters: radiusMeters(),
      }),
    });
    $("response").textContent = data.narrative || "";
    $("trace").textContent = "Agent: proximity";
    renderAlerts(data.alerts || []);
    const cameras = (data.alerts || []).map((alert) => alert.camera).filter(Boolean);
    if (cameras.length) {
      cameras.forEach((camera) => markerFor(camera).addTo(cameraLayer));
    }
  } finally {
    setBusy(false);
  }
}

async function sendChat(message, coords) {
  setBusy(true, "Agents running…");
  try {
    const body = { message, radius_meters: radiusMeters() };
    if (coords) {
      body.lat = coords.lat;
      body.lon = coords.lon;
    }
    const data = await fetchJson("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    $("response").textContent = data.response || "";
    $("trace").textContent = data.agent_trace?.length ? `Agents: ${data.agent_trace.join(" → ")}` : "";
    renderSources([...(data.findings || []), ...(data.policy_notes || [])]);
    renderAlerts(data.alerts || []);
    if (data.cameras?.length) drawCameras(data.cameras);
    if (data.lat && data.lon) map.setView([data.lat, data.lon], 13);
  } finally {
    setBusy(false);
  }
}

function locate() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error("Geolocation is not available in this browser."));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => resolve({ lat: pos.coords.latitude, lon: pos.coords.longitude }),
      () => reject(new Error("Location permission was denied.")),
      { enableHighAccuracy: true, timeout: 10000 }
    );
  });
}

function renderPresets() {
  const root = $("presets");
  root.innerHTML = "";
  presets.forEach((preset) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip";
    chip.textContent = preset.name;
    chip.addEventListener("click", async () => {
      activePreset = preset;
      root.querySelectorAll(".chip").forEach((node) => node.classList.remove("active"));
      chip.classList.add("active");
      $("place").value = preset.name;
      map.setView([preset.lat, preset.lon], 13);
      await scan({
        lat: preset.lat,
        lon: preset.lon,
        place: preset.name,
        radius_meters: preset.scan_radius_meters,
      });
    });
    root.appendChild(chip);
  });
}

$("radius").addEventListener("input", () => {
  $("radius-label").textContent = $("radius").value;
});

$("scan-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const place = $("place").value.trim();
  if (!place) return;
  try {
    await scan({ place, radius_meters: 4000 });
  } catch (err) {
    $("response").textContent = String(err);
  }
});

$("stand-preset").addEventListener("click", () => {
  const preset = activePreset || presets[0];
  if (!preset) return;
  standAt(preset.stand_lat, preset.stand_lon, `You · ${preset.stand_label}`);
  $("response").textContent = `Standing at ${preset.stand_label}. Click Check this spot.`;
});

$("check-spot").addEventListener("click", async () => {
  try {
    await checkSpot(lastCoords);
  } catch (err) {
    $("response").textContent = String(err);
  }
});

$("near-me").addEventListener("click", async () => {
  try {
    const coords = await locate();
    standAt(coords.lat, coords.lon, "You (GPS, not stored)");
    await checkSpot(coords);
  } catch (err) {
    $("response").textContent = String(err);
  }
});

$("chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = $("message").value.trim();
  if (!message) return;
  try {
    await sendChat(message, lastCoords);
  } catch (err) {
    $("response").textContent = String(err);
  }
});

map.on("click", (event) => {
  standAt(event.latlng.lat, event.latlng.lng, "You (map click, not stored)");
});

async function boot() {
  try {
    const health = await fetchJson("/api/health");
    $("health").textContent = health.llm_enabled
      ? `LLM supervisor on (${health.provider}). Map scan works without a key.`
      : "No LLM key — map scan, proximity, and keyword agents still work.";
  } catch {
    $("health").textContent = "API unreachable.";
  }
  try {
    const data = await fetchJson("/api/presets");
    presets = data.presets || [];
    renderPresets();
  } catch {
    $("response").textContent = "Could not load demo cities.";
  }
  try {
    const stored = await fetchJson("/api/cameras");
    if (stored.cameras?.length) drawCameras(stored.cameras);
  } catch {
    /* seed load is optional */
  }
}

boot();
