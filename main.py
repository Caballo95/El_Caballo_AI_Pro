import os
import time
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

last_update_id = None

def send_message(text, keyboard=None):
    data = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    if keyboard:
        data["reply_markup"] = keyboard
    requests.post(f"{API}/sendMessage", json=data)

def main_menu():
    return {
        "inline_keyboard": [
            [{"text": "🌙 OTC", "callback_data": "menu_otc"}],
            [{"text": "📈 Forex", "callback_data": "menu_forex"}],
            [{"text": "📊 Estadísticas", "callback_data": "stats"}],
            [{"text": "⏸ Detener señales", "callback_data": "stop"}]
        ]
    }

def otc_menu():
    return {
        "inline_keyboard": [
            [{"text": "EUR/USD OTC", "callback_data": "signal_EURUSD_OTC"}],
            [{"text": "GBP/USD OTC", "callback_data": "signal_GBPUSD_OTC"}],
            [{"text": "USD/JPY OTC", "callback_data": "signal_USDJPY_OTC"}],
            [{"text": "⬅️ Volver", "callback_data": "back"}]
        ]
    }

def analyze_pair(pair):
    # Por ahora es estructura base. Luego aquí irá el motor real con indicadores.
    return (
        f"🐎 <b>El_Caballo_AI_Pro</b>\n\n"
        f"📊 Analizando: <b>{pair}</b>\n"
        f"⏱ Expiración: <b>1M</b>\n\n"
        f"⚠️ Motor de análisis en preparación.\n"
        f"Próximo paso: agregar EMA, RSI, MACD, ADX, CCI, Alligator y score inteligente."
    )

def handle_callback(data):
    if data == "menu_otc":
        send_message("🌙 Selecciona un par OTC:", otc_menu())

    elif data == "menu_forex":
        send_message("📈 Forex estará disponible después de terminar OTC.", main_menu())

    elif data == "stats":
        send_message("📊 Estadísticas todavía no disponibles. Primero activaremos el motor de señales.", main_menu())

    elif data == "stop":
        send_message("⏸ Señales detenidas temporalmente.", main_menu())

    elif data == "back":
        send_message("🐎 Menú principal:", main_menu())

    elif data.startswith("signal_"):
        pair = data.replace("signal_", "").replace("_", " ")
        send_message(analyze_pair(pair), main_menu())

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
                    send_message("🐎 <b>El_Caballo_AI_Pro</b>\n\nSelecciona una opción:", main_menu())

            if "callback_query" in update:
                callback = update["callback_query"]
                handle_callback(callback["data"])

    except Exception as e:
        print("Error:", e)

print("El_Caballo_AI_Pro activo 24/7")
send_message("🐎 El_Caballo_AI_Pro actualizado con menú principal.")

while True:
    get_updates()
    time.sleep(2)
