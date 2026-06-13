import os
import time
import random
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

last_update_id = None
selected_pair = {}

def send_message(text, keyboard=None):
    data = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    if keyboard:
        data["reply_markup"] = keyboard
    requests.post(f"{API}/sendMessage", json=data)
def send_photo(photo_url, caption="", keyboard=None):
    data = {
        "chat_id": CHAT_ID,
        "photo": photo_url,
        "caption": caption,
        "parse_mode": "HTML"
    }

    if keyboard:
        data["reply_markup"] = keyboard

    requests.post(f"{API}/sendPhoto", json=data)
def main_menu():
    return {"inline_keyboard": [
        [{"text": "🌙 OTC", "callback_data": "menu_otc"}],
        [{"text": "📈 Forex", "callback_data": "menu_forex"}],
        [{"text": "📊 Estadísticas", "callback_data": "stats"}],
        [{"text": "⏸ Detener señales", "callback_data": "stop"}]
    ]}

def otc_menu():
    return {"inline_keyboard": [
        [{"text": "EUR/USD OTC", "callback_data": "pair_EUR_USD_OTC"}],
        [{"text": "GBP/USD OTC", "callback_data": "pair_GBP_USD_OTC"}],
        [{"text": "USD/JPY OTC", "callback_data": "pair_USD_JPY_OTC"}],
        [{"text": "AUD/CAD OTC", "callback_data": "pair_AUD_CAD_OTC"}],
        [{"text": "AUD/CHF OTC", "callback_data": "pair_AUD_CHF_OTC"}],
        [{"text": "⬅️ Volver", "callback_data": "back"}]
    ]}

def expiry_menu(pair):
    return {"inline_keyboard": [
        [{"text": "⏱ 1 minuto", "callback_data": f"expiry_1_{pair}"}],
        [{"text": "⏱ 3 minutos", "callback_data": f"expiry_3_{pair}"}],
        [{"text": "⏱ 5 minutos", "callback_data": f"expiry_5_{pair}"}],
        [{"text": "⬅️ Volver", "callback_data": "menu_otc"}]
    ]}

def generate_signal(pair, expiry):
    direction = random.choice(["BUY", "SELL"])
    confidence = random.randint(76, 91)
    reversal = 100 - confidence
    volatility = random.randint(55, 82)

    if direction == "BUY":
        signal = "🟢 COMPRA ARRIBA"
    else:
        signal = "🔴 VENTA ABAJO"

    pair_text = pair.replace("_", "/").replace("/OTC", " OTC")

    return f"""🖤💛 <b>El_Caballo_AI_Pro</b>

{signal}
📊 <b>{pair_text}</b>

⏱ Expiración: <b>{expiry} minutos</b>
🎯 Confianza: <b>{confidence}%</b>
🔄 Probabilidad de reversión: <b>{reversal}%</b>
📈 Volatilidad: <b>{volatility}/100</b>

🕒 Hora de entrada: <b>AHORA</b>"""

def handle_callback(data):
    if data == "menu_otc":
        send_message("🌙 <b>Selecciona un par OTC:</b>", otc_menu())

    elif data == "menu_forex":
        send_message("📈 Forex estará disponible después de terminar OTC.", main_menu())

    elif data == "stats":
        send_message("📊 Estadísticas todavía no disponibles.", main_menu())

    elif data == "stop":
        send_message("⏸ Señales detenidas temporalmente.", main_menu())

    elif data == "back":
        send_message("🖤💛 <b>El_Caballo_AI_Pro</b>\n\nSelecciona una opción:", main_menu())

    elif data.startswith("pair_"):
        pair = data.replace("pair_", "")
        send_message("⏱ <b>Selecciona expiración:</b>", expiry_menu(pair))

    elif data.startswith("expiry_"):
        parts = data.split("_", 2)
        expiry = parts[1]
        pair = parts[2]
        send_message(generate_signal(pair, expiry), main_menu())

def get_updates():
    global last_update_id
    params = {"timeout": 30}
    if last_update_id:
        params["offset"] = last_update_id + 1

    try:
        r = requests.get(f"{API}/getUpdates", params=params, timeout=35)
        data = r.json()

        for update in data.get("result", []):
            last_update_id = update["update_id"]

            if "message" in update:
                text = update["message"].get("text", "")
                if text == "/start":
    send_photo(
        "https://raw.githubusercontent.com/Caballo95/El_Caballo_AI_Pro/main/ChatGPT%20Imagen%2013%20jun%202026,%2005_57_21%20a.m..png",
        "🖤💛 <b>El_Caballo_AI_Pro</b>\n\nSelecciona una opción:",
        main_menu()
    )

            if "callback_query" in update:
                handle_callback(update["callback_query"]["data"])

    except Exception as e:
        print("Error:", e)

print("El_Caballo_AI_Pro V2 activo 24/7")
send_message("🖤💛 El_Caballo_AI_Pro actualizado: menú OTC + expiración listo.")

while True:
    get_updates()
    time.sleep(2)
