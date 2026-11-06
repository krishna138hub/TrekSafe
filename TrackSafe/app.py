"""
TrackSafe Monitoring Station - SIMULATION MODE.

Run this file from PyCharm. It starts the Flask/Socket.IO server in a background
thread, then runs the console input layer in the main thread (PyCharm Run window).
"""
import logging
import threading
import webbrowser
import serial

from flask import Flask, jsonify, render_template
from flask_socketio import SocketIO, emit

from models import TrackSafeProcessor
from simulator import ConsoleInput

HOST, PORT = "127.0.0.1", 5000

app = Flask(__name__)
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")
processor = TrackSafeProcessor()
esp32_serial = None

def serial_listener():
    global esp32_serial
    esp32_serial = serial.Serial("COM3", 115200, timeout=1)
    ser = esp32_serial

    print("ESP32 serial listener connected on COM3")

    while True:
        line = ser.readline().decode(errors="ignore").strip()

        if line == "SOS BUTTON PRESSED!":
            processor.process({
                "type": "sos",
                "device_id": "TS001"
            })
            print("TrackSafe: SOS event received from ESP32")

        if line == "FALL DETECTED!":
            processor.process({
                "type": "fall",
                "device_id": "TS001"
            })
            print("TrackSafe: FALL event received from ESP32")

# Every change in the data layer is pushed to all connected browsers.
processor.add_listener(lambda snap: socketio.emit("state", snap))


@app.route("/")
def dashboard():
    return render_template("dashboard.html")


@app.route("/api/state")
def api_state():
    return jsonify(processor.snapshot())


@socketio.on("connect")
def on_connect():
    emit("state", processor.snapshot())


@socketio.on("acknowledge")
def on_acknowledge(data):
    # Dashboard button goes through the same processor as any other input.
    processor.process({"type": "clear_alert", "alert_id": data.get("alert_id")})


def run_server():
    socketio.run(app, host=HOST, port=PORT, debug=False, use_reloader=False,
                 allow_unsafe_werkzeug=True)


if __name__ == "__main__":
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    threading.Thread(target=serial_listener, daemon=True).start()
    threading.Thread(target=run_server, daemon=True).start()

    print(f"TrackSafe server starting on http://{HOST}:{PORT}")

    console = ConsoleInput(processor, on_ready=lambda: webbrowser.open(f"http://{HOST}:{PORT}"))
    console.run()
    
