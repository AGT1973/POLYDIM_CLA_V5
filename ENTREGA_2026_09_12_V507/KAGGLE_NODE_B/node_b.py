import os
os.system('pip install paho-mqtt')
import torch
import numpy as np
import time
import paho.mqtt.client as mqtt
from transformers import AutoModelForCausalLM
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("NODE_B")

tensor_recibido = None

def on_connect(client, userdata, flags, rc):
    logger.info("Conectado al tubo MQTT desde el segundo cluster de Google.")
    client.subscribe("polydim/latent/bridge/1973/transfer")

def on_message(client, userdata, msg):
    global tensor_recibido
    logger.info("!!! IMPACTO BINARIO RECIBIDO EN EL TUBO !!!")
    # Transformamos el bloque binario crudo directo a RAM sin parsear JSON (DPI-compliant)
    raw_bytes = msg.payload
    array_np = np.frombuffer(raw_bytes, dtype=np.float16).reshape(1, 16, 3072)
    tensor_recibido = torch.tensor(array_np).to("cuda:0")
    logger.info("Tensor materializado exitosamente.")

client = mqtt.Client()
client.on_connect = on_connect
client.on_message = on_message
client.connect("test.mosquitto.org", 1883, 60)
client.loop_start()

client.publish("polydim/latent/bridge/1973/status", "NODE_B_BOOTING")

logger.info("Cargando Qwen 2.5 (Node B)...")
model = AutoModelForCausalLM.from_pretrained("Qwen/Qwen2.5-1.5B-Instruct", torch_dtype=torch.float16, device_map="cuda:0")

client.publish("polydim/latent/bridge/1973/status", "NODE_B_READY")

logger.info("Esperando inyeccion de tensor desde el otro lado del mundo...")
while tensor_recibido is None:
    time.sleep(1)

logger.info("Procesando la señal extraterrestre (Dimension Translation 3072 -> 1536)...")
tensor_reducido = tensor_recibido[:, :, :1536]

with torch.no_grad():
    salida = model.model.layers[0](tensor_reducido)[0]

logger.info(f"Mutacion Neuronal Aplicada. Norma resultante: {torch.norm(salida).item()}")
client.publish("polydim/latent/bridge/1973/status", "NODE_B_COMPLETED_MUTATION")
logger.info("Operacion Geopolitica Finalizada.")
time.sleep(5)
client.loop_stop()
