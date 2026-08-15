const map = L.map("map").setView([37.7749, -122.4194], 13);
L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
  maxZoom: 19,
  attribution: "&copy; OpenStreetMap",
}).addTo(map);

const cameraLayer = L.layerGroup().addTo(map);
let youMarker = null;
let lastCoords = null;

const colors = {
  openstreetmap: "#5ee0a0",
  news: "#7ab8ff",
  seed: "#9aa4b2",
  user_report: "#d4a5ff",
};

function markerFor(camera) {
  const color = colors[camera.source] || "#5ee0a0";
  return L.circleMarker([camera.lat, camera.lon], {
    radius: 7,
    color,
    fillColor: color,
    fillOpacity: 0.9,
    weight: 1,
  }).bindPopup(
    `<strong>${camera.manufacturer || "ALPR"}</strong><br/>` +
      `${camera.street || camera.city || "Mapped location"}<br/>` +
      `source: ${camera.source} · confidence: ${camera.confidence}` +
      (camera.source_url ? `<br/><a href="${camera.source_url}" target="_blank" rel="noopener">source</a>` : "")
  );
}

async function loadCameras() {
  const res = await fetch("/api/cameras");
  const data = await res.json();
  cameraLayer.clearLayers();
  data.cameras.forEach((camera) => markerFor(camera).addTo(cameraLayer));
}

function renderResult(data) {
  document.getElementById("response").textContent = data.response || "";
  document.getElementById("trace").textContent = data.agent_trace?.length
    ? `Agents: ${data.agent_trace.join(" → ")}`
    : "";
  const sources = document.getElementById("sources");
  sources.innerHTML = "";
  const links = [
    ...(data.findings || []),
    ...(data.policy_notes || []),
  ];
  links.forEach((item) => {
    const li = document.createElement("li");
    li.innerHTML = `<a href="${item.url}" target="_blank" rel="noopener">${item.title}</a>`;
    sources.appendChild(li);
  });
  (data.cameras || []).forEach((camera) => markerFor(camera).addTo(cameraLayer));
  if (data.lat && data.lon) {
    map.setView([data.lat, data.lon], 13);
  }
}

async function sendChat(message, coords) {
  const body = { message };
  if (coords) {
    body.lat = coords.lat;
    body.lon = coords.lon;
  }
  document.getElementById("response").textContent = "Agents running…";
  const res = await fetch("/api/chat", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  renderResult(data);
}

function locate() {
  return new Promise((resolve, reject) => {
    if (!navigator.geolocation) {
      reject(new Error("Geolocation is not available in this browser."));
      return;
    }
    navigator.geolocation.getCurrentPosition(
      (pos) => {
        const coords = { lat: pos.coords.latitude, lon: pos.coords.longitude };
        lastCoords = coords;
        if (youMarker) {
          youMarker.setLatLng([coords.lat, coords.lon]);
        } else {
          youMarker = L.circleMarker([coords.lat, coords.lon], {
            radius: 8,
            color: "#f2c14e",
            fillColor: "#f2c14e",
            fillOpacity: 1,
          })
            .bindPopup("You (opt-in, not stored)")
            .addTo(map);
        }
        map.setView([coords.lat, coords.lon], 15);
        resolve(coords);
      },
      () => reject(new Error("Location permission was denied.")),
      { enableHighAccuracy: true, timeout: 10000 }
    );
  });
}

document.getElementById("chat-form").addEventListener("submit", async (event) => {
  event.preventDefault();
  const message = document.getElementById("message").value.trim();
  if (!message) return;
  try {
    await sendChat(message, lastCoords);
  } catch (err) {
    document.getElementById("response").textContent = String(err);
  }
});

document.getElementById("near-me").addEventListener("click", async () => {
  try {
    const coords = await locate();
    await sendChat(
      "Alert me if I am near a publicly mapped Flock or ALPR camera.",
      coords
    );
  } catch (err) {
    document.getElementById("response").textContent = String(err);
  }
});

async function boot() {
  try {
    const res = await fetch("/api/health");
    const health = await res.json();
    document.getElementById("health").textContent = health.llm_enabled
      ? `LLM supervisor on (${health.provider}). Tools still work if the model is down.`
      : "No LLM key configured — keyword supervisor + live OSM/web tools.";
  } catch {
    document.getElementById("health").textContent = "API unreachable.";
  }
  await loadCameras();
}

boot();
