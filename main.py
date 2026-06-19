import os
import time
import json
import re
import threading
from pathlib import Path
from flask import Flask, request
import requests

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

DATA_FILE = Path("bot_data.json")
last_update_id = None

PAIRS = {
    "EURUSD": "EUR/USD",
    "AUDUSD": "AUD/USD",
    "AUDCAD": "AUD/CAD",
    "AUDCHF": "AUD/CHF",
    "AUDNZD": "AUD/NZD",
    "GBPUSD": "GBP/USD",
    "GBPCAD": "GBP/CAD",
    "GBPJPY": "GBP/JPY",
}

DEFAULT_DATA = {
    "selected_pair": None,
    "selected_pair_name": None,
    "selected_expiry": None,
    "pending_request": False,
    "requested_at": None,
    "signals": 0,
    "wins": 0,
    "losses": 0,
    "history": [],
    "latest_signals": {},
    "sent_ids": []
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


data = load_data()


def send_message(text, keyboard=None):
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    if keyboard:
        payload["reply_markup"] = keyboard
    try:
        requests.post(f"{API}/sendMessage", json=payload, timeout=10)
    except Exception as e:
        print("SEND ERROR:", e)


def edit_message(chat_id, message_id, text, keyboard=None):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"}
    if keyboard:
        payload["reply_markup"] = keyboard
    try:
        requests.post(f"{API}/editMessageText", json=payload, timeout=10)
    except Exception as e:
        print("EDIT ERROR:", e)


def answer_callback(callback_id):
    try:
        requests.post(f"{API}/answerCallbackQuery", json={"callback_query_id": callback_id}, timeout=10)
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
    rows = []
    for code, name in PAIRS.items():
        rows.append([{"text": name, "callback_data": f"pair_{code}"}])
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
    d = load_data()
    total = d.get("signals", 0)
    wins = d.get("wins", 0)
    losses = d.get("losses", 0)
    closed = wins + losses
    rate = round((wins / closed) * 100, 2) if closed > 0 else 0

    return f"""📊 <b>Estadísticas El_Caballo_AI_Pro</b>

⭐ Señales totales: <b>{total}</b>
✅ WIN: <b>{wins}</b>
❌ LOSS: <b>{losses}</b>
🎯 Win rate: <b>{rate}%</b>

📌 Par activo:
<b>{d.get("selected_pair_name") or "Ninguno seleccionado"}</b>

⏱ Expiración activa:
<b>{d.get("selected_expiry") or "No seleccionada"} minuto(s)</b>
"""


def normalize_pair(raw):
    if not raw:
        return None
    p = str(raw).upper()
    for s in ["FXCM:", "OANDA:", "FOREXCOM:", "CAPITALCOM:", "/", "-", "_", " "]:
        p = p.replace(s, "")
    for code in PAIRS:
        if code in p:
            return code
    return None


def safe_int(value, default=None):
    try:
        if value is None:
            return default
        return int(float(str(value).replace("%", "").strip()))
    except Exception:
        return default


def classify_signal(direction, probability, reversal):
    prob = safe_int(probability)
    rev = safe_int(reversal)

    if direction == "NEUTRAL":
        return "NEUTRAL", "🟡 MERCADO INDECISO", "⚠️ Recomendación: esperar confirmación"

    if prob is None or rev is None:
        if direction == "BUY":
            return "TRADE", "🟢 COMPRA ARRIBA", "✅ Recomendación: ENTRAR AHORA"
        if direction == "SELL":
            return "TRADE", "🔴 VENTA ABAJO", "✅ Recomendación: ENTRAR AHORA"

    if prob < 55 or rev > 45:
        return "NEUTRAL", "🟡 MERCADO INDECISO", "⚠️ Recomendación: NO operar / esperar confirmación"

    if 55 <= prob < 75 or 31 <= rev <= 45:
        return "NEUTRAL", "🟡 MERCADO INDECISO", "⚠️ Señal débil: operar con mucho cuidado"

    if direction == "BUY":
        return "TRADE", "🟢 COMPRA ARRIBA", "✅ Recomendación: ENTRAR AHORA"

    if direction == "SELL":
        return "TRADE", "🔴 VENTA ABAJO", "✅ Recomendación: ENTRAR AHORA"

    return "NEUTRAL", "🟡 MERCADO INDECISO", "⚠️ Recomendación: esperar confirmación"


def parse_tradingview_payload(payload):
    if isinstance(payload, dict):
        pair = payload.get("pair") or payload.get("symbol") or payload.get("ticker")
        direction = payload.get("direction") or payload.get("signal") or payload.get("side")
        probability = payload.get("probability") or payload.get("probabilidad") or payload.get("confidence")
        reversal = payload.get("reversal") or payload.get("reversion")
        volatility = payload.get("volatility") or payload.get("volatilidad")
    else:
        text = str(payload)
        pair_match = re.search(
            r"(EURUSD|AUDUSD|AUDCAD|AUDCHF|AUDNZD|GBPUSD|GBPCAD|GBPJPY|EUR/USD|AUD/USD|AUD/CAD|AUD/CHF|AUD/NZD|GBP/USD|GBP/CAD|GBP/JPY)",
            text.upper()
        )
        pair = pair_match.group(1) if pair_match else None

        upper = text.upper()
        if "INDECISO" in upper or "NEUTRAL" in upper:
            direction = "NEUTRAL"
        elif "COMPRA" in upper or "BUY" in upper or "CALL" in upper:
            direction = "BUY"
        elif "VENTA" in upper or "SELL" in upper or "PUT" in upper:
            direction = "SELL"
        else:
            direction = None

        probability_match = re.search(r"Probabilidad:\s*([0-9]+)", text, re.IGNORECASE)
        reversal_match = re.search(r"Reversi[oó]n:\s*([0-9]+)", text, re.IGNORECASE)
        volatility_match = re.search(r"Volatilidad:\s*([0-9]+)", text, re.IGNORECASE)

        probability = probability_match.group(1) if probability_match else None
        reversal = reversal_match.group(1) if reversal_match else None
        volatility = volatility_match.group(1) if volatility_match else None

    pair_code = normalize_pair(pair)
    if not pair_code or not direction:
        return None

    direction = str(direction).upper()

    if direction in ["BUY", "CALL", "COMPRA", "COMPRA ARRIBA"]:
        direction_clean = "BUY"
    elif direction in ["SELL", "PUT", "VENTA", "VENTA ABAJO"]:
        direction_clean = "SELL"
    elif direction in ["NEUTRAL", "INDECISO", "MERCADO INDECISO"]:
        direction_clean = "NEUTRAL"
    else:
        return None

    d = load_data()
    expiry = str(d.get("selected_expiry") or "1")

    signal_type, title, recommendation = classify_signal(direction_clean, probability, reversal)

    return {
        "pair_code": pair_code,
        "pair_name": PAIRS[pair_code],
        "direction": direction_clean,
        "signal_type": signal_type,
        "title": title,
        "expiry": expiry,
        "probability": str(probability if probability is not None else "N/A"),
        "reversal": str(reversal if reversal is not None else "N/A"),
        "volatility": str(volatility if volatility is not None else "N/A"),
        "recommendation": recommendation,
        "created_at": int(time.time())
    }


def build_signal_text(signal):
    return f"""🖤💛 <b>El_Caballo_AI_Pro V8</b>

{signal["title"]}
📊 <b>{signal["pair_name"]}</b>

⏱ Expiración: <b>{signal["expiry"]} minuto(s)</b>
🎯 Probabilidad: <b>{signal["probability"]}%</b>
🔄 Reversión: <b>{signal["reversal"]}%</b>
📈 Volatilidad: <b>{signal["volatility"]}/100</b>

{signal["recommendation"]}
"""


def register_signal(signal):
    d = load_data()
    signal_id = str(int(time.time() * 1000))

    item = {
        "id": signal_id,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "pair": signal["pair_name"],
        "pair_code": signal["pair_code"],
        "direction": signal["direction"],
        "expiry": signal["expiry"],
        "probability": signal["probability"],
        "reversal": signal["reversal"],
        "volatility": signal["volatility"],
        "result": "PENDING"
    }

    d["signals"] = d.get("signals", 0) + 1
    d.setdefault("history", []).append(item)
    save_data(d)
    return signal_id


def send_signal(signal):
    text = build_signal_text(signal)

    if signal["signal_type"] == "TRADE":
        signal_id = register_signal(signal)
        send_message(text, result_keyboard(signal_id))
    else:
        send_message(text, main_menu())


def update_result(signal_id, result):
    d = load_data()
    found = False

    for item in d.get("history", []):
        if item.get("id") == signal_id:
            if item.get("result") != "PENDING":
                save_data(d)
                return False

            item["result"] = result
            found = True

            if result == "WIN":
                d["wins"] = d.get("wins", 0) + 1
            else:
                d["losses"] = d.get("losses", 0) + 1
            break

    if found:
        save_data(d)

    return found


def handle_callback(callback):
    global data
    data = load_data()

    callback_id = callback["id"]
    chat_id = callback["message"]["chat"]["id"]
    message_id = callback["message"]["message_id"]
    action = callback["data"]

    answer_callback(callback_id)

    if action == "menu_forex":
        edit_message(chat_id, message_id, "📈 <b>Selecciona el par Forex mercado real:</b>", forex_menu())

    elif action == "back_main":
        edit_message(chat_id, message_id, "🖤💛 <b>El_Caballo_AI_Pro V8</b>\n\nSelecciona una opción:", main_menu())

    elif action.startswith("pair_"):
        pair_code = action.replace("pair_", "")
        if pair_code in PAIRS:
            data["selected_pair"] = pair_code
            data["selected_pair_name"] = PAIRS[pair_code]
            save_data(data)

            edit_message(
                chat_id,
                message_id,
                f"⏱ <b>Selecciona expiración para {PAIRS[pair_code]}:</b>",
                expiry_menu(pair_code)
            )

    elif action.startswith("expiry_"):
        parts = action.split("_")
        expiry = parts[-1]
        pair_code = "_".join(parts[1:-1])

        if pair_code in PAIRS:
            data["selected_pair"] = pair_code
            data["selected_pair_name"] = PAIRS[pair_code]
            data["selected_expiry"] = expiry
            data["pending_request"] = True
            data["requested_at"] = int(time.time())
            save_data(data)

            edit_message(
                chat_id,
                message_id,
                f"🔎 Analizando <b>{PAIRS[pair_code]}</b>...\n⏱ Expiración seleccionada: <b>{expiry} minuto(s)</b>\n\nEsperando lectura real de TradingView.",
                None
            )

            latest = data.get("latest_signals", {}).get(pair_code)
            if latest and int(time.time()) - int(latest.get("created_at", 0)) <= 120:
                data["pending_request"] = False
                save_data(data)
                send_signal(latest)

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
        send_message("🖤💛 <b>El_Caballo_AI_Pro V8</b>\n\nSelecciona una opción:", main_menu())


def telegram_loop():
    global last_update_id

    while True:
        try:
            params = {"timeout": 30}
            if last_update_id is not None:
                params["offset"] = last_update_id + 1

            r = requests.get(f"{API}/getUpdates", params=params, timeout=35)
            updates = r.json().get("result", [])

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
    return "El_Caballo_AI_Pro V8 activo"


@app.route("/webhook", methods=["POST"])
def webhook():
    global data

    try:
        content_type = request.headers.get("Content-Type", "")

        if "application/json" in content_type:
            payload = request.get_json(silent=True)
        else:
            payload = request.data.decode("utf-8")

        signal = parse_tradingview_payload(payload)

        if not signal:
            print("Webhook recibido pero no reconocido:", payload)
            return {"ok": False, "reason": "invalid signal"}, 200

        data = load_data()

        data.setdefault("latest_signals", {})
        data["latest_signals"][signal["pair_code"]] = signal
        save_data(data)

        selected_pair = data.get("selected_pair")
        pending = data.get("pending_request")

        if not selected_pair or not pending:
            print("Señal guardada pero no enviada: no fue solicitada desde Telegram")
            return {"ok": True, "stored": signal["pair_code"]}, 200

        if signal["pair_code"] != selected_pair:
            print(f"Señal guardada pero ignorada: {signal['pair_code']} != {selected_pair}")
            return {"ok": True, "ignored": "different pair"}, 200

        data["pending_request"] = False
        save_data(data)

        send_signal(signal)

        return {"ok": True, "sent": signal["pair_code"]}, 200

    except Exception as e:
        print("WEBHOOK ERROR:", e)
        return {"ok": False, "error": str(e)}, 500


def start_bot():
    print("El_Caballo_AI_Pro V8 receptor TradingView activo")
    threading.Thread(target=telegram_loop, daemon=True).start()


if __name__ == "__main__":
    start_bot()
    port = int(os.getenv("PORT", 8080))
    app.run(host="0.0.0.0", port=port)
