import os
import time
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")

def enviar_mensaje(texto):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    data = {
        "chat_id": CHAT_ID,
        "text": texto
    }
    requests.post(url, data=data)

print("El_Caballo_AI_Pro iniciado correctamente")

enviar_mensaje("🐎 El_Caballo_AI_Pro está conectado y funcionando.")

while True:
    time.sleep(300)
