# TrackSafe Monitoring Station (SIMULATION MODE)

Prototype monitoring dashboard. **No hardware is used** - all data is typed into the PyCharm console.

## Run (PyCharm)
1. Open the `TrackSafe` folder as a project.
2. Create/select a Python 3.9+ interpreter, then install: `pip install -r requirements.txt`
3. Run `app.py`. Answer the setup questions in the Run window; the browser opens at http://127.0.0.1:5000
4. Type commands in the console (name or number): activate, deactivate, location, sos, fall,
   heart_rate, battery, clear_alert, show_devices, exit.

Note: map tiles and JS libraries (Leaflet, Socket.IO) load from the internet, so you need a connection.
Devices start OFFLINE - run `activate` to put them on the map.

## Architecture
    simulator.py (input layer)  ->  models.py TrackSafeProcessor.process(event)  ->  Socket.IO "state"  ->  dashboard.js
- `models.py` - Device / Alert models, zone logic, event handlers. Knows nothing about the input source.
- `simulator.py` - console input only. Builds event dicts (see the contract at top of `models.py`).
- `app.py` - Flask + Flask-SocketIO; pushes a full snapshot to browsers after every change.
- The dashboard only consumes the snapshot. The ACKNOWLEDGE button uses the same processor.

## Switching to ESP32 / LoRa later
Write a `SerialInput` class (pyserial) that reads lines from the receiver, converts each into an event dict
(e.g. `{"type": "sos", "device_id": "TS003"}`) and calls `processor.process(event)`. In `app.py`, start it
instead of `ConsoleInput`. Dashboard and data layer stay unchanged. Real GPS packets would map to the
`location` event; unknown device IDs could auto-register via `processor.register_device()`.

## Customising
Edit `ZONES` in `models.py` to match your trail area (name, centre, radius in metres).
