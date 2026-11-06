import serial

ser = serial.Serial("COM4", 115200, timeout=1)

print("Connected to ESP32-S3 on COM4")

while True:
    line = ser.readline().decode(errors="ignore").strip()

    if line:
        print("ESP32:", line)