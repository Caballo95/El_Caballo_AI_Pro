import os
import time
import json
import uuid
import threading
from pathlib import Path

import requests
from flask import Flask

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
TWELVE_API_KEY = os.getenv("TWELVE_API_KEY")

API = f"https://api.telegram.org/bot{BOT_TOKEN}"
DATA_FILE = Path("bot_data.json")

last_update_id = None

PAIRS = {
    "EURUSD": {"name": "EUR/USD", "symbol": "EUR/USD"},
    "AUDUSD": {"name": "AUD/USD", "symbol": "AUD/USD"},
    "AUDCAD": {"name": "AUD/CAD", "symbol": "AUD/CAD"},
    "AUDCHF": {"name": "AUD/CHF", "symbol": "AUD/CHF"},
    "AUDNZD": {"name": "AUD/NZD", "symbol": "AUD/NZD"},
    "GBPUSD": {"name": "GBP/USD", "symbol": "GBP/USD"},
    "GBPCAD": {"name": "GBP/CAD", "symbol": "GBP/CAD"},
    "GBPJPY": {"name": "GBP/JPY", "symbol": "GBP/JPY"},
}

DEFAULT_DATA = {
    "last_update_id": None,
    "session": "",
    "messages_to_delete": [],
    "selected_pair": None,
    "selected_expiry": None,
    "signals": 0,
    "wins": 0,
    "losses": 0,
    "history": []
}


def load_data():
    if DATA_FILE.exists():
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            for k, v in DEFAULT_DATA.items():
                data.setdefault(k, v)
            return data
        except Exception:
            return DEFAULT_DATA.copy()
    return DEFAULT_DATA.copy()


def save_data(data):
    DATA_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def new_session():
    data = load_data()
    data["session"] = uuid.uuid4().hex[:10]
    data["messages_to_delete"] = []
    save_data(data)
    return data["session"]


def valid_session(session):
    return session == load_data().get("session")


def send_message(text, keyboard=None):
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    if keyboard:
        payload["reply_markup"] = keyboard

    r = requests.post(f"{API}/sendMessage", json=payload, timeout=15)
    result = r.json()
    return result.get("result", {}).get("message_id")


def edit_message(chat_id, message_id, text, keyboard=None):
    payload = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML"
    }
    if keyboard:
        payload["reply_markup"] = keyboard

    try:
        requests.post(f"{API}/editMessageText", json=payload, timeout=15)
    except Exception:
        pass


def delete_message(chat_id, message_id):
    try:
        requests.post(
            f"{API}/deleteMessage",
            json={"chat_id": chat_id, "message_id": message_id},
            timeout=10
        )
    except Exception:
        pass


def remember_message(message_id):
    if not message_id:
        return

    data = load_data()
    ids = data.get("messages_to_delete", [])

    if message_id not in ids:
        ids.append(message_id)

    data["messages_to_delete"] = ids[-30:]
    save_data(data)


def clean_chat():
    data = load_data()
    ids = data.get("messages_to_delete", [])

    for mid in ids:
        delete_message(CHAT_ID, mid)

    data["messages_to_delete"] = []
    save_data(data)


def answer_callback(callback_id):
    try:
        requests.post(
            f"{API}/answerCallbackQuery",
            json={"callback_query_id": callback_id},
            timeout=10
        )
    except Exception:
        pass


def main_menu(session):
    return {
        "inline_keyboard": [
            [{"text": "📈 Forex mercado real", "callback_data": f"menu_forex:{session}"}],
            [{"text": "📊 Estadísticas", "callback_data": f"stats:{session}"}],
            [{"text": "🧹 Limpiar chat", "callback_data": f"reset:{session}"}]
        ]
    }


def forex_menu(session):
    items = list(PAIRS.items())
    rows = []

    for i in range(0, len(items), 2):
        row = []
        for code, info in items[i:i + 2]:
            row.append({
                "text": info["name"],
                "callback_data": f"pair:{code}:{session}"
            })
        rows.append(row)

    rows.append([{"text": "⬅️ Volver", "callback_data": f"back:{session}"}])
    return {"inline_keyboard": rows}


def expiry_menu(pair, session):
    return {
        "inline_keyboard": [
            [{"text": "1 minuto", "callback_data": f"expiry:{pair}:1:{session}"}],
            [{"text": "3 minutos", "callback_data": f"expiry:{pair}:3:{session}"}],
            [{"text": "5 minutos", "callback_data": f"expiry:{pair}:5:{session}"}],
            [{"text": "⬅️ Volver", "callback_data": f"menu_forex:{session}"}]
        ]
    }


def result_keyboard(signal_id, session):
    return {
        "inline_keyboard": [
            [
                {"text": "✅ WIN", "callback_data": f"win:{signal_id}:{session}"},
                {"text": "❌ LOSS", "callback_data": f"loss:{signal_id}:{session}"}
            ],
            [{"text": "📊 Estadísticas", "callback_data": f"stats:{session}"}],
            [{"text": "🧹 Limpiar chat", "callback_data": f"reset:{session}"}]
        ]
    }


def stats_text():
    data = load_data()
    wins = data.get("wins", 0)
    losses = data.get("losses", 0)
    total = wins + losses
    rate = round((wins / total) * 100, 2) if total else 0

    return f"""📊 <b>Estadísticas El_Caballo_AI_Pro</b>

⭐ Señales generadas: <b>{data.get("signals", 0)}</b>
✅ WIN: <b>{wins}</b>
❌ LOSS: <b>{losses}</b>
🎯 Win rate marcado por ti: <b>{rate}%</b>
"""


def ema(values, length):
    if not values:
        return 0

    values = values[-length * 4:]
    k = 2 / (length + 1)
    result = values[0]

    for value in values[1:]:
        result = value * k + result * (1 - k)

    return result


def rsi(closes, length=14):
    if len(closes) < length + 1:
        return 50

    gains = []
    losses = []

    for i in range(1, len(closes)):
        diff = closes[i] - closes[i - 1]
        gains.append(max(diff, 0))
        losses.append(abs(min(diff, 0)))

    avg_gain = sum(gains[-length:]) / length
    avg_loss = sum(losses[-length:]) / length

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def atr(highs, lows, closes, length=14):
    if len(closes) < length + 1:
        return 0

    values = []

    for i in range(1, len(closes)):
        values.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1])
        ))

    return sum(values[-length:]) / length


def macd(closes):
    if len(closes) < 35:
        return 0, 0

    macd_values = []

    for i in range(35, len(closes) + 1):
        part = closes[:i]
        fast = ema(part, 12)
        slow = ema(part, 26)
        macd_values.append(fast - slow)

    line = macd_values[-1]
    signal = ema(macd_values, 9)

    return line, signal


def fetch_candles(symbol):

    response = requests.get(
        "https://api.twelvedata.com/time_series",
        params={
            "symbol": symbol,
            "interval": "1min",
            "outputsize": 220,
            "apikey": TWELVE_API_KEY
        },
        timeout=20
    ).json()

    if "values" not in response:
        raise Exception(str(response))

    candles = list(reversed(response["values"]))

    return {
        "open": [float(c["open"]) for c in candles],
        "high": [float(c["high"]) for c in candles],
        "low": [float(c["low"]) for c in candles],
        "close": [float(c["close"]) for c in candles],
    }


def analyze_pair(pair_code, expiry):
    pair = PAIRS[pair_code]
    data = fetch_candles(pair["symbol"])

    opens = data["open"]
    highs = data["high"]
    lows = data["low"]
    closes = data["close"]

    last = closes[-1]
    previous = closes[-2]
    open_last = opens[-1]

    ema9 = ema(closes, 9)
    ema21 = ema(closes, 21)
    ema50 = ema(closes, 50)
    ema200 = ema(closes, 200)

    rsi_value = rsi(closes)
    macd_line, macd_signal = macd(closes)
    atr_value = atr(highs, lows, closes)

    support = min(lows[-25:])
    resistance = max(highs[-25:])

    candle_range = highs[-1] - lows[-1]
    body = abs(last - open_last)
    body_ratio = body / candle_range if candle_range else 0

    bull_candle = last > open_last and body_ratio >= 0.45
    bear_candle = last < open_last and body_ratio >= 0.45

    near_support = last <= support + atr_value * 0.8
    near_resistance = last >= resistance - atr_value * 0.8

    up_exhausted = closes[-1] > closes[-2] > closes[-3] > closes[-4]
    down_exhausted = closes[-1] < closes[-2] < closes[-3] < closes[-4]

    buy = 0
    sell = 0

    if ema9 > ema21:
        buy += 18
    else:
        sell += 18

    if ema50 > ema200:
        buy += 14
    else:
        sell += 14

    if last > ema50:
        buy += 12
    else:
        sell += 12

    if macd_line > macd_signal:
        buy += 16
    else:
        sell += 16

    if 42 <= rsi_value <= 68:
        buy += 14
    if 32 <= rsi_value <= 58:
        sell += 14

    if bull_candle:
        buy += 14
    if bear_candle:
        sell += 14

    if near_support:
        buy += 8
    if near_resistance:
        sell += 8

    if rsi_value > 74:
        buy -= 14
        sell += 5

    if rsi_value < 26:
        sell -= 14
        buy += 5

    if up_exhausted:
        buy -= 10

    if down_exhausted:
        sell -= 10

    buy = max(1, min(100, buy))
    sell = max(1, min(100, sell))

    direction = "BUY" if buy > sell else "SELL"
    strength = buy if direction == "BUY" else sell
    opposite = sell if direction == "BUY" else buy
    difference = abs(buy - sell)

    atr_avg = sum([
        atr(highs[:i], lows[:i], closes[:i])
        for i in range(40, len(closes))
        if atr(highs[:i], lows[:i], closes[:i]) > 0
    ][-30:]) or atr_value

    volatility = round(max(1, min(100, (atr_value / atr_avg) * 60))) if atr_avg else 50

    reversal = round(max(5, min(65, (opposite / max(strength + opposite, 1)) * 100 + (12 if difference < 20 else 0))))

    if strength < 72 or difference < 25 or reversal > 42:
        title = "🟡 MERCADO INDECISO"
        recommendation = "⚠️ Señal débil. Mejor esperar confirmación."
        trade = False
    elif direction == "BUY":
        title = "🟢 COMPRA ARRIBA"
        recommendation = "✅ Recomendación: ENTRAR AHORA"
        trade = True
    else:
        title = "🔴 VENTA ABAJO"
        recommendation = "✅ Recomendación: ENTRAR AHORA"
        trade = True

    return {
        "pair_code": pair_code,
        "pair_name": pair["name"],
        "expiry": expiry,
        "title": title,
        "direction": direction,
        "strength": round(strength),
        "reversal": reversal,
        "volatility": volatility,
        "buy": round(buy),
        "sell": round(sell),
        "recommendation": recommendation,
        "trade": trade
    }


def signal_text(signal):
    return f"""🖤💛 <b>El_Caballo_AI_Pro</b>

🔍 Análisis terminado para <b>{signal["pair_name"]}</b>

{signal["title"]}
📊 <b>{signal["pair_name"]}</b>

⏱ Expiración: <b>{signal["expiry"]} minuto(s)</b>
🎯 Fuerza de señal según mercado: <b>{signal["strength"]}/100</b>
🔄 Riesgo de reversión: <b>{signal["reversal"]}/100</b>
📈 Volatilidad: <b>{signal["volatility"]}/100</b>

📊 Fuerza compra: <b>{signal["buy"]}/100</b>
📊 Fuerza venta: <b>{signal["sell"]}/100</b>

{signal["recommendation"]}
"""


def register_signal(signal):
    data = load_data()
    signal_id = str(int(time.time() * 1000))

    data["signals"] += 1
    data["history"].append({
        "id": signal_id,
        "pair": signal["pair_name"],
        "direction": signal["direction"],
        "expiry": signal["expiry"],
        "strength": signal["strength"],
        "reversal": signal["reversal"],
        "volatility": signal["volatility"],
        "result": "PENDING",
        "time": time.strftime("%Y-%m-%d %H:%M:%S")
    })

    save_data(data)
    return signal_id


def run_analysis(pair_code, expiry, session):
    try:
        time.sleep(10)

        signal = analyze_pair(pair_code, expiry)

        clean_chat()

        if signal["trade"]:
            signal_id = register_signal(signal)
            mid = send_message(signal_text(signal), result_keyboard(signal_id, session))
        else:
            mid = send_message(signal_text(signal), main_menu(session))

        remember_message(mid)

    except Exception as e:
        clean_chat()
        mid = send_message(f"⚠️ Error analizando el mercado:\n<code>{str(e)}</code>", main_menu(session))
        remember_message(mid)


def update_result(signal_id, result):
    data = load_data()

    for item in data["history"]:
        if item["id"] == signal_id:
            if item["result"] != "PENDING":
                return False

            item["result"] = result

            if result == "WIN":
                data["wins"] += 1
            else:
                data["losses"] += 1

            save_data(data)
            return True

    return False


def handle_callback(callback):
    answer_callback(callback["id"])

    chat_id = callback["message"]["chat"]["id"]
    msg_id = callback["message"]["message_id"]
    parts = callback["data"].split(":")

    cmd = parts[0]
    session = parts[-1] if len(parts) > 1 else ""

    if cmd != "reset" and not valid_session(session):
        edit_message(chat_id, msg_id, "⚠️ Este botón es viejo. Escribe /start para abrir el menú nuevo.")
        return

    if cmd != "reset":
        remember_message(msg_id)

    if cmd == "reset":
        clean_chat()
        session = new_session()
        edit_message(
            chat_id,
            msg_id,
            "🖤💛 <b>El_Caballo_AI_Pro</b>\n\nSelecciona una opción:",
            main_menu(session)
        )

    elif cmd == "menu_forex":
        edit_message(chat_id, msg_id, "📈 <b>Selecciona el par Forex mercado real:</b>", forex_menu(session))

    elif cmd == "back":
        edit_message(chat_id, msg_id, "🖤💛 <b>El_Caballo_AI_Pro</b>\n\nSelecciona una opción:", main_menu(session))

    elif cmd == "pair":
        pair = parts[1]
        edit_message(chat_id, msg_id, f"⏱ <b>Selecciona expiración para {PAIRS[pair]['name']}:</b>", expiry_menu(pair, session))

    elif cmd == "expiry":
        pair = parts[1]
        expiry = parts[2]

        data = load_data()
        data["selected_pair"] = pair
        data["selected_expiry"] = expiry
        save_data(data)

        clean_chat()

        mid = send_message(
            f"🔎 Analizando <b>{PAIRS[pair]['name']}</b>...\n"
            f"⏱ Expiración seleccionada: <b>{expiry} minuto(s)</b>\n\n"
            f"📊 Leyendo velas reales e indicadores...",
            None
        )
        remember_message(mid)

        threading.Thread(target=run_analysis, args=(pair, expiry, session), daemon=True).start()

    elif cmd == "stats":
        edit_message(chat_id, msg_id, stats_text(), main_menu(session))

    elif cmd == "win":
        signal_id = parts[1]
        ok = update_result(signal_id, "WIN")
        msg = "✅ Resultado guardado como WIN." if ok else "⚠️ Esta señal ya fue marcada."
        edit_message(chat_id, msg_id, msg + "\n\n" + stats_text(), main_menu(session))

    elif cmd == "loss":
        signal_id = parts[1]
        ok = update_result(signal_id, "LOSS")
        msg = "❌ Resultado guardado como LOSS." if ok else "⚠️ Esta señal ya fue marcada."
        edit_message(chat_id, msg_id, msg + "\n\n" + stats_text(), main_menu(session))


def handle_message(message):
    text = message.get("text", "")

    if text == "/start":
        clean_chat()
        session = new_session()
        mid = send_message("🖤💛 <b>El_Caballo_AI_Pro</b>\n\nSelecciona una opción:", main_menu(session))
        remember_message(mid)

    elif text == "/reset":
        clean_chat()
        session = new_session()
        mid = send_message("✅ Bot reiniciado.\n\n🖤💛 <b>El_Caballo_AI_Pro</b>\n\nSelecciona una opción:", main_menu(session))
        remember_message(mid)


def telegram_loop():
    global last_update_id

    last_update_id = load_data().get("last_update_id")

    while True:
        try:
            params = {"timeout": 30}

            if last_update_id is not None:
                params["offset"] = last_update_id + 1

            r = requests.get(f"{API}/getUpdates", params=params, timeout=35)

            for u in r.json().get("result", []):
                last_update_id = u["update_id"]

                data = load_data()
                data["last_update_id"] = last_update_id
                save_data(data)

                if "callback_query" in u:
                    handle_callback(u["callback_query"])
                elif "message" in u:
                    handle_message(u["message"])

        except Exception as e:
            print("TELEGRAM LOOP ERROR:", e)
            time.sleep(5)


app = Flask(__name__)


@app.route("/", methods=["GET"])
def home():
    return "El_Caballo_AI_Pro limpio activo"


@app.route("/webhook", methods=["POST"])
def webhook():
    return {"ok": True, "mode": "direct telegram analysis"}, 200


if __name__ == "__main__":
    print("El_Caballo_AI_Pro limpio activo")
    threading.Thread(target=telegram_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.getenv("PORT", 8080)))
