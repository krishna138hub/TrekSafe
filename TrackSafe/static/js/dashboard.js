/* TrackSafe dashboard - consumes only the structured "state" snapshot from the backend. */
(function () {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) =>
    ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

  // ---- map ----------------------------------------------------------
  const map = L.map("map", { zoomControl: true }).setView([10.115, 76.245], 12);
  L.tileLayer("https://{s}.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}{r}.png", {
    maxZoom: 19, attribution: "&copy; OpenStreetMap &copy; CARTO"
  }).addTo(map);

  const markers = {};            // device_id -> L.marker
  let zoneLayer = L.layerGroup().addTo(map);
  let zonesDrawn = false;
  const heat = L.heatLayer([], {
    radius: 45, blur: 30, maxZoom: 15, max: 1.0,
    gradient: { 0.2: "#38bdf8", 0.5: "#22c55e", 0.75: "#f59e0b", 1.0: "#ef4444" }
  }).addTo(map);
  let state = null, fitted = false;

  const markerClass = (d) => (d.alert_status !== "NONE" ? d.alert_status : d.status);

  function popupHtml(d) {
    return `<b>${esc(d.device_id)}</b><br>
      Status: ${esc(d.status)}<br>
      Latitude: ${d.latitude.toFixed(6)}<br>
      Longitude: ${d.longitude.toFixed(6)}<br>
      Zone: ${esc(d.zone)}<br>
      Last update: ${esc(d.last_update)}<br>
      Heart rate: ${d.heart_rate} BPM<br>
      Battery: ${d.battery}%<br>
      Alert: ${esc(d.alert_status)}`;
  }

  function drawZones(defs) {
    if (zonesDrawn) return;
    zonesDrawn = true;
    defs.forEach((z) => {
      L.circle([z.lat, z.lon], { radius: z.radius, color: "#38bdf8", weight: 1,
        dashArray: "4 6", fill: false, opacity: .45 }).addTo(zoneLayer);
      L.marker([z.lat, z.lon], { interactive: false, icon: L.divIcon({
        className: "", html: `<span style="color:#8b9ab3;font-size:11px;white-space:nowrap">${esc(z.name)}</span>` })
      }).addTo(zoneLayer);
    });
  }

  function renderMap(s) {
    drawZones(s.zone_defs);
    const showOffline = $("t-offline").checked;
    const seen = new Set();
    s.devices.forEach((d) => {
      if (d.status === "OFFLINE" && !showOffline) return;
      seen.add(d.device_id);
      const cls = markerClass(d);
      const icon = L.divIcon({ className: "", iconSize: [24, 24], iconAnchor: [12, 12],
        html: `<div class="mk ${cls}"></div>` });
      let m = markers[d.device_id];
      if (!m) {
        m = L.marker([d.latitude, d.longitude], { icon, title: d.device_id }).addTo(map);
        m.bindPopup("");
        markers[d.device_id] = m;
      }
      m.setLatLng([d.latitude, d.longitude]);
      m.setIcon(icon);
      m.setZIndexOffset(d.alert_status !== "NONE" ? 1000 : 0);
      m.setPopupContent(popupHtml(d));
    });
    Object.keys(markers).forEach((id) => {
      if (!seen.has(id)) { map.removeLayer(markers[id]); delete markers[id]; }
    });

    // heatmap of ACTIVE device concentration (not a risk map)
    const pts = s.devices.filter((d) => d.status === "ACTIVE")
      .map((d) => {
        const n = s.devices.filter((o) => o.status === "ACTIVE" &&
          Math.abs(o.latitude - d.latitude) < 0.01 && Math.abs(o.longitude - d.longitude) < 0.01).length;
        return [d.latitude, d.longitude, Math.min(1, 0.3 + n * 0.2)];
      });
    heat.setLatLngs(pts);
    if ($("t-heat").checked) { if (!map.hasLayer(heat)) heat.addTo(map); }
    else if (map.hasLayer(heat)) map.removeLayer(heat);

    if (!fitted && s.devices.length) {
      const b = L.latLngBounds(s.devices.map((d) => [d.latitude, d.longitude]));
      map.fitBounds(b.pad(0.6), { maxZoom: 14 });
      fitted = true;
    }
  }

  function focusDevice(id) {
    const m = markers[id];
    if (!m) return;
    map.flyTo(m.getLatLng(), Math.max(map.getZoom(), 15), { duration: 0.8 });
    m.openPopup();
    $("map").scrollIntoView({ behavior: "smooth", block: "center" });
  }

  // ---- panels -------------------------------------------------------
  function renderSummary(s) {
    $("s-total").textContent = s.summary.total;
    $("s-active").textContent = s.summary.active;
    $("s-offline").textContent = s.summary.offline;
    $("s-sos").textContent = s.summary.sos;
    $("s-fall").textContent = s.summary.fall;
    $("card-sos").classList.toggle("hot", s.summary.sos > 0);
    $("card-fall").classList.toggle("hot", s.summary.fall > 0);
  }

  function renderAlerts(s) {
    const open = s.alerts.filter((a) => a.status === "UNRESOLVED");
    const c = $("alert-count");
    c.textContent = open.length;
    c.classList.toggle("zero", open.length === 0);
    $("alerts").innerHTML = open.length ? open.map((a) => `
      <div class="alert ${a.type}">
        <div class="t">${a.type === "SOS" ? "🚨 SOS ALERT" : "⚠ FALL DETECTED"}</div>
        <div class="meta"><b>${esc(a.device_id)}</b>${esc(a.zone || "")} &nbsp;${esc(a.timestamp)}<br>
          ${a.latitude.toFixed(6)}, ${a.longitude.toFixed(6)} &nbsp;Status: ${esc(a.status)}</div>
        <button data-view="${esc(a.device_id)}">View on map</button>
        <button class="ack" data-ack="${a.alert_id}">Acknowledge</button>
      </div>`).join("") : `<div class="empty">No active alerts.</div>`;
  }

  function renderZones(s) {
    const max = Math.max(1, ...s.zones.map((z) => z.active));
    $("zones").innerHTML = s.zones.map((z) => `
      <div class="zrow"><span>${esc(z.name)}</span>
        <div class="zbar"><i style="width:${(z.active / max) * 100}%"></i></div>
        <span class="n">${z.active}</span></div>`).join("");
  }

  function renderDevices(s) {
    $("devices").innerHTML = s.devices.length ? s.devices.map((d) => `
      <tr class="r-${d.alert_status}" data-view="${esc(d.device_id)}">
        <td><b>${esc(d.device_id)}</b></td>
        <td><span class="badge b-${d.status}">${d.status}</span></td>
        <td>${esc(d.zone)}</td>
        <td>${d.latitude.toFixed(6)}, ${d.longitude.toFixed(6)}</td>
        <td>${esc(d.last_update)}</td>
        <td>${d.heart_rate} BPM</td>
        <td>${d.battery}%</td>
        <td><span class="badge b-${d.alert_status}">${d.alert_status}</span></td>
      </tr>`).join("") : `<tr><td colspan="8" class="empty">No devices registered.</td></tr>`;
  }

  function renderLog(s) {
    $("log").innerHTML = s.log.length ? s.log.map((e) => `
      <div class="lrow ${esc(e.level)}"><span class="tm">${esc(e.time)}</span>
      <span class="id">${esc(e.device_id)}</span>${esc(e.message)}</div>`).join("")
      : `<div class="empty">No activity yet.</div>`;
  }

  function render(s) {
    state = s;
    renderSummary(s); renderAlerts(s); renderZones(s);
    renderDevices(s); renderLog(s); renderMap(s);
  }

  // ---- events -------------------------------------------------------
  document.addEventListener("click", (e) => {
    const v = e.target.closest("[data-view]");
    const a = e.target.closest("[data-ack]");
    if (a) socket.emit("acknowledge", { alert_id: Number(a.dataset.ack) });
    else if (v) focusDevice(v.dataset.view);
  });
  ["t-heat", "t-offline"].forEach((id) => $(id).addEventListener("change", () => state && renderMap(state)));

  setInterval(() => { $("clock").textContent = new Date().toLocaleTimeString("en-GB"); }, 1000);

  const socket = io();
  socket.on("connect", () => { $("conn").textContent = "Live"; $("conn").className = "conn on"; });
  socket.on("disconnect", () => { $("conn").textContent = "Disconnected"; $("conn").className = "conn off"; });
  socket.on("state", render);
})();
