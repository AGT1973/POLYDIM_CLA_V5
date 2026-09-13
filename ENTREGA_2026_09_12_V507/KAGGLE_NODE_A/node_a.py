import os
os.system('pip install paho-mqtt')
import torch
import numpy as np
import time
import paho.mqtt.client as mqtt
from transformers import AutoModelForCausalLM
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("NODE_A")

# Variables Globales
node_b_ready = False

def on_connect(client, userdata, flags, rc):
    logger.info("Conectado al tubo MQTT.")
    client.subscribe("polydim/latent/bridge/1973/status")

def on_message(client, userdata, msg):
    global node_b_ready
    payload = msg.payload.decode('utf-8')
    if payload == "NODE_B_READY":
        node_b_ready = True

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect("test.mosquitto.org", 1883, 60)
client.loop_start()

client.publish("polydim/latent/bridge/1973/status", "NODE_A_BOOTING")

logger.info("Cargando Phi-3 (Node A)...")
model = AutoModelForCausalLM.from_pretrained("microsoft/Phi-3-mini-4k-instruct", torch_dtype=torch.float16, device_map="cuda:0")

logger.info("Generando Tensor Latente D=3072...")
estado_latente = torch.randn(1, 16, 3072, dtype=torch.float16)

client.publish("polydim/latent/bridge/1973/status", "NODE_A_READY_WAITING_FOR_B")

logger.info("Esperando a que Node B despierte en el otro continente...")
while not node_b_ready:
    time.sleep(2)

logger.info("Node B esta listo. Disparando chorro binario puro (Tensor) por el Océano...")
tensor_bytes = estado_latente.cpu().numpy().tobytes()
client.publish("polydim/latent/bridge/1973/transfer", tensor_bytes, qos=1)

client.publish("polydim/latent/bridge/1973/status", "NODE_A_TENSOR_SENT")
logger.info("Mision de inyeccion completada.")
time.sleep(5)
client.loop_stop()
