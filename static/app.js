const map = L.map("map").setView([37.7749, -122.4194], 13);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap",
}).addTo(map);

const cameraLayer = L.layerGroup().addTo(map);
let youMarker = null;
let accuracyCircle = null;
let lastCoords = null;
let presets = [];
let activePreset = null;
let loadedCameras = [];
let lastScanCenter = null;
let watchId = null;
let demoTimer = null;
let tracking = false;
let followMode = null;
let lastAlertKey = "";
let scanningAround = false;

const RESCAN_METERS = 1800;
const GPS_OPTIONS = { enableHighAccuracy: true, maximumAge: 2000, timeout: 15000 };
const DEMO_PATH = [
  [37.7797, -122.3981],
  [37.7804, -122.3994],
  [37.7811, -122.4008],
  [37.7818, -122.4021],
  [37.7826, -122.4034],
  [37.7834, -122.4046],
];

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
    if (button.id === "stop-follow" || button.id === "follow-me" || button.id === "demo-walk") {
      return;
    }
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

function haversineMeters(lat1, lon1, lat2, lon2) {
  const toRad = (deg) => (deg * Math.PI) / 180;
  const dPhi = toRad(lat2 - lat1);
  const dLambda = toRad(lon2 - lon1);
  const a =
    Math.sin(dPhi / 2) ** 2 +
    Math.cos(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.sin(dLambda / 2) ** 2;
  return 2 * 6371000 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
}

function compassBearing(lat1, lon1, lat2, lon2) {
  const toRad = (deg) => (deg * Math.PI) / 180;
  const y = Math.sin(toRad(lon2 - lon1)) * Math.cos(toRad(lat2));
  const x =
    Math.cos(toRad(lat1)) * Math.sin(toRad(lat2)) -
    Math.sin(toRad(lat1)) * Math.cos(toRad(lat2)) * Math.cos(toRad(lon2 - lon1));
  const degrees = ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360;
  return ["N", "NE", "E", "SE", "S", "SW", "W", "NW"][Math.floor((degrees + 22.5) / 45) % 8];
}

function drawCameras(cameras, fit = true) {
  loadedCameras = cameras || [];
  cameraLayer.clearLayers();
  loadedCameras.forEach((camera) => markerFor(camera).addTo(cameraLayer));
  if (fit && loadedCameras.length && !tracking) {
    const bounds = L.latLngBounds(loadedCameras.map((camera) => [camera.lat, camera.lon]));
    map.fitBounds(bounds.pad(0.15));
  }
}

function standAt(lat, lon, label, accuracy) {
  lastCoords = { lat, lon, accuracy };
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
  youMarker.bindPopup(label || "You (opt-in, not stored)");
  if (typeof accuracy === "number" && accuracy > 0) {
    if (accuracyCircle) {
      accuracyCircle.setLatLng([lat, lon]).setRadius(accuracy);
    } else {
      accuracyCircle = L.circle([lat, lon], {
        radius: accuracy,
        color: "#f2c14e",
        weight: 1,
        fillColor: "#f2c14e",
        fillOpacity: 0.08,
      }).addTo(map);
    }
  }
  if (tracking) {
    map.setView([lat, lon], Math.max(map.getZoom(), 16), { animate: true });
  } else {
    youMarker.openPopup();
    map.setView([lat, lon], Math.max(map.getZoom(), 15));
  }
}

function radiusMeters() {
  return Number($("radius").value);
}

function localAlerts(lat, lon, radius) {
  return loadedCameras
    .map((camera) => {
      const distance = haversineMeters(lat, lon, camera.lat, camera.lon);
      const bearing = compassBearing(lat, lon, camera.lat, camera.lon);
      return {
        camera,
        distance_meters: Math.round(distance * 10) / 10,
        bearing,
        message:
          `A publicly mapped ${camera.manufacturer || "ALPR camera"} is about ${Math.round(distance)} meters` +
          ` to the ${bearing} from your current location. This is an opt-in awareness notice from public maps.`,
      };
    })
    .filter((alert) => alert.distance_meters <= radius)
    .sort((a, b) => a.distance_meters - b.distance_meters);
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

function updateLiveHud(text) {
  const hud = $("live-hud");
  hud.textContent = text;
  hud.classList.toggle("hidden", !tracking);
}

function setTrackingUi(on, mode) {
  tracking = on;
  followMode = on ? mode : null;
  $("follow-me").classList.toggle("tracking", mode === "gps" && on);
  $("demo-walk").classList.toggle("tracking", mode === "demo" && on);
  $("stop-follow").classList.toggle("hidden", !on);
  if (!on) {
    updateLiveHud("");
    if (accuracyCircle) {
      map.removeLayer(accuracyCircle);
      accuracyCircle = null;
    }
  }
}

async function fetchJson(url, options) {
  const res = await fetch(url, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || res.statusText || "Request failed");
  }
  return data;
}

async function scan(body, fit = true) {
  setBusy(true, "Scanning public OSM tags…");
  try {
    const data = await fetchJson("/api/scan", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    lastScanCenter = data.lat && data.lon ? { lat: data.lat, lon: data.lon } : null;
    drawCameras(data.cameras || [], fit);
    $("stats").textContent =
      `${data.count} publicly mapped ALPR nodes` +
      (data.flock_count ? ` · ${data.flock_count} tagged Flock Safety` : "") +
      (data.place ? ` · ${data.place}` : "");
    if (!tracking) {
      $("response").textContent =
        `Scout/map scan complete. ${data.count} OpenStreetMap ALPR tags in range. ` +
        "Click the map, follow GPS, or use a demo spot.";
      $("trace").textContent = "Direct OSM scan (no LLM)";
      if (data.lat && data.lon) {
        map.setView([data.lat, data.lon], 13);
      }
    }
    return data;
  } finally {
    setBusy(false);
  }
}

function applyAlerts(alerts, lat, lon, accuracy, sourceLabel) {
  const radius = radiusMeters();
  const nearest = alerts[0];
  const acc = typeof accuracy === "number" ? ` · ±${Math.round(accuracy)} m` : "";
  const key = `${alerts.length}:${nearest ? nearest.camera.id : "none"}:${Math.round(nearest ? nearest.distance_meters : 0)}`;
  if (tracking) {
    updateLiveHud(
      `Following${acc} · ${alerts.length} camera${alerts.length === 1 ? "" : "s"} in ${radius} m`
    );
  }
  if (tracking && key === lastAlertKey) {
    return;
  }
  lastAlertKey = key;
  renderAlerts(alerts);
  $("trace").textContent = sourceLabel;
  $("response").textContent = alerts.length
    ? `${alerts.length} publicly mapped ALPR camera(s) within ${radius} m. Nearest: ${Math.round(nearest.distance_meters)} m ${nearest.bearing} (${nearest.camera.manufacturer || "ALPR"}). Coordinates are not stored.`
    : `No publicly mapped ALPR cameras within ${radius} m. Public maps are incomplete.`;
}

async function ensureCamerasAround(lat, lon) {
  const needScan =
    !loadedCameras.length ||
    !lastScanCenter ||
    haversineMeters(lat, lon, lastScanCenter.lat, lastScanCenter.lon) > RESCAN_METERS;
  if (!needScan || scanningAround) return;
  scanningAround = true;
  try {
    await scan({ lat, lon, radius_meters: 4000, place: "current position" }, false);
  } finally {
    scanningAround = false;
  }
}

async function checkSpot(coords, options = {}) {
  if (!coords) {
    $("response").textContent = "Stand somewhere first: click the map, follow GPS, or use a demo spot.";
    return;
  }
  const live = Boolean(options.live);
  standAt(coords.lat, coords.lon, options.label, coords.accuracy);
  if (live) {
    await ensureCamerasAround(coords.lat, coords.lon);
    applyAlerts(
      localAlerts(coords.lat, coords.lon, radiusMeters()),
      coords.lat,
      coords.lon,
      coords.accuracy,
      "Live proximity (on-device)"
    );
    return;
  }
  setBusy(true, "Checking nearby cameras…");
  try {
    const data = await fetchJson("/api/nearby", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        lat: coords.lat,
        lon: coords.lon,
        radius_meters: radiusMeters(),
        refresh_osm: options.refreshOsm !== false,
        live: false,
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
      (pos) =>
        resolve({
          lat: pos.coords.latitude,
          lon: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
        }),
      (err) => reject(new Error(err.message || "Location permission was denied.")),
      GPS_OPTIONS
    );
  });
}

function stopTracking() {
  if (watchId !== null && navigator.geolocation) {
    navigator.geolocation.clearWatch(watchId);
  }
  watchId = null;
  if (demoTimer) {
    clearInterval(demoTimer);
    demoTimer = null;
  }
  setTrackingUi(false);
}

async function onPosition(coords, label) {
  await checkSpot(coords, { live: true, label: label || "You (live, not stored)" });
}

function startGpsFollow() {
  if (!navigator.geolocation) {
    $("response").textContent = "This browser does not support geolocation.";
    return;
  }
  stopTracking();
  setTrackingUi(true, "gps");
  updateLiveHud("Following GPS… waiting for a fix");
  watchId = navigator.geolocation.watchPosition(
    (pos) => {
      onPosition(
        {
          lat: pos.coords.latitude,
          lon: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
        },
        "You (live GPS, not stored)"
      ).catch((err) => {
        $("response").textContent = String(err);
      });
    },
    (err) => {
      $("response").textContent = err.message || "Could not follow GPS. Try localhost or HTTPS, and allow location.";
      stopTracking();
    },
    GPS_OPTIONS
  );
}

function interpolate(a, b, t) {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
}

function startDemoWalk() {
  stopTracking();
  setTrackingUi(true, "demo");
  updateLiveHud("Demo walk · simulated GPS");
  let step = 0;
  const stepsPerLeg = 8;
  demoTimer = setInterval(() => {
    const leg = Math.floor(step / stepsPerLeg);
    if (leg >= DEMO_PATH.length - 1) {
      stopTracking();
      $("response").textContent = "Demo walk finished. Turn on Follow my position to use real GPS.";
      return;
    }
    const t = (step % stepsPerLeg) / stepsPerLeg;
    const [lat, lon] = interpolate(DEMO_PATH[leg], DEMO_PATH[leg + 1], t);
    onPosition({ lat, lon, accuracy: 12 }, "You (demo walk, not stored)").catch((err) => {
      $("response").textContent = String(err);
    });
    step += 1;
  }, 700);
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
  if (tracking && lastCoords) {
    applyAlerts(
      localAlerts(lastCoords.lat, lastCoords.lon, radiusMeters()),
      lastCoords.lat,
      lastCoords.lon,
      lastCoords.accuracy,
      "Live proximity (on-device)"
    );
  }
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
  stopTracking();
  standAt(preset.stand_lat, preset.stand_lon, `You · ${preset.stand_label}`);
  $("response").textContent = `Standing at ${preset.stand_label}. Click Check this spot or Demo walk.`;
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
    stopTracking();
    const coords = await locate();
    standAt(coords.lat, coords.lon, "You (GPS, not stored)", coords.accuracy);
    await checkSpot(coords);
  } catch (err) {
    $("response").textContent = String(err);
  }
});

$("follow-me").addEventListener("click", () => {
  if (tracking && followMode === "gps") {
    stopTracking();
    return;
  }
  startGpsFollow();
});

$("demo-walk").addEventListener("click", () => {
  if (tracking && followMode === "demo") {
    stopTracking();
    return;
  }
  startDemoWalk();
});

$("stop-follow").addEventListener("click", () => {
  stopTracking();
  $("response").textContent = "Stopped tracking. Last position was not stored.";
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
  if (tracking) return;
  standAt(event.latlng.lat, event.latlng.lng, "You (map click, not stored)");
});

async function boot() {
  try {
    const health = await fetchJson("/api/health");
    $("health").textContent = health.llm_enabled
      ? `LLM supervisor on (${health.provider}). Map scan works without a key.`
      : "No LLM key — map scan, live follow, and keyword agents still work.";
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
