import paho.mqtt.client as mqtt
import time

def on_connect(client, userdata, flags, rc):
    print("[ORQUESTADOR LOCAL] Conectado al tubo transoceanico MQTT (test.mosquitto.org).")
    client.subscribe("polydim/latent/bridge/1973/status")

def on_message(client, userdata, msg):
    print(f"[RADAR GLOBAL] {msg.topic} -> {msg.payload.decode('utf-8')}")

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message

print("[ORQUESTADOR LOCAL] Desplegando radares. Esperando que las Nubes despierten...")
try:
    client.connect("test.mosquitto.org", 1883, 60)
    client.loop_start()
except Exception as e:
    print(f"Error conectando radar: {e}")

while True:
    time.sleep(1)
