import socket
import random
import time

SERVER_IP = "192.168.120.33"  # Change to your Raspberry Pi Server IP
PORT = 5000

# Sensor value ranges
RANGES = {
    "MQ2": (500, 830),
    "MQ3": (330, 550),
    "MQ5": (290, 600),
    "MQ6": (310, 530),
    "MQ7": (360, 800),
    "MQ8": (220, 800),
    "MQ135": (270, 590),
}

# Smoke detection value ranges
SMOKE_RANGES = {
    "MQ2": (510, 800),
    "MQ3": (330, 450),
    "MQ5": (290, 410),
    "MQ6": (320, 420),
    "MQ7": (550, 610),
    "MQ8": (540, 670),
    "MQ135": (270, 380),
}

def generate_sensor_data(smoke=False):
    """Generate random sensor data. If `smoke=True`, generate values in smoke range."""
    if smoke:
        return {sensor: random.randint(*SMOKE_RANGES[sensor]) for sensor in RANGES}
    else:
        return {sensor: random.randint(*RANGES[sensor]) for sensor in RANGES}

def main():
    client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client_socket.connect((SERVER_IP, PORT))
    client_socket.settimeout(1)  # Set timeout for non-blocking STOP message check

    print("[CLIENT] Connected to server.")

    stop_requested = False  # Flag to handle STOP command

    while True:
        if stop_requested:
            print("[CLIENT] Pipeline Closed. Waiting for RESET...")
            while True:
                try:
                    message = client_socket.recv(1024).decode()
                    if message == "RESET":
                        print("[CLIENT] RESET command received. Resuming emissions...")
                        stop_requested = False
                        break  # Exit waiting loop
                except socket.timeout:
                    pass  # Continue waiting

        # Send random values for 20 seconds (every 2 seconds)
        print("[CLIENT] Sending normal sensor values...")
        for _ in range(10):  # 10 iterations of 2s each = 20s
            sensor_data = generate_sensor_data(smoke=False)
            data_str = ",".join(str(sensor_data[key]) for key in sensor_data)
            client_socket.sendall(data_str.encode())
            print(f"[CLIENT] Sent data: {data_str}")
            time.sleep(2)  # **Now sending every 2 seconds**

        # Send smoke values for 15 seconds (every 2 seconds)
        print("[CLIENT] Switching to smoke emission...")
        for _ in range(7):  # 7 iterations of 2s each = 14s (approx. 15s)
            sensor_data = generate_sensor_data(smoke=True)
            data_str = ",".join(str(sensor_data[key]) for key in sensor_data)
            client_socket.sendall(data_str.encode())
            print(f"[CLIENT] Sent SMOKE data: {data_str}")
            time.sleep(2)  # **Now sending every 2 seconds**

            try:
                message = client_socket.recv(1024).decode()
                if message == "STOP":
                    print("[CLIENT] STOP command received. Halting pipeline.")
                    stop_requested = True
                    break  # Exit the smoke loop if STOP is received
            except socket.timeout:
                pass  # Continue sending if no STOP message is received

if __name__ == "__main__":
    main()
