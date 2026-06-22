import os, time, json, uuid, threading
from pathlib import Path
from datetime import datetime, timezone
import requests
from flask import Flask

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
TWELVE_API_KEY = os.getenv("TWELVE_API_KEY")

API = f"https://api.telegram.org/bot{BOT_TOKEN}"
DATA_FILE = Path("bot_data.json")

PAIRS = {
    "EURUSD": {"name": "EUR/USD", "symbol": "EUR/USD"},
    "GBPUSD": {"name": "GBP/USD", "symbol": "GBP/USD"},
    "AUDUSD": {"name": "AUD/USD", "symbol": "AUD/USD"},
    "USDJPY": {"name": "USD/JPY", "symbol": "USD/JPY"},
    "USDCAD": {"name": "USD/CAD", "symbol": "USD/CAD"},
    "USDCHF": {"name": "USD/CHF", "symbol": "USD/CHF"},
    "NZDUSD": {"name": "NZD/USD", "symbol": "NZD/USD"},
}

DEFAULT_DATA = {
    "last_update_id": None,
    "session": "",
    "messages_to_delete": [],
    "signals": 0,
    "wins": 0,
    "losses": 0,
    "history": []
}

last_update_id = None


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
    data = load_data()
    return session and session == data.get("session")


def remember_message(message_id):
    if not message_id:
        return
    data = load_data()
    arr = data.get("messages_to_delete", [])
    if message_id not in arr:
        arr.append(message_id)
    data["messages_to_delete"] = arr[-25:]
    save_data(data)


def clean_chat():
    data = load_data()
    for mid in data.get("messages_to_delete", []):
        try:
            requests.post(
                f"{API}/deleteMessage",
                json={"chat_id": CHAT_ID, "message_id": mid},
                timeout=8
            )
        except Exception:
            pass
    data["messages_to_delete"] = []
    save_data(data)


def send_message(text, keyboard=None):
    payload = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }
    if keyboard:
        payload["reply_markup"] = keyboard

    try:
        r = requests.post(f"{API}/sendMessage", json=payload, timeout=15)
        return r.json().get("result", {}).get("message_id")
    except Exception:
        return None


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


def answer_callback(callback_id):
    try:
        requests.post(f"{API}/answerCallbackQuery", json={"callback_query_id": callback_id}, timeout=8)
    except Exception:
        pass


def button(text, data):
    return {"text": text, "callback_data": data}


def main_menu(session):
    return {
        "inline_keyboard": [
            [button("📈 Forex mercado real", f"menu_forex:{session}")],
            [button("📊 Estadísticas", f"stats:{session}")],
            [button("🧹 Limpiar chat", f"reset:{session}")]
        ]
    }


def forex_menu(session):
    rows = []
    for code, p in PAIRS.items():
        rows.append([button(p["name"], f"pair:{code}:{session}")])
    rows.append([button("⬅️ Volver", f"back:{session}")])
    return {"inline_keyboard": rows}


def expiry_menu(pair_code, session):
    return {
        "inline_keyboard": [
            [button("1 minuto", f"expiry:{pair_code}:1:{session}")],
            [button("2 minutos", f"expiry:{pair_code}:2:{session}")],
            [button("3 minutos", f"expiry:{pair_code}:3:{session}")],
            [button("5 minutos", f"expiry:{pair_code}:5:{session}")],
            [button("⬅️ Volver", f"menu_forex:{session}")]
        ]
    }


def result_keyboard(signal_id, session):
    return {
        "inline_keyboard": [
            [
                button("✅ WIN", f"win:{signal_id}:{session}"),
                button("❌ LOSS", f"loss:{signal_id}:{session}")
            ],
            [button("📊 Estadísticas", f"stats:{session}")],
            [button("🧹 Limpiar chat", f"reset:{session}")]
        ]
    }


def sma(values, period):
    if len(values) < period:
        return sum(values) / len(values)
    return sum(values[-period:]) / period


def ema(values, period):
    if len(values) < period:
        return sum(values) / len(values)
    k = 2 / (period + 1)
    e = values[0]
    for v in values[1:]:
        e = v * k + e * (1 - k)
    return e


def rsi(values, period=14):
    if len(values) < period + 1:
        return 50
    gains, losses = [], []
    for i in range(-period, 0):
        diff = values[i] - values[i - 1]
        gains.append(max(diff, 0))
        losses.append(abs(min(diff, 0)))
    avg_gain = sum(gains) / period
    avg_loss = sum(losses) / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def atr(highs, lows, closes, period=14):
    if len(closes) < period + 1:
        return 0
    trs = []
    start = len(closes) - period
    for i in range(start, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1])
        )
        trs.append(tr)
    return sum(trs) / len(trs)


def macd(values):
    if len(values) < 35:
        return 0, 0
    macd_values = []
    for i in range(35, len(values) + 1):
        part = values[:i]
        macd_values.append(ema(part, 12) - ema(part, 26))
    line = macd_values[-1]
    signal = ema(macd_values, 9)
    return line, signal


def parse_dt(dt_text):
    try:
        return datetime.strptime(dt_text, "%Y-%m-%d %H:%M:%S").replace(tzinfo=timezone.utc)
    except Exception:
        return None


def fetch_candles(symbol):
    if not TWELVE_API_KEY:
        raise Exception("API_KEY_NO_CONFIGURADA")

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
        msg = str(response)
        if "apikey" in msg.lower() or "401" in msg:
            raise Exception("API_KEY_INVALIDA")
        raise Exception("DATOS_NO_DISPONIBLES")

    candles = list(reversed(response["values"]))

    return {
        "datetime": [c["datetime"] for c in candles],
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
    dts = data["datetime"]

    last_candle_time = parse_dt(dts[-1])
    candle_age_minutes = 999
    if last_candle_time:
        candle_age_minutes = (datetime.now(timezone.utc) - last_candle_time).total_seconds() / 60

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

    atr_values = []
    for i in range(40, len(closes)):
        v = atr(highs[:i], lows[:i], closes[:i])
        if v > 0:
            atr_values.append(v)
    atr_avg = sum(atr_values[-30:]) / len(atr_values[-30:]) if atr_values else atr_value

    volatility = round(max(1, min(100, (atr_value / atr_avg) * 60))) if atr_avg else 1

    support = min(lows[-25:])
    resistance = max(highs[-25:])
    candle_range = highs[-1] - lows[-1]
    body = abs(last - open_last)

    buy = 0
    sell = 0

    if last > ema9: buy += 10
    else: sell += 10

    if ema9 > ema21: buy += 15
    else: sell += 15

    if ema21 > ema50: buy += 15
    else: sell += 15

    if last > ema200: buy += 10
    else: sell += 10

    if rsi_value > 55: buy += 15
    elif rsi_value < 45: sell += 15

    if macd_line > macd_signal: buy += 15
    else: sell += 15

    if last > previous: buy += 10
    else: sell += 10

    if body > candle_range * 0.45 if candle_range else False:
        if last > open_last:
            buy += 10
        else:
            sell += 10

    if abs(last - support) < atr_value * 1.2:
        buy += 8

    if abs(resistance - last) < atr_value * 1.2:
        sell += 8

    buy = round(max(1, min(100, buy)))
    sell = round(max(1, min(100, sell)))

    direction = "BUY" if buy > sell else "SELL"
    strength = buy if direction == "BUY" else sell
    opposite = sell if direction == "BUY" else buy
    difference = abs(buy - sell)

    reversal = round(max(5, min(95, (opposite / max(strength + opposite, 1)) * 100)))

    market_closed = candle_age_minutes > 10 or volatility < 15
    weak_market = volatility < 25
    indecisive = strength < 72 or difference < 25 or reversal > 42

    if market_closed:
        title = "⏸ MERCADO CERRADO O SIN MOVIMIENTO"
        recommendation = "⛔ Recomendación: NO ENTRAR"
        trade = False

    elif weak_market:
        title = "🟡 MERCADO MUY LENTO"
        recommendation = "⚠️ Mejor esperar más volatilidad."
        trade = False

    elif indecisive:
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
        "buy": buy,
        "sell": sell,
        "recommendation": recommendation,
        "trade": trade,
        "candle_age": round(candle_age_minutes, 1),
        "rsi": round(rsi_value, 1),
        "macd": "BUY" if macd_line > macd_signal else "SELL",
        "ema": "BUY" if ema9 > ema21 > ema50 else "SELL" if ema9 < ema21 < ema50 else "NEUTRAL"
    }


def signal_text(signal):
    return f"""🖤💛 <b>El_Caballo_AI_Pro</b>

🔎 Análisis terminado para <b>{signal["pair_name"]}</b>

{signal["title"]}
📊 <b>{signal["pair_name"]}</b>

⏱ Expiración: <b>{signal["expiry"]} minuto(s)</b>
🎯 Probabilidad/Fuerza: <b>{signal["strength"]}/100</b>
🔄 Riesgo de reversión: <b>{signal["reversal"]}/100</b>
📈 Volatilidad: <b>{signal["volatility"]}/100</b>

📊 Fuerza compra: <b>{signal["buy"]}/100</b>
📊 Fuerza venta: <b>{signal["sell"]}/100</b>

📌 RSI: <b>{signal["rsi"]}</b>
📌 MACD: <b>{signal["macd"]}</b>
📌 EMAs: <b>{signal["ema"]}</b>

{signal["recommendation"]}"""


def register_signal(signal):
    data = load_data()
    signal_id = uuid.uuid4().hex[:8]
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
    data["history"] = data["history"][-100:]
    save_data(data)
    return signal_id


def stats_text():
    data = load_data()
    total = data.get("wins", 0) + data.get("losses", 0)
    rate = round((data.get("wins", 0) / total) * 100, 1) if total else 0

    return f"""🖤💛 <b>El_Caballo_AI_Pro</b>

📊 <b>Estadísticas</b>

✅ Wins: <b>{data.get("wins", 0)}</b>
❌ Losses: <b>{data.get("losses", 0)}</b>
🎯 Efectividad: <b>{rate}%</b>
📌 Señales registradas: <b>{data.get("signals", 0)}</b>"""


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


def safe_error_text(e):
    msg = str(e)

    if "API_KEY_INVALIDA" in msg:
        return "⚠️ TwelveData rechazó la API Key. Revisa que la key esté activa."
    if "API_KEY_NO_CONFIGURADA" in msg:
        return "⚠️ Falta TWELVE_API_KEY en Railway Variables."
    if "DATOS_NO_DISPONIBLES" in msg:
        return "⚠️ No hay datos disponibles ahora. Puede ser mercado cerrado o límite de API."
    return "⚠️ No pude analizar el mercado ahora. Intenta otra vez en unos minutos."


def run_analysis(pair_code, expiry, session):
    try:
        time.sleep(2)
        signal = analyze_pair(pair_code, expiry)

        clean_chat()

        if signal["trade"]:
            signal_id = register_signal(signal)
            mid = send_message(signal_text(signal), result_keyboard(signal_id, session))
        else:
            mid = send_message(signal_text(signal), main_menu(session))

        remember_message(mid)
        return

    except Exception as e:
        clean_chat()
        mid = send_message(safe_error_text(e), main_menu(session))
        remember_message(mid)
        return


def handle_message(message):
    global last_update_id

    text = message.get("text", "")
    chat_id = str(message.get("chat", {}).get("id", ""))

    if CHAT_ID and chat_id != str(CHAT_ID):
        return

    if text in ["/start", "/reset"]:
        clean_chat()
        session = new_session()
        mid = send_message("🖤💛 <b>El_Caballo_AI_Pro</b>\n\nSelecciona una opción:", main_menu(session))
        remember_message(mid)


def handle_callback(callback):
    answer_callback(callback["id"])

    chat_id = callback["message"]["chat"]["id"]
    msg_id = callback["message"]["message_id"]
    parts = callback["data"].split(":")

    cmd = parts[0]
    session = parts[-1] if len(parts) > 1 else ""

    if cmd != "reset" and not valid_session(session):
        return

    if cmd != "reset":
        remember_message(msg_id)

    if cmd == "reset":
        clean_chat()
        session = new_session()
        mid = send_message("✅ Bot reiniciado.\n\n🖤💛 <b>El_Caballo_AI_Pro</b>\n\nSelecciona una opción:", main_menu(session))
        remember_message(mid)

    elif cmd == "menu_forex":
        edit_message(chat_id, msg_id, "📈 <b>Selecciona el par Forex mercado real:</b>", forex_menu(session))

    elif cmd == "back":
        edit_message(chat_id, msg_id, "🖤💛 <b>El_Caballo_AI_Pro</b>\n\nSelecciona una opción:", main_menu(session))

    elif cmd == "pair":
        pair_code = parts[1]
        edit_message(chat_id, msg_id, f"⏱ <b>Selecciona expiración para {PAIRS[pair_code]['name']}:</b>", expiry_menu(pair_code, session))

    elif cmd == "expiry":
        pair_code = parts[1]
        expiry = int(parts[2])
        edit_message(chat_id, msg_id, f"🔎 Analizando <b>{PAIRS[pair_code]['name']}</b>...\nEspera unos segundos.")
        threading.Thread(target=run_analysis, args=(pair_code, expiry, session), daemon=True).start()

    elif cmd == "stats":
        edit_message(chat_id, msg_id, stats_text(), main_menu(session))

    elif cmd in ["win", "loss"]:
        signal_id = parts[1]
        result = "WIN" if cmd == "win" else "LOSS"
        ok = update_result(signal_id, result)
        text = "✅ Resultado guardado." if ok else "⚠️ Ese resultado ya fue registrado."
        edit_message(chat_id, msg_id, text + "\n\n" + stats_text(), main_menu(session))


def telegram_loop():
    global last_update_id

    data = load_data()
    last_update_id = data.get("last_update_id")

    while True:
        try:
            params = {"timeout": 30}
            if last_update_id is not None:
                params["offset"] = last_update_id + 1

            r = requests.get(f"{API}/getUpdates", params=params, timeout=35)
            updates = r.json().get("result", [])

            for u in updates:
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
    return "El_Caballo_AI_Pro activo"


@app.route("/webhook", methods=["POST"])
def webhook():
    return {"ok": True, "mode": "telegram polling"}, 200


if __name__ == "__main__":
    print("El_Caballo_AI_Pro limpio activo")
    threading.Thread(target=telegram_loop, daemon=True).start()
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
