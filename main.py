import os
import time
import random
import requests
import json
from datetime import datetime
from pathlib import Path
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

last_update_id = None
LEARNING_FILE = "learning_data.json"

def load_learning_data():
    if Path(LEARNING_FILE).exists():
        with open(LEARNING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    return {
        "total_signals": 0,
        "wins": 0,
        "losses": 0,
        "strategies": {},
        "indicators": {},
        "history": []
    }


def save_learning_data(data):
    with open(LEARNING_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2)


learning_data = load_learning_data()

def send_message(text, keyboard=None):
    data = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    if keyboard:
        data["reply_markup"] = keyboard

    r = requests.post(f"{API}/sendMessage", json=data)
    return r.json()


def edit_message(chat_id, message_id, text, keyboard=None):
    data = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if keyboard:
        data["reply_markup"] = keyboard

    requests.post(f"{API}/editMessageText", json=data)


def answer_callback(callback_id):
    requests.post(
        f"{API}/answerCallbackQuery",
        json={"callback_query_id": callback_id}
    )


def main_menu():
    return {
        "inline_keyboard": [
            [{"text": "🌙 OTC", "callback_data": "menu_otc"}],
            [{"text": "📈 Forex", "callback_data": "menu_forex"}],
            [{"text": "📊 Estadísticas", "callback_data": "stats"}],
            [{"text": "⏸️ Detener señales", "callback_data": "stop"}]
        ]
    }


def otc_menu():
    return {
        "inline_keyboard": [
            [{"text": "EUR/USD OTC", "callback_data": "pair_EUR_USD_OTC"}],
            [{"text": "GBP/USD OTC", "callback_data": "pair_GBP_USD_OTC"}],
            [{"text": "USD/JPY OTC", "callback_data": "pair_USD_JPY_OTC"}],
            [{"text": "AUD/CAD OTC", "callback_data": "pair_AUD_CAD_OTC"}],
            [{"text": "AUD/CHF OTC", "callback_data": "pair_AUD_CHF_OTC"}],
            [{"text": "⬅️ Volver", "callback_data": "back_main"}]
        ]
    }


def expiry_menu(pair):
    return {
        "inline_keyboard": [
            [{"text": "⏱️ 1 minuto", "callback_data": f"expiry_1_{pair}"}],
            [{"text": "⏱️ 3 minutos", "callback_data": f"expiry_3_{pair}"}],
            [{"text": "⏱️ 5 minutos", "callback_data": f"expiry_5_{pair}"}],
            [{"text": "⬅️ Volver", "callback_data": "menu_otc"}]
        ]
    }


def pair_name(pair):
    return pair.replace("_", "/").replace("/OTC", " OTC")


def generate_signal(pair, expiry):
    # Temporal: luego quitaremos random y pondremos análisis real
    seed = int(time.time() // 60) + sum(ord(c) for c in pair) + int(expiry)
    rng = random.Random(seed)

    direction = rng.choice(["BUY", "SELL"])
    confidence = rng.randint(76, 91)
    reversal = 100 - confidence
    volatility = rng.randint(55, 82)

    signal = "🟢 COMPRA ARRIBA" if direction == "BUY" else "🔴 VENTA ABAJO"

    return f"""🖤💛 <b>El_Caballo_AI_Pro</b>

{signal}
📊 <b>{pair_name(pair)}</b>

⏱ Expiración: <b>{expiry} minutos</b>
🎯 Confianza: <b>{confidence}%</b>
🔄 Probabilidad de reversión: <b>{reversal}%</b>
📈 Volatilidad: <b>{volatility}/100</b>

🕒 Hora de entrada: <b>AHORA</b>"""


def handle_callback(callback):
    data = callback["data"]
    callback_id = callback["id"]
    chat_id = callback["message"]["chat"]["id"]
    message_id = callback["message"]["message_id"]

    answer_callback(callback_id)

    if data == "menu_otc":
        edit_message(chat_id, message_id, "🌙 <b>Selecciona un par OTC:</b>", otc_menu())

    elif data == "menu_forex":
        edit_message(chat_id, message_id, "📈 Forex estará disponible después de terminar OTC.", main_menu())

    elif data == "stats":
        edit_message(chat_id, message_id, "📊 Estadísticas todavía no disponibles.", main_menu())

    elif data == "stop":
        edit_message(chat_id, message_id, "⏸️ Señales detenidas temporalmente.", main_menu())

    elif data == "back_main":
        edit_message(
            chat_id,
            message_id,
            "🖤💛 <b>El_Caballo_AI_Pro</b>\n\nSelecciona una opción:",
            main_menu()
        )

    elif data.startswith("pair_"):
        pair = data.replace("pair_", "")
        edit_message(
            chat_id,
            message_id,
            f"⏱️ <b>Selecciona expiración para {pair_name(pair)}:</b>",
            expiry_menu(pair)
        )

    elif data.startswith("expiry_"):
        parts = data.split("_", 2)
        expiry = parts[1]
        pair = parts[2]
        edit_message(chat_id, message_id, generate_signal(pair, expiry), main_menu())


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
                    send_message(
                        "🖤💛 <b>El_Caballo_AI_Pro</b>\n\nSelecciona una opción:",
                        main_menu()
                    )

            if "callback_query" in update:
                handle_callback(update["callback_query"])

    except Exception as e:
        print("Error:", e)


print("El_Caballo_AI_Pro V3 menú limpio activo 24/7")

while True:
    get_updates()
    time.sleep(2)
