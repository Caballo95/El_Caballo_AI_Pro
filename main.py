import os
import time
import random
import requests
import json
from pathlib import Path
from datetime import datetime
import pandas as pd
import yfinance as yf
import ta
BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

LEARNING_FILE = "learning_data.json"
last_update_id = None


def load_learning_data():
    if Path(LEARNING_FILE).exists():
        with open(LEARNING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)

    return {
        "total_signals": 0,
        "wins": 0,
        "losses": 0,
        "pairs": {},
        "strategies": {},
        "indicators": {},
        "expiries": {},
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

    r = requests.post(f"{API}/editMessageText", json=data)
    return r.json()


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
    pairs = [
        "EUR_USD_OTC",
        "GBP_USD_OTC",
        "AUD_CHF_OTC",
        "AUD_USD_OTC",
        "USD_JPY_OTC"
    ]

    keyboard = []
    for pair in pairs:
        keyboard.append([{
            "text": pair.replace("_", "/"),
            "callback_data": f"pair_{pair}"
        }])

    keyboard.append([{"text": "⬅️ Volver", "callback_data": "back_main"}])

    return {"inline_keyboard": keyboard}


def expiry_menu(pair):
    return {
        "inline_keyboard": [
            [{"text": "1 minuto", "callback_data": f"expiry_{pair}_1"}],
            [{"text": "2 minutos", "callback_data": f"expiry_{pair}_2"}],
            [{"text": "3 minutos", "callback_data": f"expiry_{pair}_3"}],
            [{"text": "5 minutos", "callback_data": f"expiry_{pair}_5"}],
            [{"text": "⬅️ Volver", "callback_data": "menu_otc"}]
        ]
    }


def result_keyboard(signal_id):
    return {
        "inline_keyboard": [
            [
                {"text": "✅ WIN", "callback_data": f"win_{signal_id}"},
                {"text": "❌ LOSS", "callback_data": f"loss_{signal_id}"}
            ],
            [{"text": "📊 Estadísticas", "callback_data": "stats"}]
        ]
    }


def pair_name(pair):
    return pair.replace("_", "/").replace("/OTC", " OTC")


def register_signal(pair, direction, expiry, confidence, reversal, volatility):
    signal_id = str(int(time.time()))

    signal_data = {
        "id": signal_id,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "pair": pair_name(pair),
        "direction": direction,
        "expiry": str(expiry),
        "confidence": confidence,
        "reversal": reversal,
        "volatility": volatility,
        "result": "PENDING",
        "strategy": "El_Caballo_AI_Pro",
        "indicators": {
            "confidence": confidence,
            "reversal": reversal,
            "volatility": volatility
        }
    }

    learning_data["total_signals"] = learning_data.get("total_signals", 0) + 1
    learning_data["history"].append(signal_data)
    save_learning_data(learning_data)

    return signal_id


def market_symbol(pair):
    symbols = {
        "EUR_USD": "EURUSD=X",
        "AUD_USD": "AUDUSD=X",
        "AUD_CAD": "AUDCAD=X",
        "AUD_CHF": "AUDCHF=X",
        "AUD_NZD": "AUDNZD=X",
    }
    return symbols.get(pair)


def analyze_real_market(pair):
    symbol = market_symbol(pair)
    if not symbol:
        return None

    df = yf.download(symbol, period="1d", interval="1m", progress=False)

    if df is None or df.empty or len(df) < 50:
        return None

    df["ema9"] = df["Close"].ewm(span=9, adjust=False).mean()
    df["ema21"] = df["Close"].ewm(span=21, adjust=False).mean()

    delta = df["Close"].diff()
    gain = delta.where(delta > 0, 0).rolling(window=7).mean()
    loss = -delta.where(delta < 0, 0).rolling(window=7).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))

    ema12 = df["Close"].ewm(span=12, adjust=False).mean()
    ema26 = df["Close"].ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()

    last = df.iloc[-1]
    prev = df.iloc[-2]

    candle_range = last["High"] - last["Low"]
    body = abs(last["Close"] - last["Open"])
    volatility = round((body / candle_range) * 100) if candle_range > 0 else 0

    buy = (
        last["ema9"] > last["ema21"]
        and last["rsi"] > 55
        and last["macd"] > last["macd_signal"]
        and last["Close"] > prev["Close"]
        and volatility >= 35
    )

    sell = (
        last["ema9"] < last["ema21"]
        and last["rsi"] < 45
        and last["macd"] < last["macd_signal"]
        and last["Close"] < prev["Close"]
        and volatility >= 35
    )

    if buy:
        return "BUY", 84, 16, volatility

    if sell:
        return "SELL", 84, 16, volatility

    return None


def generate_signal(pair, expiry):
    result = analyze_real_market(pair)

    if result is None:
        send_message(
            f"⚠️ <b>{pair_name(pair)}</b>\n\nNo hay confirmación fuerte ahora.\nEl bot no recomienda entrada.",
            main_menu()
        )
        return

    direction, confidence, reversal, volatility = result

    signal_text = "🟢 COMPRA ARRIBA" if direction == "BUY" else "🔴 VENTA ABAJO"

    signal_id = register_signal(
        pair,
        direction,
        expiry,
        confidence,
        reversal,
        volatility
    )

    text = f"""🖤💛 <b>El_Caballo_AI_Pro</b>

{signal_text}
📊 <b>{pair_name(pair)}</b>

⏱️ Expiración: <b>{expiry} minutos</b>
🎯 Confianza: <b>{confidence}%</b>
🔄 Probabilidad de reversión: <b>{reversal}%</b>
📈 Volatilidad: <b>{volatility}/100</b>

📌 Análisis real:
EMA 9 / EMA 21
RSI 7
MACD
Fuerza de vela

🕘 Hora de entrada: <b>AHORA</b>"""

    send_message(text, result_keyboard(signal_id))


def update_result(signal_id, result):
    found = False

    for item in learning_data.get("history", []):
        if item.get("id") == signal_id:
            if item.get("result") == "PENDING":
                item["result"] = result
                found = True

                pair = item.get("pair", "UNKNOWN")
                strategy = item.get("strategy", "DEFAULT")
                expiry = str(item.get("expiry", "0"))

                if pair not in learning_data["pairs"]:
                    learning_data["pairs"][pair] = {"wins": 0, "losses": 0}

                if strategy not in learning_data["strategies"]:
                    learning_data["strategies"][strategy] = {"wins": 0, "losses": 0}

                if expiry not in learning_data["expiries"]:
                    learning_data["expiries"][expiry] = {"wins": 0, "losses": 0}

                if result == "WIN":
                    learning_data["wins"] = learning_data.get("wins", 0) + 1
                    learning_data["pairs"][pair]["wins"] += 1
                    learning_data["strategies"][strategy]["wins"] += 1
                    learning_data["expiries"][expiry]["wins"] += 1

                elif result == "LOSS":
                    learning_data["losses"] = learning_data.get("losses", 0) + 1
                    learning_data["pairs"][pair]["losses"] += 1
                    learning_data["strategies"][strategy]["losses"] += 1
                    learning_data["expiries"][expiry]["losses"] += 1

                break

    save_learning_data(learning_data)
    return found


def stats_text():
    total = learning_data.get("total_signals", 0)
    wins = learning_data.get("wins", 0)
    losses = learning_data.get("losses", 0)
    win_rate = round((wins / (wins + losses)) * 100, 2) if (wins + losses) > 0 else 0

    text = f"""📊 <b>Estadísticas El_Caballo_AI_Pro</b>

⭐ Señales totales: <b>{total}</b>
✅ WIN: <b>{wins}</b>
❌ LOSS: <b>{losses}</b>
🎯 Win rate: <b>{win_rate}%</b>
"""

    text += "\n<b>📌 Pares:</b>\n"
    for pair, data in learning_data.get("pairs", {}).items():
        w = data.get("wins", 0)
        l = data.get("losses", 0)
        wr = round((w / (w + l)) * 100, 2) if (w + l) > 0 else 0
        text += f"{pair}: {w}W / {l}L — {wr}%\n"

    text += "\n<b>⏱️ Expiraciones:</b>\n"
    for expiry, data in learning_data.get("expiries", {}).items():
        w = data.get("wins", 0)
        l = data.get("losses", 0)
        wr = round((w / (w + l)) * 100, 2) if (w + l) > 0 else 0
        text += f"{expiry}m: {w}W / {l}L — {wr}%\n"

    return text


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
        edit_message(chat_id, message_id, stats_text(), main_menu())

    elif data == "stop":
        edit_message(chat_id, message_id, "⏸️ Señales detenidas temporalmente.", main_menu())

    elif data == "back_main":
        edit_message(chat_id, message_id, "🖤💛 <b>El_Caballo_AI_Pro</b>\n\nSelecciona una opción:", main_menu())

    elif data.startswith("pair_"):
        pair = data.replace("pair_", "")
        edit_message(
            chat_id,
            message_id,
            f"⏱️ <b>Selecciona expiración para {pair_name(pair)}:</b>",
            expiry_menu(pair)
        )

    elif data.startswith("expiry_"):
        parts = data.split("_")
        expiry = parts[-1]
        pair = "_".join(parts[1:-1])
        generate_signal(pair, expiry)

    elif data.startswith("win_"):
        signal_id = data.replace("win_", "")
        ok = update_result(signal_id, "WIN")
        msg = "✅ Resultado guardado como WIN." if ok else "⚠️ Esta señal ya fue marcada."
        edit_message(chat_id, message_id, msg + "\n\n" + stats_text(), main_menu())

    elif data.startswith("loss_"):
        signal_id = data.replace("loss_", "")
        ok = update_result(signal_id, "LOSS")
        msg = "❌ Resultado guardado como LOSS." if ok else "⚠️ Esta señal ya fue marcada."
        edit_message(chat_id, message_id, msg + "\n\n" + stats_text(), main_menu())


def handle_message(message):
    text = message.get("text", "")

    if text == "/start":
        send_message("🖤💛 <b>El_Caballo_AI_Pro</b>\n\nSelecciona una opción:", main_menu())


def get_updates():
    global last_update_id

    params = {}
    if last_update_id is not None:
        params["offset"] = last_update_id + 1

    r = requests.get(f"{API}/getUpdates", params=params)
    updates = r.json().get("result", [])

    for update in updates:
        last_update_id = update["update_id"]

        if "callback_query" in update:
            handle_callback(update["callback_query"])

        elif "message" in update:
            handle_message(update["message"])


def main():
    send_message("🤖 El_Caballo_AI_Pro activo.", main_menu())

    while True:
        try:
            get_updates()
            time.sleep(2)
        except Exception as e:
            print("Error:", e)
            time.sleep(5)


if __name__ == "__main__":
    main()
