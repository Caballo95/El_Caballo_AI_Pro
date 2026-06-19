import os
import time
import json
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
    "selected_pair": None,
    "selected_pair_name": None,
    "selected_expiry": None,
    "analysis_message_id": None,
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
    except Exception as e:
        print("SEND ERROR:", e)
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
    except Exception as e:
        print("EDIT ERROR:", e)


def delete_message(chat_id, message_id):
    try:
        requests.post(
            f"{API}/deleteMessage",
            json={"chat_id": chat_id, "message_id": message_id},
            timeout=15
        )
    except Exception as e:
        print("DELETE ERROR:", e)


def answer_callback(callback_id):
    try:
        requests.post(
            f"{API}/answerCallbackQuery",
            json={"callback_query_id": callback_id},
            timeout=10
        )
    except Exception:
        pass


def main_menu():
    return {
        "inline_keyboard": [
            [{"text": "📈 Forex mercado real", "callback_data": "menu_forex"}],
            [{"text": "📊 Estadísticas", "callback_data": "stats"}]
        ]
    }


def forex_menu():
    items = list(PAIRS.items())
    rows = []

    for i in range(0, len(items), 2):
        row = []
        for code, info in items[i:i + 2]:
            row.append({"text": info["name"], "callback_data": f"pair_{code}"})
        rows.append(row)

    rows.append([{"text": "⬅️ Volver", "callback_data": "back_main"}])
    return {"inline_keyboard": rows}


def expiry_menu(pair_code):
    return {
        "inline_keyboard": [
            [{"text": "1 minuto", "callback_data": f"expiry_{pair_code}_1"}],
            [{"text": "3 minutos", "callback_data": f"expiry_{pair_code}_3"}],
            [{"text": "5 minutos", "callback_data": f"expiry_{pair_code}_5"}],
            [{"text": "⬅️ Volver", "callback_data": "menu_forex"}]
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


def stats_text():
    data = load_data()
    wins = data.get("wins", 0)
    losses = data.get("losses", 0)
    closed = wins + losses
    rate = round((wins / closed) * 100, 2) if closed > 0 else 0

    return f"""📊 <b>Estadísticas El_Caballo_AI_Pro V10</b>

⭐ Señales totales: <b>{data.get("signals", 0)}</b>
✅ WIN: <b>{wins}</b>
❌ LOSS: <b>{losses}</b>
🎯 Win rate: <b>{rate}%</b>

📌 Par activo:
<b>{data.get("selected_pair_name") or "Ninguno"}</b>

⏱ Expiración activa:
<b>{data.get("selected_expiry") or "No seleccionada"} minuto(s)</b>
"""


def ema(values, length):
    if len(values) < length:
        length = len(values)
    k = 2 / (length + 1)
    result = values[0]
    for v in values[1:]:
        result = (v * k) + (result * (1 - k))
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

    trs = []
    for i in range(1, len(closes)):
        tr = max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i - 1]),
            abs(lows[i] - closes[i - 1])
        )
        trs.append(tr)

    return sum(trs[-length:]) / length


def macd(closes):
    macd_values = []

    for i in range(35, len(closes) + 1):
        part = closes[:i]
        fast = ema(part[-35:], 12)
        slow = ema(part[-35:], 26)
        macd_values.append(fast - slow)

    macd_line = macd_values[-1]
    signal_line = ema(macd_values[-9:], 9) if len(macd_values) >= 9 else macd_line
    return macd_line, signal_line


def fetch_candles(symbol):
    if not TWELVE_API_KEY:
        raise Exception("Falta TWELVE_API_KEY en Railway Variables")

    url = "https://api.twelvedata.com/time_series"
    params = {
        "symbol": symbol,
        "interval": "1min",
        "outputsize": 220,
        "apikey": TWELVE_API_KEY
    }

    response = requests.get(url, params=params, timeout=20).json()

    if "values" not in response:
        raise Exception(str(response))

    candles = list(reversed(response["values"]))

    return {
        "open": [float(x["open"]) for x in candles],
        "high": [float(x["high"]) for x in candles],
        "low": [float(x["low"]) for x in candles],
        "close": [float(x["close"]) for x in candles]
    }


def analyze_pair(pair_code, expiry):
    info = PAIRS[pair_code]
    candles = fetch_candles(info["symbol"])

    opens = candles["open"]
    highs = candles["high"]
    lows = candles["low"]
    closes = candles["close"]

    close = closes[-1]
    open_price = opens[-1]

    ema9 = ema(closes[-60:], 9)
    ema21 = ema(closes[-60:], 21)
    ema50 = ema(closes[-100:], 50)
    ema200 = ema(closes[-220:], 200)

    rsi_value = rsi(closes, 14)
    macd_line, macd_signal = macd(closes)

    atr_value = atr(highs, lows, closes, 14)
    atr_values = []

    for i in range(30, len(closes)):
        atr_values.append(atr(highs[:i], lows[:i], closes[:i], 14))

    atr_avg = sum(atr_values[-30:]) / len(atr_values[-30:]) if atr_values else atr_value
    volatility = round(max(1, min(100, (atr_value / atr_avg) * 60))) if atr_avg else 50

    support = min(lows[-25:])
    resistance = max(highs[-25:])

    body = abs(close - open_price)
    candle_range = highs[-1] - lows[-1]
    body_ratio = body / candle_range if candle_range else 0

    bull_candle = close > open_price and body_ratio >= 0.45
    bear_candle = close < open_price and body_ratio >= 0.45

    near_support = close <= support + atr_value * 0.8
    near_resistance = close >= resistance - atr_value * 0.8

    up_exhausted = closes[-1] > closes[-2] > closes[-3] > closes[-4]
    down_exhausted = closes[-1] < closes[-2] < closes[-3] < closes[-4]

    buy_score = 0
    sell_score = 0

    buy_score += 15 if ema9 > ema21 else 0
    sell_score += 15 if ema9 < ema21 else 0

    buy_score += 12 if ema50 > ema200 else 0
    sell_score += 12 if ema50 < ema200 else 0

    buy_score += 10 if close > ema50 else 0
    sell_score += 10 if close < ema50 else 0

    buy_score += 15 if 45 < rsi_value < 70 else 0
    sell_score += 15 if 30 < rsi_value < 55 else 0

    buy_score += 15 if macd_line > macd_signal else 0
    sell_score += 15 if macd_line < macd_signal else 0

    buy_score += 12 if bull_candle else 0
    sell_score += 12 if bear_candle else 0

    buy_score += 6 if near_support else 0
    sell_score += 6 if near_resistance else 0

    buy_score -= 10 if rsi_value > 75 else 0
    sell_score -= 10 if rsi_value < 25 else 0

    buy_score -= 8 if up_exhausted else 0
    sell_score -= 8 if down_exhausted else 0

    buy_score = max(1, min(94, buy_score))
    sell_score = max(1, min(94, sell_score))

    if buy_score > sell_score:
        direction = "BUY"
        probability = buy_score
        opposite = sell_score
    else:
        direction = "SELL"
        probability = sell_score
        opposite = buy_score

    diff = abs(buy_score - sell_score)

    reversal = round(max(5, min(49, (opposite / max(probability + opposite, 1)) * 100)))

    if diff < 10 or probability < 60:
        title = "🟡 MERCADO INDECISO"
        recommendation = "⚠️ Señal débil. Mejor esperar confirmación."
        signal_type = "NEUTRAL"
    elif direction == "BUY":
        title = "🟢 COMPRA ARRIBA"
        recommendation = "✅ Recomendación: ENTRAR AHORA"
        signal_type = "TRADE"
    else:
        title = "🔴 VENTA ABAJO"
        recommendation = "✅ Recomendación: ENTRAR AHORA"
        signal_type = "TRADE"

    return {
        "pair_code": pair_code,
        "pair_name": info["name"],
        "expiry": expiry,
        "title": title,
        "direction": direction,
        "signal_type": signal_type,
        "probability": round(probability),
        "reversal": reversal,
        "volatility": volatility,
        "buy_score": round(buy_score),
        "sell_score": round(sell_score),
        "recommendation": recommendation
    }


def signal_text(signal):
    return f"""🖤💛 <b>El_Caballo_AI_Pro V10</b>

🔍 Análisis terminado para <b>{signal["pair_name"]}</b>

{signal["title"]}
📊 <b>{signal["pair_name"]}</b>

⏱ Expiración: <b>{signal["expiry"]} minuto(s)</b>
🎯 Probabilidad de acierto: <b>{signal["probability"]}%</b>
🔄 Probabilidad de reversión: <b>{signal["reversal"]}%</b>
📈 Volatilidad: <b>{signal["volatility"]}/100</b>

📊 Fuerza compra: <b>{signal["buy_score"]}%</b>
📊 Fuerza venta: <b>{signal["sell_score"]}%</b>

{signal["recommendation"]}
"""


def register_signal(signal):
    data = load_data()
    signal_id = str(int(time.time() * 1000))

    data["signals"] = data.get("signals", 0) + 1
    data.setdefault("history", []).append({
        "id": signal_id,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "pair": signal["pair_name"],
        "direction": signal["direction"],
        "expiry": signal["expiry"],
        "probability": signal["probability"],
        "reversal": signal["reversal"],
        "volatility": signal["volatility"],
        "result": "PENDING"
    })

    save_data(data)
    return signal_id


def run_analysis(pair_code, expiry):
    data = load_data()
    msg_id = data.get("analysis_message_id")

    try:
        signal = analyze_pair(pair_code, expiry)

        if msg_id:
            delete_message(CHAT_ID, msg_id)
            data["analysis_message_id"] = None
            save_data(data)

        if signal["signal_type"] == "TRADE":
            signal_id = register_signal(signal)
            send_message(signal_text(signal), result_keyboard(signal_id))
        else:
            send_message(signal_text(signal), main_menu())

    except Exception as e:
        if msg_id:
            delete_message(CHAT_ID, msg_id)

        data["analysis_message_id"] = None
        save_data(data)

        send_message(
            f"⚠️ Error analizando el mercado:\n<code>{str(e)}</code>",
            main_menu()
        )


def update_result(signal_id, result):
    data = load_data()

    for item in data.get("history", []):
        if item.get("id") == signal_id:
            if item.get("result") != "PENDING":
                return False

            item["result"] = result

            if result == "WIN":
                data["wins"] = data.get("wins", 0) + 1
            else:
                data["losses"] = data.get("losses", 0) + 1

            save_data(data)
            return True

    return False


def handle_callback(callback):
    data = load_data()

    callback_id = callback["id"]
    chat_id = callback["message"]["chat"]["id"]
    message_id = callback["message"]["message_id"]
    action = callback["data"]

    answer_callback(callback_id)

    if action == "menu_forex":
        edit_message(
            chat_id,
            message_id,
            "📈 <b>Selecciona el par Forex mercado real:</b>",
            forex_menu()
        )

    elif action == "back_main":
        edit_message(
            chat_id,
            message_id,
            "🖤💛 <b>El_Caballo_AI_Pro V10</b>\n\nSelecciona una opción:",
            main_menu()
        )

    elif action.startswith("pair_"):
        pair_code = action.replace("pair_", "")

        if pair_code in PAIRS:
            data["selected_pair"] = pair_code
            data["selected_pair_name"] = PAIRS[pair_code]["name"]
            save_data(data)

            edit_message(
                chat_id,
                message_id,
                f"⏱ <b>Selecciona expiración para {PAIRS[pair_code]['name']}:</b>",
                expiry_menu(pair_code)
            )

    elif action.startswith("expiry_"):
        parts = action.split("_")
        expiry = parts[-1]
        pair_code = "_".join(parts[1:-1])

        if pair_code in PAIRS:
            data["selected_pair"] = pair_code
            data["selected_pair_name"] = PAIRS[pair_code]["name"]
            data["selected_expiry"] = expiry
            save_data(data)

            analyzing_id = send_message(
                f"🔎 Analizando <b>{PAIRS[pair_code]['name']}</b>...\n"
                f"⏱ Expiración seleccionada: <b>{expiry} minuto(s)</b>\n\n"
                f"📊 Leyendo velas e indicadores reales..."
            )

            data["analysis_message_id"] = analyzing_id
            save_data(data)

            threading.Thread(
                target=run_analysis,
                args=(pair_code, expiry),
                daemon=True
            ).start()

    elif action == "stats":
        edit_message(chat_id, message_id, stats_text(), main_menu())

    elif action.startswith("win_"):
        signal_id = action.replace("win_", "")
        ok = update_result(signal_id, "WIN")
        msg = "✅ Resultado guardado como WIN." if ok else "⚠️ Esta señal ya fue marcada."
        edit_message(chat_id, message_id, msg + "\n\n" + stats_text(), main_menu())

    elif action.startswith("loss_"):
        signal_id = action.replace("loss_", "")
        ok = update_result(signal_id, "LOSS")
        msg = "❌ Resultado guardado como LOSS." if ok else "⚠️ Esta señal ya fue marcada."
        edit_message(chat_id, message_id, msg + "\n\n" + stats_text(), main_menu())


def handle_message(message):
    text = message.get("text", "")

    if text == "/start":
        send_message(
            "🖤💛 <b>El_Caballo_AI_Pro V10</b>\n\nSelecciona una opción:",
            main_menu()
        )


def telegram_loop():
    global last_update_id

    while True:
        try:
            params = {"timeout": 30}

            if last_update_id is not None:
                params["offset"] = last_update_id + 1

            response = requests.get(f"{API}/getUpdates", params=params, timeout=35)
            updates = response.json().get("result", [])

            for update in updates:
                last_update_id = update["update_id"]

                if "callback_query" in update:
                    handle_callback(update["callback_query"])

                elif "message" in update:
                    handle_message(update["message"])

        except Exception as e:
            print("TELEGRAM LOOP ERROR:", e)
            time.sleep(5)


app = Flask(__name__)


@app.route("/", methods=["GET"])
def home():
    return "El_Caballo_AI_Pro V10 activo"


@app.route("/webhook", methods=["POST"])
def webhook():
    return {"ok": True, "mode": "V10 direct analysis"}, 200


def start_bot():
    print("El_Caballo_AI_Pro V10 activo")
    threading.Thread(target=telegram_loop, daemon=True).start()


if __name__ == "__main__":
    start_bot()
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
