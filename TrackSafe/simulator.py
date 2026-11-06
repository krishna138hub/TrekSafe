"""
INPUT LAYER (prototype): manual console input from the PyCharm terminal.

This module only turns typed commands into structured events and hands them to
TrackSafeProcessor.process(). To use real hardware later, write another input
class (e.g. SerialInput reading ESP32 lines with pyserial) that builds the same
event dicts - nothing in models.py or the dashboard has to change.
"""

COMMANDS = ["activate", "deactivate", "location", "sos", "fall",
            "heart_rate", "battery", "return", "clear_alert",
            "show_devices", "exit"]

BANNER = """
========================================
       TRACKSAFE SIMULATION CONSOLE
========================================

Available commands:
"""


class ConsoleInput:
    def __init__(self, processor, on_ready=None):
        self.processor = processor
        self.on_ready = on_ready

    # ------------------------------------------------------------ helpers
    @staticmethod
    def _ask(prompt):
        return input(prompt).strip()

    def _ask_device(self):
        did = self._ask("Device ID: ").upper()
        if did not in self.processor.devices:
            print(f"  ! Unknown device. Registered: {', '.join(self.processor.devices)}")
            return None
        return did

    def _ask_number(self, prompt, cast=float):
        try:
            return cast(self._ask(prompt))
        except ValueError:
            print("  ! Not a valid number.")
            return None

    def _send(self, event):
        ok, msg = self.processor.process(event)
        print(("  OK  " if ok else "  !!  ") + msg)

    # -------------------------------------------------------------- setup
    def setup(self):
        print("\n=== TRACKSAFE - INITIAL SETUP (SIMULATION MODE) ===\n")
        while True:
            try:
                n = int(self._ask("Enter number of devices: "))
                if n > 0:
                    break
            except ValueError:
                pass
            print("  ! Enter a whole number greater than 0.")
        for i in range(1, n + 1):
            while True:
                default = f"TS{i:03d}"
                did = self._ask(f"Enter Device ID for device {i} [{default}]: ") or default
                ok, msg = self.processor.register_device(did)
                print("  " + msg)
                if ok:
                    break

    # --------------------------------------------------------------- loop
    def show_devices(self):
        print(f"\n{'ID':<8}{'STATUS':<9}{'ZONE':<13}{'LAT':<11}{'LON':<11}{'HR':<5}{'BAT':<6}ALERT")
        for d in self.processor.devices.values():
            print(f"{d.device_id:<8}{d.status:<9}{d.zone:<13}{d.latitude:<11.6f}"
                  f"{d.longitude:<11.6f}{d.heart_rate:<5}{d.battery:<6}{d.alert_status}")

    def _print_menu(self):
        print(BANNER)
        for i, c in enumerate(COMMANDS, 1):
            print(f"{i}. {c}")
        print("\n(type a command name or its number)")

    def run(self):
        self.setup()
        if self.on_ready:
            self.on_ready()
        self._print_menu()
        while True:
            try:
                raw = self._ask("\nEnter command: ").lower()
            except (EOFError, KeyboardInterrupt):
                break
            if raw.isdigit() and 1 <= int(raw) <= len(COMMANDS):
                raw = COMMANDS[int(raw) - 1]
            if raw in ("exit", "quit"):
                break
            if raw in ("help", "menu", "?"):
                self._print_menu()
            elif raw == "show_devices":
                self.show_devices()
            elif raw in ("activate", "deactivate", "sos", "fall", "return", "clear_alert"):
                did = self._ask_device()
                if did:
                    self._send({"type": raw, "device_id": did})
            elif raw == "location":
                did = self._ask_device()
                if did:
                    lat = self._ask_number("Latitude: ")
                    lon = self._ask_number("Longitude: ") if lat is not None else None
                    if lat is not None and lon is not None:
                        self._send({"type": "location", "device_id": did,
                                    "latitude": lat, "longitude": lon})
            elif raw in ("heart_rate", "battery"):
                did = self._ask_device()
                if did:
                    label = "Heart rate: " if raw == "heart_rate" else "Battery: "
                    val = self._ask_number(label, int)
                    if val is not None:
                        self._send({"type": raw, "device_id": did, "value": val})
            elif raw:
                print("  ! Unknown command. Type 'help' to see the list.")
        print("Shutting down TrackSafe simulation. Goodbye.")
