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
let routeLayer = null;
let destMarker = null;
let destCoords = null;
let originMarker = null;
let originCoords = null;
let settingPoint = null;
let demoWalkReverse = false;
let demoWalkGeneration = 0;
let privacyLayers = [];
let lastNearestMeters = null;
let focusCircle = null;
let flockVoiceOn = false;
let flockVoiceWatch = null;
let demoFlocks = [];

const RESCAN_METERS = 1800;
const GPS_OPTIONS = { enableHighAccuracy: true, maximumAge: 2000, timeout: 15000 };
const LIVE_CLOSE_FLOCK_M = 50;
const LIVE_NEAR_FLOCK_M = 150;
const LIVE_CLOSE_ALPR_M = 30;
const LIVE_NEAR_ALPR_M = 80;
const LIVE_TREND_M = 8;
const LIVE_DISCLAIMER =
  "Public maps are incomplete and may be stale. This is civic awareness, not a live camera feed, and not a way to evade law enforcement.";

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
    if (
      button.id === "stop-follow" ||
      button.id === "live-track" ||
      button.id === "demo-walk-to" ||
      button.id === "demo-walk-from" ||
      button.id === "demo-flocks-here"
    ) {
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
      (camera.notes ? `<br/>${escapeHtml(camera.notes)}` : "") +
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

function isDemoFlockId(id) {
  return String(id || "").startsWith("demo-");
}

function replaceDemoFlocks(prefix, pins) {
  demoFlocks = demoFlocks.filter((pin) => !String(pin.id).startsWith(prefix)).concat(pins);
}

function offsetMeters(lat, lon, eastMeters, northMeters) {
  const dLat = northMeters / 111320;
  const dLon = eastMeters / (111320 * Math.max(0.2, Math.cos((lat * Math.PI) / 180)));
  return { lat: lat + dLat, lon: lon + dLon };
}

function makeDemoFlock(id, lat, lon, street) {
  return {
    id,
    lat,
    lon,
    manufacturer: "Flock Safety",
    source: "seed",
    street,
    city: "Demo",
    confidence: "low",
    notes: "Temporary demo Flock pin. Not a real camera — for live tracking demos only.",
  };
}

function drawCameras(cameras, fit = true) {
  const incoming = cameras || [];
  const extras = demoFlocks.filter((pin) => !incoming.some((camera) => camera.id === pin.id));
  loadedCameras = incoming.concat(extras);
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

function isFlockCamera(camera) {
  return (camera?.manufacturer || "").toLowerCase().startsWith("flock");
}

function liveTrend(current, previous) {
  if (current == null || previous == null) return "steady";
  if (current <= previous - LIVE_TREND_M) return "approaching";
  if (current >= previous + LIVE_TREND_M) return "receding";
  return "steady";
}

function liveStatusFromAlerts(alerts, radius, previousNearest) {
  const ranked = (alerts || [])
    .slice()
    .sort((a, b) => a.distance_meters - b.distance_meters);
  const nearest = ranked[0] || null;
  const flockAlerts = ranked.filter((item) => isFlockCamera(item.camera));
  const nearestFlock = flockAlerts[0] || null;
  const flockCount = flockAlerts.length;
  const trend = liveTrend(nearest ? nearest.distance_meters : null, previousNearest);
  let level = "clear";
  if (nearest) {
    const nearestM = nearest.distance_meters;
    const flockM = nearestFlock ? nearestFlock.distance_meters : Infinity;
    if (flockM <= LIVE_CLOSE_FLOCK_M || nearestM <= LIVE_CLOSE_ALPR_M) level = "close";
    else if (flockM <= LIVE_NEAR_FLOCK_M || nearestM <= LIVE_NEAR_ALPR_M) level = "nearby";
    else level = "watch";
  }
  const focus = nearestFlock || nearest;
  const who = focus?.camera?.manufacturer || "ALPR camera";
  const distance = focus ? Math.round(focus.distance_meters) : 0;
  const bearing = focus?.bearing || "";
  const where = focus ? ` about ${distance} m${bearing ? ` ${bearing}` : ""}` : "";
  const clause =
    trend === "approaching"
      ? "; you are moving closer"
      : trend === "receding"
        ? "; you are moving farther away"
        : "";
  let recommendedAction;
  if (level === "clear") {
    recommendedAction =
      `No publicly mapped ALPR cameras within ${radius} m. Recommended action: continue on public roads as usual, and keep live tracking on if you want updates as you move. That does not mean the area is camera-free. ${LIVE_DISCLAIMER}`;
  } else if (level === "watch") {
    recommendedAction =
      `${ranked.length} mapped ALPR camera(s) in your ${radius} m alert radius (${flockCount} tagged Flock). Nearest is${where} (${who}). Recommended action: stay aware you may be photographed on this public roadway. If you want a path with fewer mapped cameras, use Recommend route. ${LIVE_DISCLAIMER}`;
  } else if (level === "nearby") {
    recommendedAction =
      `Mapped ${who}${where}${clause}. Recommended action: you may be scanned on this public road. Stay on a legal route; if you prefer fewer mapped cameras ahead, compare public-road options with Recommend route. Do not interfere with cameras. ${LIVE_DISCLAIMER}`;
  } else {
    recommendedAction =
      `You are within about ${distance} m of a mapped ${who}${bearing ? ` ${bearing}` : ""}${clause} — likely inside a typical ALPR capture range. Recommended action: proceed legally on this public roadway. For later legs of this trip, Recommend route can compare public-road options with fewer mapped cameras. Do not interfere with equipment. ${LIVE_DISCLAIMER}`;
  }
  const flockM = nearestFlock ? nearestFlock.distance_meters : Infinity;
  let hud;
  if (!nearest) {
    hud = `LIVE · CLEAR · 0 cameras in ${radius} m`;
  } else if (level === "watch") {
    hud = `LIVE · WATCH · ${ranked.length} ALPR · nearest ${distance} m ${bearing}`.trim();
  } else if (level === "close") {
    const label = flockM <= LIVE_CLOSE_FLOCK_M ? "FLOCK CLOSE" : "CLOSE";
    const shown = label.startsWith("FLOCK") ? nearestFlock : nearest;
    hud = `LIVE · ${label} · ${Math.round(shown.distance_meters)} m ${shown.bearing || ""}`.trim();
  } else {
    const label = flockM <= LIVE_NEAR_FLOCK_M ? "FLOCK NEARBY" : "NEARBY";
    const shown = label.startsWith("FLOCK") ? nearestFlock : nearest;
    hud = `LIVE · ${label} · ${Math.round(shown.distance_meters)} m ${shown.bearing || ""}`.trim();
  }
  return {
    level,
    trend,
    count: ranked.length,
    flock_count: flockCount,
    recommended_action: recommendedAction,
    hud,
    nearest,
    nearest_flock: nearestFlock,
  };
}

function resetLivePanel() {
  const panel = $("live-panel");
  panel.className = "live-panel";
  $("live-level").textContent = "Live tracking off";
  $("live-counts").textContent = "";
  $("live-action").textContent =
    "Turn on Live tracking (GPS) or Live demo walk to continuously watch mapped Flock / ALPR cameras around you and get a recommended civic action. Coordinates stay in the browser and are not stored.";
}

function renderLiveStatus(status, options = {}) {
  const panel = $("live-panel");
  const levels = ["clear", "watch", "nearby", "close"];
  panel.className = "live-panel";
  if (status?.level && levels.includes(status.level)) {
    panel.classList.add(`level-${status.level}`);
  }
  const demo = followMode === "demo" || options.demo;
  const titles = {
    clear: demo ? "Live demo — clear" : "Clear — no mapped cameras in range",
    watch: demo ? "Live demo — watch" : "Watch — mapped cameras in radius",
    nearby: demo
      ? status?.nearest_flock
        ? "Live demo — Flock nearby"
        : "Live demo — ALPR nearby"
      : status?.nearest_flock
        ? "Flock nearby"
        : "ALPR nearby",
    close:
      status?.nearest_flock && status.nearest_flock.distance_meters <= LIVE_CLOSE_FLOCK_M
        ? demo
          ? "Live demo — Flock close"
          : "Flock close — likely in range"
        : demo
          ? "Live demo — close"
          : "Close — likely in range",
  };
  $("live-level").textContent = titles[status?.level] || "Live tracking";
  const flock = status?.flock_count || 0;
  $("live-counts").textContent = status
    ? `${status.count || 0} ALPR · ${flock} Flock`
    : "";
  $("live-action").textContent = status?.recommended_action || "";
  if (options.tracking) {
    const hud = $("live-hud");
    hud.textContent = status?.hud || "LIVE";
    hud.classList.toggle("hidden", false);
    hud.classList.remove("level-clear", "level-watch", "level-nearby", "level-close");
    if (status?.level) hud.classList.add(`level-${status.level}`);
  }
}

function highlightNearest(alert) {
  if (focusCircle) {
    map.removeLayer(focusCircle);
    focusCircle = null;
  }
  if (!alert?.camera) return;
  const flock = isFlockCamera(alert.camera);
  focusCircle = L.circle([alert.camera.lat, alert.camera.lon], {
    radius: 70,
    color: flock ? "#ff8a5b" : "#f2c14e",
    weight: 2,
    fillColor: flock ? "#ff8a5b" : "#f2c14e",
    fillOpacity: 0.08,
  }).addTo(map);
}

function pickObnoxiousVoice() {
  const voices = window.speechSynthesis?.getVoices?.() || [];
  const ranked = voices.filter((voice) => /en[-_]/i.test(voice.lang));
  const funny = ranked.find((voice) => /whisper|novelty|zarvox|bad news|boing|hysterical|princess|belinda|fiona/i.test(voice.name));
  const british = ranked.find((voice) => /female|samantha|karen|moira|tessa|google uk/i.test(voice.name));
  return funny || british || ranked[0] || voices[0] || null;
}

function stopFlockVoice() {
  flockVoiceOn = false;
  if (flockVoiceWatch) {
    clearInterval(flockVoiceWatch);
    flockVoiceWatch = null;
  }
  if (window.speechSynthesis) {
    window.speechSynthesis.cancel();
  }
}

function shoutFlockBlock() {
  if (!flockVoiceOn || !window.speechSynthesis) return;
  const utter = new SpeechSynthesisUtterance("FLOCKBLOCK. FLOCKBLOCK. FLOCKBLOKK.");
  const voice = pickObnoxiousVoice();
  if (voice) utter.voice = voice;
  utter.lang = voice?.lang || "en-US";
  utter.rate = 1.35;
  utter.pitch = 2;
  utter.volume = 1;
  utter.onend = () => {
    if (flockVoiceOn) setTimeout(shoutFlockBlock, 60);
  };
  utter.onerror = () => {
    if (flockVoiceOn) setTimeout(shoutFlockBlock, 250);
  };
  window.speechSynthesis.speak(utter);
}

function armFlockVoice(preview) {
  if (!window.speechSynthesis) return;
  window.speechSynthesis.getVoices();
  const utter = new SpeechSynthesisUtterance(preview || "Flock block.");
  const voice = pickObnoxiousVoice();
  if (voice) utter.voice = voice;
  utter.lang = voice?.lang || "en-US";
  utter.rate = 1.25;
  utter.pitch = 1.9;
  utter.volume = 1;
  window.speechSynthesis.speak(utter);
}

function plantDemoFlockOnPath(path) {
  const fractions = [0.18, 0.48, 0.78];
  const pins = fractions.map((fraction, index) => {
    const point = path[Math.min(path.length - 1, Math.max(0, Math.floor(path.length * fraction)))];
    return makeDemoFlock(
      `demo-walk-flock-${index}`,
      point[0],
      point[1],
      "Live demo walk pin"
    );
  });
  replaceDemoFlocks("demo-walk-flock-", pins);
  drawCameras(loadedCameras.filter((camera) => !String(camera.id).startsWith("demo-walk-flock-")), false);
}

function plantDemoFlocksNear(lat, lon) {
  const layout = [
    [18, 14, "Demo Flock · close"],
    [-32, -18, "Demo Flock · close"],
    [95, -40, "Demo Flock · nearby"],
    [-160, 75, "Demo Flock · farther"],
  ];
  const pins = layout.map(([east, north, street], index) => {
    const point = offsetMeters(lat, lon, east, north);
    return makeDemoFlock(`demo-live-flock-${index}`, point.lat, point.lon, street);
  });
  replaceDemoFlocks("demo-live-flock-", pins);
  drawCameras(loadedCameras.filter((camera) => !String(camera.id).startsWith("demo-live-flock-")), false);
}

function ensureDemoFlocksNear(lat, lon) {
  if (demoFlocks.some((pin) => String(pin.id).startsWith("demo-live-flock-"))) return;
  plantDemoFlocksNear(lat, lon);
}

function clearDemoWalkFlocks() {
  const next = demoFlocks.filter((pin) => !String(pin.id).startsWith("demo-walk-flock-"));
  if (next.length === demoFlocks.length) return;
  demoFlocks = next;
  drawCameras(
    loadedCameras.filter((camera) => !String(camera.id).startsWith("demo-walk-flock-")),
    false
  );
}

function setFlockVoice(on) {
  if (on) {
    if (flockVoiceOn) {
      if (window.speechSynthesis?.paused) window.speechSynthesis.resume();
      return;
    }
    flockVoiceOn = true;
    if (window.speechSynthesis?.getVoices) {
      window.speechSynthesis.getVoices();
    }
    shoutFlockBlock();
    if (!flockVoiceWatch) {
      flockVoiceWatch = setInterval(() => {
        if (!flockVoiceOn || !window.speechSynthesis) return;
        if (window.speechSynthesis.paused) window.speechSynthesis.resume();
        if (!window.speechSynthesis.speaking) shoutFlockBlock();
      }, 400);
    }
    return;
  }
  stopFlockVoice();
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

function updateLiveHud(text, level) {
  const hud = $("live-hud");
  hud.textContent = text;
  hud.classList.toggle("hidden", !tracking);
  hud.classList.remove("level-clear", "level-watch", "level-nearby", "level-close");
  if (level) hud.classList.add(`level-${level}`);
}

function setTrackingUi(on, mode, options = {}) {
  tracking = on;
  followMode = on ? mode : null;
  $("live-track").classList.toggle("tracking", mode === "gps" && on);
  $("demo-walk-to").classList.toggle("tracking", mode === "demo" && on && !demoWalkReverse);
  $("demo-walk-from").classList.toggle("tracking", mode === "demo" && on && demoWalkReverse);
  $("stop-follow").classList.toggle("hidden", !on);
  if (!on) {
    stopFlockVoice();
    clearDemoWalkFlocks();
    lastNearestMeters = null;
    if (options.keepStatus) {
      const hud = $("live-hud");
      hud.classList.remove("hidden");
      if (hud.textContent && !/finished/.test(hud.textContent)) {
        hud.textContent = `${hud.textContent} · finished`;
      }
    } else {
      updateLiveHud("");
      resetLivePanel();
      highlightNearest(null);
    }
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
  const status = liveStatusFromAlerts(alerts, radius, lastNearestMeters);
  const key = `${status.level}:${alerts.length}:${nearest ? nearest.camera.id : "none"}:${Math.round(nearest ? nearest.distance_meters : 0)}:${status.trend}`;
  lastNearestMeters = nearest ? nearest.distance_meters : null;
  highlightNearest(status.nearest_flock || status.nearest);
  renderLiveStatus(status, { tracking, demo: followMode === "demo" });
  if (tracking) {
    const hudText =
      followMode === "demo" ? status.hud.replace(/^LIVE ·/, "LIVE DEMO ·") : status.hud;
    const nearestIsDemoFlock = isDemoFlockId(status.nearest_flock?.camera?.id);
    const shouting =
      status.level === "close" ||
      ((followMode === "demo" || nearestIsDemoFlock) &&
        Boolean(status.nearest_flock) &&
        status.nearest_flock.distance_meters <= LIVE_NEAR_FLOCK_M);
    updateLiveHud(shouting ? `FLOCKBLOCK · ${hudText}${acc}` : `${hudText}${acc}`, status.level);
    setFlockVoice(shouting);
  } else {
    setFlockVoice(false);
  }
  if (tracking && key === lastAlertKey) {
    return;
  }
  lastAlertKey = key;
  renderAlerts(alerts);
  $("trace").textContent = sourceLabel;
  $("response").textContent = status.recommended_action;
}

async function ensureCamerasAround(lat, lon) {
  while (scanningAround) {
    await new Promise((resolve) => setTimeout(resolve, 80));
  }
  const needScan =
    !loadedCameras.length ||
    !lastScanCenter ||
    haversineMeters(lat, lon, lastScanCenter.lat, lastScanCenter.lon) > RESCAN_METERS;
  if (!needScan) return;
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
    if (followMode === "gps") {
      ensureDemoFlocksNear(coords.lat, coords.lon);
    }
    applyAlerts(
      localAlerts(coords.lat, coords.lon, radiusMeters()),
      coords.lat,
      coords.lon,
      coords.accuracy,
      followMode === "demo" ? "Live demo walk (on-device)" : "Live proximity (on-device)"
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
    if (data.recommended_action) {
      renderLiveStatus(
        {
          level: data.level,
          count: data.count,
          flock_count: data.flock_count,
          recommended_action: data.recommended_action,
          hud: data.hud,
          nearest: (data.alerts || [])[0],
          nearest_flock: (data.alerts || []).find((item) => isFlockCamera(item.camera)),
        },
        { tracking: false }
      );
      highlightNearest(
        (data.alerts || []).find((item) => isFlockCamera(item.camera)) || (data.alerts || [])[0]
      );
    }
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

function stopTracking(options = {}) {
  demoWalkGeneration += 1;
  if (watchId !== null && navigator.geolocation) {
    navigator.geolocation.clearWatch(watchId);
  }
  watchId = null;
  if (demoTimer) {
    clearInterval(demoTimer);
    demoTimer = null;
  }
  if (routeLayer && !options.keepStatus) {
    map.removeLayer(routeLayer);
    routeLayer = null;
  }
  setTrackingUi(false, null, options);
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
  armFlockVoice("Live tracking. Flock block is armed.");
  $("live-level").textContent = "Live tracking on — waiting for GPS";
  $("live-counts").textContent = "";
  $("live-action").textContent =
    "Allow location to watch mapped Flock cameras around you. Coordinates stay in the browser and are not stored.";
  $("response").textContent =
    "Live tracking on. Waiting for a GPS fix. Nearby Flock feedback and a recommended civic action will update as you move.";
  updateLiveHud("LIVE · waiting for a GPS fix", "watch");
  watchId = navigator.geolocation.watchPosition(
    (pos) => {
      onPosition(
        {
          lat: pos.coords.latitude,
          lon: pos.coords.longitude,
          accuracy: pos.coords.accuracy,
        },
        "You (live tracking, not stored)"
      ).catch((err) => {
        $("response").textContent = String(err);
      });
    },
    (err) => {
      $("response").textContent = err.message || "Could not start live tracking. Try localhost or HTTPS, and allow location.";
      stopTracking();
    },
    GPS_OPTIONS
  );
}

async function animateAlongPath(path, streets, reverse) {
  const streetLabel = streets?.length ? streets.slice(0, 3).join(" → ") : "mapped streets";
  const generation = demoWalkGeneration;
  demoWalkReverse = Boolean(reverse);
  lastNearestMeters = null;
  lastAlertKey = "";
  setTrackingUi(true, "demo");
  $("live-level").textContent = reverse ? "Live demo walk from — starting" : "Live demo walk to — starting";
  $("live-counts").textContent = "";
  $("live-action").textContent =
    `Simulated live feed on ${streetLabel}. Nearby Flock / ALPR feedback and a recommended civic action update as the marker moves. Nothing is stored.`;
  $("response").textContent =
    "Live demo walk on. The same live feed as GPS tracking, simulated along public streets.";
  $("trace").textContent = `Live demo walk · ${streetLabel}`;
  updateLiveHud("LIVE DEMO · starting", "watch");
  if (routeLayer) {
    map.removeLayer(routeLayer);
  }
  routeLayer = L.polyline(path, {
    color: "#f2c14e",
    weight: 5,
    opacity: 0.85,
    dashArray: "10 8",
  }).addTo(map);
  map.fitBounds(routeLayer.getBounds(), { padding: [36, 36], maxZoom: 17 });
  await ensureCamerasAround(path[0][0], path[0][1]);
  plantDemoFlockOnPath(path);
  for (let index = 0; index < path.length; index += 1) {
    if (generation !== demoWalkGeneration) return;
    const [lat, lon] = path[index];
    try {
      await onPosition({ lat, lon, accuracy: 8 }, "You (live demo walk, not stored)");
    } catch (err) {
      if (generation !== demoWalkGeneration) return;
      $("response").textContent = String(err);
    }
    if (generation !== demoWalkGeneration) return;
    await new Promise((resolve) => setTimeout(resolve, flockVoiceOn ? 850 : 450));
  }
  if (generation !== demoWalkGeneration) return;
  stopTracking({ keepStatus: true });
  $("response").textContent =
    "Live demo walk finished. The last nearby-camera reading is still shown. Turn on Live tracking for real GPS, or run another live demo walk.";
}

async function startDemoWalk(reverse = false) {
  if (tracking && followMode === "demo") {
    stopTracking();
    return;
  }
  stopTracking();
  let origin;
  let dest;
  try {
    ({ from: origin, to: dest } = await getRouteEnds());
  } catch (err) {
    $("response").textContent = String(err);
    return;
  }
  armFlockVoice("Live demo walk. Flock block is armed.");
  setOrigin(origin.lat, origin.lon, origin.label || "Route from");
  setDestination(dest.lat, dest.lon, dest.label || "Route to");
  setBusy(true, reverse ? "Starting live demo walk from…" : "Starting live demo walk to…");
  try {
    await ensureCamerasAround(origin.lat, origin.lon);
    const data = await fetchJson("/api/walk-route", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        lat: origin.lat,
        lon: origin.lon,
        dest_lat: dest.lat,
        dest_lon: dest.lon,
        origin: origin.label,
        destination: dest.label,
        reverse,
      }),
    });
    const path = (data.points || []).map((point) => [point.lat, point.lon]);
    if (path.length < 2) {
      throw new Error("No street geometry returned for this live demo walk.");
    }
    $("trace").textContent =
      `Live demo walk ${reverse ? "from" : "to"} (${data.source || "osrm"}) · ${data.distance_meters || "?"} m`;
    setBusy(false);
    await animateAlongPath(path, data.streets || [], reverse);
  } catch (err) {
    $("response").textContent = String(err);
    setTrackingUi(false);
  } finally {
    setBusy(false);
  }
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
      setOrigin(preset.stand_lat, preset.stand_lon, preset.stand_label);
      const firstDest = (preset.destinations || [])[0];
      if (firstDest) {
        setDestination(firstDest.lat, firstDest.lon, firstDest.name);
      } else if (preset.walk_dest_lat != null) {
        setDestination(preset.walk_dest_lat, preset.walk_dest_lon, "Demo walk end");
      }
      renderDestinations(preset);
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
  setOrigin(preset.stand_lat, preset.stand_lon, preset.stand_label);
  $("response").textContent = `Standing at ${preset.stand_label}. Set Route to, then recommend a route or start a live demo walk.`;
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

$("live-track").addEventListener("click", () => {
  if (tracking && followMode === "gps") {
    stopTracking();
    return;
  }
  startGpsFollow();
});

$("demo-flocks-here").addEventListener("click", async () => {
  try {
    let coords = lastCoords;
    if (!coords) {
      coords = await locate();
      standAt(coords.lat, coords.lon, "You (GPS, not stored)", coords.accuracy);
    }
    plantDemoFlocksNear(coords.lat, coords.lon);
    applyAlerts(
      localAlerts(coords.lat, coords.lon, radiusMeters()),
      coords.lat,
      coords.lon,
      coords.accuracy,
      "Demo Flock pins (on-device)"
    );
    $("response").textContent =
      "Planted fake Flock pins around your current location. They stay in the browser and are labeled as demo. Turn on Live tracking to hear FLOCKBLOCK when you are close.";
  } catch (err) {
    $("response").textContent = String(err);
  }
});

$("demo-walk-to").addEventListener("click", () => {
  startDemoWalk(false);
});

$("demo-walk-from").addEventListener("click", () => {
  startDemoWalk(true);
});

$("stop-follow").addEventListener("click", () => {
  stopTracking();
  $("response").textContent = "Stopped tracking. Last position was not stored.";
});

function clearPrivacyRoutes() {
  privacyLayers.forEach((layer) => map.removeLayer(layer));
  privacyLayers = [];
}

function setOrigin(lat, lon, label) {
  originCoords = { lat, lon, label: label || "Route from" };
  $("origin").value = originCoords.label;
  if (originMarker) {
    originMarker.setLatLng([lat, lon]);
  } else {
    originMarker = L.circleMarker([lat, lon], {
      radius: 8,
      color: "#5ee0a0",
      fillColor: "#5ee0a0",
      fillOpacity: 1,
      weight: 2,
    }).addTo(map);
  }
  originMarker.bindPopup(escapeHtml(originCoords.label));
}

function setDestination(lat, lon, label) {
  destCoords = { lat, lon, label: label || "Route to" };
  $("destination").value = destCoords.label;
  if (destMarker) {
    destMarker.setLatLng([lat, lon]);
  } else {
    destMarker = L.circleMarker([lat, lon], {
      radius: 8,
      color: "#7ab8ff",
      fillColor: "#7ab8ff",
      fillOpacity: 1,
      weight: 2,
    }).addTo(map);
  }
  destMarker.bindPopup(escapeHtml(destCoords.label)).openPopup();
}

function swapEnds() {
  const from = originCoords ? { ...originCoords } : null;
  const to = destCoords ? { ...destCoords } : null;
  const fromText = $("origin").value;
  const toText = $("destination").value;
  if (to) {
    setOrigin(to.lat, to.lon, to.label);
  } else {
    originCoords = null;
    $("origin").value = toText;
    if (originMarker) {
      map.removeLayer(originMarker);
      originMarker = null;
    }
  }
  if (from) {
    setDestination(from.lat, from.lon, from.label);
  } else {
    destCoords = null;
    $("destination").value = fromText;
    if (destMarker) {
      map.removeLayer(destMarker);
      destMarker = null;
    }
  }
}

function setPointMode(mode) {
  settingPoint = settingPoint === mode ? null : mode;
  $("set-from-map").classList.toggle("tracking", settingPoint === "from");
  $("set-dest-map").classList.toggle("tracking", settingPoint === "to");
  if (settingPoint === "from") {
    $("response").textContent = "Click the map to set Route from.";
  } else if (settingPoint === "to") {
    $("response").textContent = "Click the map to set Route to.";
  } else {
    $("response").textContent = "Map click cancelled.";
  }
}

function renderDestinations(preset) {
  const root = $("dest-presets");
  root.innerHTML = "";
  if (preset.stand_lat != null) {
    const standChip = document.createElement("button");
    standChip.type = "button";
    standChip.className = "chip";
    standChip.textContent = `From: ${preset.stand_label}`;
    standChip.addEventListener("click", () => {
      setOrigin(preset.stand_lat, preset.stand_lon, preset.stand_label);
    });
    root.appendChild(standChip);
  }
  (preset.destinations || []).forEach((dest) => {
    const chip = document.createElement("button");
    chip.type = "button";
    chip.className = "chip";
    chip.textContent = dest.name;
    chip.addEventListener("click", () => {
      if (settingPoint === "from") {
        setOrigin(dest.lat, dest.lon, dest.name);
        setPointMode(null);
      } else {
        setDestination(dest.lat, dest.lon, dest.name);
      }
    });
    root.appendChild(chip);
  });
}

function drawPrivacyRoutes(data) {
  clearPrivacyRoutes();
  const alts = data.alternatives || [];
  alts.forEach((route, index) => {
    const isBest = index === 0;
    const line = L.polyline(
      (route.points || []).map((point) => [point.lat, point.lon]),
      {
        color: isBest ? "#f2c14e" : "#6d7786",
        weight: isBest ? 6 : 3,
        opacity: isBest ? 0.95 : 0.55,
      }
    ).addTo(map);
    privacyLayers.push(line);
  });
  if (data.origin_lat && data.origin_lon) {
    setOrigin(data.origin_lat, data.origin_lon, data.origin || "Route from");
  }
  if (data.dest_lat && data.dest_lon) {
    setDestination(data.dest_lat, data.dest_lon, data.destination || "Route to");
  }
  if (privacyLayers.length) {
    map.fitBounds(privacyLayers[0].getBounds(), { padding: [40, 40] });
  }
}

function renderRouteOptions(data) {
  const list = $("route-options");
  list.innerHTML = "";
  (data.alternatives || []).forEach((route, index) => {
    const item = document.createElement("li");
    if (index === 0) item.className = "best";
    const km = (route.distance_meters / 1000).toFixed(2);
    const minutes = route.duration_seconds ? Math.max(1, Math.round(route.duration_seconds / 60)) : null;
    const steps = (route.steps || []).slice(0, 4).join(" → ");
    item.innerHTML =
      `<strong>${index === 0 ? "Recommended" : "Alternative"}</strong> · ` +
      `${route.camera_count} mapped cameras` +
      (route.flock_count ? ` (${route.flock_count} Flock)` : "") +
      ` · ${km} km` +
      (minutes ? ` · ${minutes} min walk` : "") +
      (steps ? `<div>${escapeHtml(steps)}</div>` : "");
    item.addEventListener("click", () => {
      if (!privacyLayers[index]) return;
      map.fitBounds(privacyLayers[index].getBounds(), { padding: [40, 40] });
    });
    list.appendChild(item);
  });
}

function pinMatchesText(coords, text) {
  if (!coords) return false;
  if (!text) return true;
  return (coords.label || "").trim().toLowerCase() === text.trim().toLowerCase();
}

async function geocodeQuery(text) {
  const preset = activePreset || presets[0];
  const bias =
    lastCoords ||
    originCoords ||
    destCoords ||
    (preset ? { lat: preset.lat, lon: preset.lon } : null);
  const params = new URLSearchParams({ q: text });
  if (bias) {
    params.set("lat", String(bias.lat));
    params.set("lon", String(bias.lon));
  }
  const data = await fetchJson(`/api/geocode?${params.toString()}`);
  return data.results || [];
}

async function resolveTypedEnd(kind) {
  const text = $(kind === "from" ? "origin" : "destination").value.trim();
  const coords = kind === "from" ? originCoords : destCoords;
  if (pinMatchesText(coords, text)) return coords;
  if (!text) return coords;
  const results = await geocodeQuery(text);
  const hit = results[0];
  if (!hit) {
    throw new Error(`Could not find "${text}". Pick a suggestion from the list.`);
  }
  if (kind === "from") setOrigin(hit.lat, hit.lon, hit.label);
  else setDestination(hit.lat, hit.lon, hit.label);
  return { lat: hit.lat, lon: hit.lon, label: hit.label };
}

function hideSuggest(kind) {
  const list = $(kind === "from" ? "origin-suggest" : "destination-suggest");
  list.hidden = true;
  list.innerHTML = "";
}

function bindPlaceSearch(kind) {
  const input = $(kind === "from" ? "origin" : "destination");
  const list = $(kind === "from" ? "origin-suggest" : "destination-suggest");
  let timer = null;
  input.addEventListener("input", () => {
    if (kind === "from" && originCoords && !pinMatchesText(originCoords, input.value)) {
      originCoords = null;
    }
    if (kind === "to" && destCoords && !pinMatchesText(destCoords, input.value)) {
      destCoords = null;
    }
    clearTimeout(timer);
    const query = input.value.trim();
    if (query.length < 2) {
      hideSuggest(kind);
      return;
    }
    timer = setTimeout(async () => {
      try {
        const results = await geocodeQuery(query);
        list.innerHTML = "";
        if (!results.length) {
          list.hidden = true;
          return;
        }
        results.forEach((hit) => {
          const item = document.createElement("li");
          item.textContent = hit.label;
          item.addEventListener("mousedown", (event) => {
            event.preventDefault();
            if (kind === "from") setOrigin(hit.lat, hit.lon, hit.label);
            else setDestination(hit.lat, hit.lon, hit.label);
            hideSuggest(kind);
          });
          list.appendChild(item);
        });
        list.hidden = false;
      } catch {
        hideSuggest(kind);
      }
    }, 220);
  });
  input.addEventListener("blur", () => {
    setTimeout(() => hideSuggest(kind), 180);
  });
}

async function setEndToCurrentLocation(kind) {
  try {
    let coords = lastCoords;
    if (!coords) {
      coords = await locate();
      standAt(coords.lat, coords.lon, "You (GPS, not stored)", coords.accuracy);
    }
    const label = "Current location";
    if (kind === "from") setOrigin(coords.lat, coords.lon, label);
    else setDestination(coords.lat, coords.lon, label);
    $("response").textContent = `Route ${kind} set to your current location. Same ends are used for Recommend and Live demo walk.`;
  } catch (err) {
    $("response").textContent = String(err);
  }
}

async function getRouteEnds() {
  const from = (await resolveTypedEnd("from")) || (lastCoords
    ? { lat: lastCoords.lat, lon: lastCoords.lon, label: "Current location" }
    : null);
  const to = await resolveTypedEnd("to");
  if (from && from.label === "Current location" && !originCoords) {
    setOrigin(from.lat, from.lon, from.label);
  }
  if (!from) {
    throw new Error("Set Route from: current location, a search, a place chip, or the map.");
  }
  if (!to) {
    throw new Error("Set Route to: current location, a search, a place chip, or the map.");
  }
  return { from, to };
}

async function recommendRoute(reverse = false) {
  let from;
  let to;
  try {
    ({ from, to } = await getRouteEnds());
  } catch (err) {
    $("response").textContent = String(err);
    return;
  }
  const body = {
    lat: from.lat,
    lon: from.lon,
    origin_lat: from.lat,
    origin_lon: from.lon,
    dest_lat: to.lat,
    dest_lon: to.lon,
    origin: from.label || $("origin").value.trim(),
    destination: to.label || $("destination").value.trim(),
    scan: true,
    reverse,
  };
  setBusy(true, reverse ? "Comparing walking routes from…" : "Comparing walking routes to…");
  try {
    const data = await fetchJson("/api/privacy-route", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    drawPrivacyRoutes(data);
    renderRouteOptions(data);
    $("response").textContent = data.narrative || "";
    $("trace").textContent = reverse
      ? "Walking directions · from destination back to origin"
      : "Walking directions · origin to destination";
    renderAlerts(
      (data.recommended?.cameras || []).slice(0, 8).map((camera) => ({
        camera,
        distance_meters: camera.distance_meters,
        bearing: "",
        message: `${camera.manufacturer || "ALPR"} is about ${Math.round(camera.distance_meters)} m from this recommended roadway.`,
      }))
    );
  } finally {
    setBusy(false);
  }
}

$("route-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  try {
    await recommendRoute(false);
  } catch (err) {
    $("response").textContent = String(err);
  }
});

$("route-from").addEventListener("click", async () => {
  try {
    await recommendRoute(true);
  } catch (err) {
    $("response").textContent = String(err);
  }
});

$("set-from-map").addEventListener("click", () => {
  setPointMode("from");
});

$("set-dest-map").addEventListener("click", () => {
  setPointMode("to");
});

$("swap-ends").addEventListener("click", () => {
  swapEnds();
  $("response").textContent = "Swapped Route from and Route to.";
});

$("from-here").addEventListener("click", () => {
  setEndToCurrentLocation("from");
});

$("to-here").addEventListener("click", () => {
  setEndToCurrentLocation("to");
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
  if (settingPoint === "from") {
    setOrigin(event.latlng.lat, event.latlng.lng, "Map origin");
    setPointMode(null);
    $("response").textContent = "Route from set. Recommend or Live demo walk will use this start.";
    return;
  }
  if (settingPoint === "to") {
    setDestination(event.latlng.lat, event.latlng.lng, "Map destination");
    setPointMode(null);
    $("response").textContent = "Route to set. Recommend or Live demo walk will use this end.";
    return;
  }
  standAt(event.latlng.lat, event.latlng.lng, "You (map click, not stored)");
});

async function boot() {
  try {
    const health = await fetchJson("/api/health");
    $("health").textContent = health.llm_enabled
      ? `LLM supervisor on (${health.provider}). Map scan works without a key.`
      : "No LLM key — map scan, live tracking, and keyword agents still work.";
  } catch {
    $("health").textContent = "API unreachable.";
  }
  try {
    const data = await fetchJson("/api/presets");
    presets = data.presets || [];
    renderPresets();
    if (presets[0]) renderDestinations(presets[0]);
    bindPlaceSearch("from");
    bindPlaceSearch("to");
  } catch {
    $("response").textContent = "Could not load demo cities.";
  }
  try {
    const stored = await fetchJson("/api/cameras");
    if (stored.cameras?.length) drawCameras(stored.cameras);
  } catch {
    /* seed load is optional */
  }
  if (window.speechSynthesis?.getVoices) {
    window.speechSynthesis.getVoices();
    window.speechSynthesis.addEventListener("voiceschanged", () => {
      window.speechSynthesis.getVoices();
    });
  }
}

boot();
