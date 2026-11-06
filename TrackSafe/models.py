"""
TrackSafe data model + data-processing layer.

This module knows NOTHING about where data comes from (console, serial, LoRa...).
Every input source must send plain dict "events" to TrackSafeProcessor.process().

Event contract (the only thing an input layer needs to produce):

    {"type": "activate",    "device_id": "TS001"}
    {"type": "deactivate",  "device_id": "TS001"}
    {"type": "location",    "device_id": "TS001", "latitude": 10.12, "longitude": 76.23}
    {"type": "sos",         "device_id": "TS003"}
    {"type": "fall",        "device_id": "TS004"}
    {"type": "heart_rate",  "device_id": "TS001", "value": 84}
    {"type": "battery",     "device_id": "TS001", "value": 73}
    {"type": "clear_alert", "device_id": "TS003"}            # all alerts of device
    {"type": "clear_alert", "alert_id": 5}                   # one specific alert
"""
import math
import threading
from collections import deque
from dataclasses import dataclass, asdict
from datetime import datetime

# ---------------------------------------------------------------- zones
# Demo zones (name, centre lat, centre lon, radius in metres). Edit freely.
ZONES = [
    {"name": "Base Camp",   "lat": 10.1000, "lon": 76.2500, "radius": 1500},
    {"name": "North Trail", "lat": 10.1300, "lon": 76.2400, "radius": 2500},
    {"name": "Lake Trail",  "lat": 10.1100, "lon": 76.2200, "radius": 2500},
    {"name": "Ridge View",  "lat": 10.1450, "lon": 76.2650, "radius": 2500},
]
DEFAULT_LOCATION = (ZONES[0]["lat"], ZONES[0]["lon"])


def _distance_m(lat1, lon1, lat2, lon2):
    """Haversine distance in metres."""
    r = 6371000
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def zone_for(lat, lon):
    best, best_d = None, None
    for z in ZONES:
        d = _distance_m(lat, lon, z["lat"], z["lon"])
        if d <= z["radius"] and (best_d is None or d < best_d):
            best, best_d = z["name"], d
    return best or "Unzoned"


def _now():
    return datetime.now()


def _hms(dt):
    return dt.strftime("%H:%M:%S")


# ---------------------------------------------------------------- models
@dataclass
class Device:
    device_id: str
    status: str = "OFFLINE"          # ACTIVE | OFFLINE
    latitude: float = DEFAULT_LOCATION[0]
    longitude: float = DEFAULT_LOCATION[1]
    zone: str = "Base Camp"
    last_update: str = "--:--:--"
    heart_rate: int = 72
    battery: int = 100
    alert_status: str = "NONE"       # NONE | SOS | FALL  (unresolved only)


@dataclass
class Alert:
    alert_id: int
    device_id: str
    type: str                        # SOS | FALL
    timestamp: str
    latitude: float
    longitude: float
    status: str = "UNRESOLVED"       # UNRESOLVED | ACKNOWLEDGED
    zone: str = ""


# ---------------------------------------------------------------- processor
class TrackSafeProcessor:
    def __init__(self):
        self._lock = threading.RLock()
        self.devices = {}            # device_id -> Device
        self.alerts = []             # all alerts, oldest first
        self.log = deque(maxlen=300) # newest first
        self._alert_seq = 0
        self._listeners = []

    # -- listeners (the web layer subscribes here) ------------------------
    def add_listener(self, fn):
        self._listeners.append(fn)

    def _notify(self, snap):
        for fn in self._listeners:
            try:
                fn(snap)
            except Exception as exc:  # never let the UI break the data layer
                print(f"[listener error] {exc}")

    # -- public API -------------------------------------------------------
    def register_device(self, device_id):
        device_id = device_id.strip().upper()
        with self._lock:
            if device_id in self.devices:
                return False, f"{device_id} already registered."
            self.devices[device_id] = Device(device_id=device_id)
            self.devices[device_id].zone = zone_for(*DEFAULT_LOCATION)
            self._log(device_id, "DEVICE REGISTERED", "info")
            snap = self._snapshot()
        self._notify(snap)
        return True, f"{device_id} registered."

    def process(self, event):
        """Single entry point for ALL input sources. Returns (ok, message)."""
        etype = str(event.get("type", "")).lower()
        handler = getattr(self, f"_on_{etype}", None)
        if handler is None:
            return False, f"Unknown event type '{etype}'."
        with self._lock:
            try:
                ok, msg = handler(event)
            except (KeyError, ValueError, TypeError) as exc:
                return False, f"Invalid event: {exc}"
            snap = self._snapshot() if ok else None
        if ok:
            self._notify(snap)
        return ok, msg

    def snapshot(self):
        with self._lock:
            return self._snapshot()

    # -- helpers ----------------------------------------------------------
    def _device(self, event):
        did = str(event["device_id"]).strip().upper()
        if did not in self.devices:
            raise KeyError(f"device '{did}' is not registered")
        return self.devices[did]

    def _touch(self, dev):
        dev.last_update = _hms(_now())

    def _log(self, device_id, message, level="info"):
        self.log.appendleft({"time": _hms(_now()), "device_id": device_id,
                             "message": message, "level": level})

    def _refresh_alert_status(self, dev):
        open_types = {a.type for a in self.alerts
                      if a.device_id == dev.device_id and a.status == "UNRESOLVED"}
        dev.alert_status = "SOS" if "SOS" in open_types else ("FALL" if "FALL" in open_types else "NONE")

    def _ensure_active(self, dev):
        if dev.status != "ACTIVE":
            dev.status = "ACTIVE"
            self._log(dev.device_id, "DEVICE ACTIVATED (by emergency event)", "info")

    # -- event handlers ---------------------------------------------------
    def _on_activate(self, e):
        dev = self._device(e)
        dev.status = "ACTIVE"
        self._touch(dev)
        self._log(dev.device_id, "DEVICE ACTIVATED", "ok")
        return True, f"{dev.device_id} is now ACTIVE."

    def _on_deactivate(self, e):
        dev = self._device(e)
        dev.status = "OFFLINE"
        self._touch(dev)
        self._log(dev.device_id, "DEVICE DEACTIVATED", "muted")
        return True, f"{dev.device_id} is now OFFLINE (last location kept)."

    def _on_location(self, e):
        dev = self._device(e)
        lat, lon = float(e["latitude"]), float(e["longitude"])
        if not (-90 <= lat <= 90 and -180 <= lon <= 180):
            raise ValueError("latitude/longitude out of range")
        dev.latitude, dev.longitude = lat, lon
        dev.zone = zone_for(lat, lon)
        self._touch(dev)
        self._log(dev.device_id, f"LOCATION UPDATED ({lat:.6f}, {lon:.6f}) - {dev.zone}", "info")
        return True, f"{dev.device_id} moved to {lat:.6f}, {lon:.6f} ({dev.zone})."

    def _raise_alert(self, e, kind, text):
        dev = self._device(e)
        self._ensure_active(dev)
        self._touch(dev)
        self._alert_seq += 1
        self.alerts.append(Alert(
            alert_id=self._alert_seq, device_id=dev.device_id, type=kind,
            timestamp=_hms(_now()), latitude=dev.latitude, longitude=dev.longitude,
            zone=dev.zone))
        self._refresh_alert_status(dev)
        self._log(dev.device_id, text, "sos" if kind == "SOS" else "fall")
        return True, f"{kind} alert raised for {dev.device_id}."

    def _on_sos(self, e):
        return self._raise_alert(e, "SOS", "SOS PRESSED")

    def _on_fall(self, e):
        return self._raise_alert(e, "FALL", "FALL DETECTED")

    def _on_heart_rate(self, e):
        dev = self._device(e)
        v = int(e["value"])
        if not 0 <= v <= 250:
            raise ValueError("heart rate must be 0-250")
        dev.heart_rate = v
        self._touch(dev)
        self._log(dev.device_id, f"HEART RATE {v} BPM", "info")
        return True, f"{dev.device_id} heart rate = {v} BPM."

    def _on_battery(self, e):
        dev = self._device(e)
        v = int(e["value"])
        if not 0 <= v <= 100:
            raise ValueError("battery must be 0-100")
        dev.battery = v
        self._touch(dev)
        self._log(dev.device_id, f"BATTERY {v}%", "warn" if v <= 20 else "info")
        return True, f"{dev.device_id} battery = {v}%."

    def _on_clear_alert(self, e):
        targets = []
        if e.get("alert_id") is not None:
            aid = int(e["alert_id"])
            targets = [a for a in self.alerts if a.alert_id == aid and a.status == "UNRESOLVED"]
        else:
            dev = self._device(e)
            targets = [a for a in self.alerts if a.device_id == dev.device_id and a.status == "UNRESOLVED"]
        if not targets:
            return False, "No unresolved alerts to acknowledge."
        for a in targets:
            a.status = "ACKNOWLEDGED"
            self._log(a.device_id, f"{a.type} ALERT ACKNOWLEDGED", "ok")
            self._refresh_alert_status(self.devices[a.device_id])
            self._touch(self.devices[a.device_id])
        return True, f"Acknowledged {len(targets)} alert(s)."

    # -- snapshot (the ONLY structure the dashboard consumes) -------------
    def _snapshot(self):
        devices = list(self.devices.values())
        active = [d for d in devices if d.status == "ACTIVE"]
        open_alerts = [a for a in self.alerts if a.status == "UNRESOLVED"]
        zone_counts = {z["name"]: 0 for z in ZONES}
        zone_counts["Unzoned"] = 0
        for d in active:
            zone_counts[d.zone] = zone_counts.get(d.zone, 0) + 1
        return {
            "mode": "SIMULATION",
            "summary": {
                "total": len(devices),
                "active": len(active),
                "offline": len(devices) - len(active),
                "sos": sum(1 for a in open_alerts if a.type == "SOS"),
                "fall": sum(1 for a in open_alerts if a.type == "FALL"),
            },
            "devices": [asdict(d) for d in devices],
            "alerts": [asdict(a) for a in reversed(self.alerts)],  # newest first
            "log": list(self.log),
            "zones": [{"name": n, "active": c} for n, c in zone_counts.items()
                      if n != "Unzoned" or c],
            "zone_defs": ZONES,
        }
