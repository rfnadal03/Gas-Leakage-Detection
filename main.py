import socket
import time
import numpy as np
import pandas as pd
import paho.mqtt.client as mqtt
import joblib
import RPi.GPIO as GPIO
import warnings
warnings.filterwarnings("ignore", category=UserWarning)

# Load trained model, scaler, and label encoder
model = joblib.load("random_forest_model.pkl")
scaler = joblib.load("scaler.pkl")
label_encoder = joblib.load("label_encoder.pkl")

BUZZER_PIN = 17  # Change to your preferred GPIO pin
GPIO.setmode(GPIO.BCM)
GPIO.setup(BUZZER_PIN, GPIO.OUT)

# MQTT Settings
MQTT_BROKER = "192.168.120.33"  # Replace with actual broker IP
MQTT_TOPIC_DISPLAY = "smoke/status"
MQTT_TOPIC_ALERT = "smoke/alert"
MQTT_TOPIC_BUTTON = "smoke/button"

# Smoke detection variables
smoke_start_time = None
smoke_detected = False
cooldown_active = False
waiting_for_reset = False  # Ensures no data is received after STOP

def on_message(client, userdata, message):
    global waiting_for_reset, cooldown_active, smoke_detected, smoke_start_time, client_socket  
    msg = message.payload.decode()
    print(f"[SERVER] Received MQTT message: {msg}")  # Debugging line
    
    if msg == "RESET":
        print("[SERVER] RESET command received. Resuming data reception...")
        GPIO.output(BUZZER_PIN, GPIO.LOW)  # Stop buzzer when reset is received
        waiting_for_reset = False  # Allow client to resume sending
        cooldown_active = False  # Reset cooldown so future smoke alerts can occur
        smoke_detected = False  # Reset smoke detection flag
        smoke_start_time = None  # Reset smoke timer

        # Ensure client_socket is valid before sending RESET
        if client_socket:
            try:
                client_socket.sendall("RESET".encode())  # Inform client
                print("[SERVER] Sent RESET command to client.")
            except Exception as e:
                print(f"[SERVER] Error sending RESET to client: {e}")

# Start Socket Server
HOST = "192.168.120.33"
PORT = 5000

server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_socket.bind((HOST, PORT))
server_socket.listen(1)
print(f"[SERVER] Listening on {HOST}:{PORT}...")

client_socket, addr = server_socket.accept()  # Client must connect first!
print(f"[SERVER] Client connected from {addr}")

# Now start MQTT (AFTER client_socket is valid)
mqtt_client = mqtt.Client()
mqtt_client.on_message = on_message  # Ensure function is defined BEFORE this line
mqtt_client.connect(MQTT_BROKER, 1883, 60)
mqtt_client.subscribe(MQTT_TOPIC_BUTTON)
mqtt_client.loop_start()

try:
    while True:
        if waiting_for_reset:
            GPIO.output(BUZZER_PIN, GPIO.HIGH)  # Activate buzzer when waiting for RESET
            print("[SERVER] Waiting for RESET command...")
            time.sleep(1)
            continue  # Skip receiving data if waiting for reset

        try:
            data = client_socket.recv(1024).decode().strip()
            if not data:
                break

            # Convert received data into array
            try:
                sensor_values = np.array([list(map(float, data.split(",")))])
            except ValueError:
                print("[SERVER] Received invalid sensor data format.")
                continue

            # Convert to DataFrame and normalize
            sensor_values_df = pd.DataFrame(sensor_values)
            sensor_values_scaled = scaler.transform(sensor_values_df)

            # Classify using ML model
            prediction = model.predict(sensor_values_scaled)
            detected_class_name = label_encoder.inverse_transform(prediction)[0]
            print(f"[SERVER] Detected: {detected_class_name}")

            # Send detected gas type to MQTT Mobile App
            mqtt_client.publish(MQTT_TOPIC_DISPLAY, f"Detected Gas: {detected_class_name}")

            # Handle smoke detection and alerting
            if detected_class_name == "Smoke":
                if not smoke_detected and not cooldown_active:
                    smoke_start_time = time.time()
                    smoke_detected = True
                    print("[SERVER] Smoke detected, monitoring duration...")

                elif smoke_detected and time.time() - smoke_start_time > 9:
                    print("[SERVER] Smoke persisted for 9s! Triggering alarm...")
                    GPIO.output(BUZZER_PIN, GPIO.HIGH)
                    mqtt_client.publish(MQTT_TOPIC_ALERT, "Smoke confirmed! Alarm triggered.")
                    mqtt_client.publish(MQTT_TOPIC_BUTTON, "ENABLE")  # Enable app button
                    client_socket.sendall("STOP".encode())  # Stop smoke detection
                    
                    # Prevent repeated alerts
                    cooldown_active = True
                    smoke_detected = False
                    waiting_for_reset = True  # Wait for RESET command

            else:
                smoke_detected = False  # Reset if no smoke detected

            time.sleep(1)

        except Exception as e:
            print(f"[SERVER] Error: {e}")
            break

except KeyboardInterrupt:
    print("\n[SERVER] Stopping server...")

# Cleanup
GPIO.cleanup()
client_socket.close()
server_socket.close()
mqtt_client.loop_stop()
print("[SERVER] Disconnected.")
