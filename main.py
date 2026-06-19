import os, time, json, threading, requests, uuid
from pathlib import Path
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
            d = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            for k, v in DEFAULT_DATA.items():
                d.setdefault(k, v)
            return d
        except:
            return DEFAULT_DATA.copy()
    return DEFAULT_DATA.copy()

def save_data(d):
    DATA_FILE.write_text(json.dumps(d, indent=2, ensure_ascii=False), encoding="utf-8")

def new_session():
    d = load_data()
    d["session"] = uuid.uuid4().hex[:8]
    save_data(d)
    return d["session"]

def send_message(text, keyboard=None):
    payload = {"chat_id": CHAT_ID, "text": text, "parse_mode": "HTML"}
    if keyboard:
        payload["reply_markup"] = keyboard
    try:
        r = requests.post(f"{API}/sendMessage", json=payload, timeout=15)
        return r.json().get("result", {}).get("message_id")
    except Exception as e:
        print("SEND ERROR:", e)
        return None

def edit_message(chat_id, message_id, text, keyboard=None):
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text, "parse_mode": "HTML"}
    if keyboard:
        payload["reply_markup"] = keyboard
    try:
        requests.post(f"{API}/editMessageText", json=payload, timeout=15)
    except Exception as e:
        print("EDIT ERROR:", e)

def delete_message(chat_id, message_id):
    try:
        requests.post(f"{API}/deleteMessage", json={"chat_id": chat_id, "message_id": message_id}, timeout=10)
    except:
        pass

def clean_chat():
    d = load_data()
    for mid in d.get("messages_to_delete", []):
        delete_message(CHAT_ID, mid)
    d["messages_to_delete"] = []
    save_data(d)

def remember_message(mid):
    if not mid:
        return
    d = load_data()
    d.setdefault("messages_to_delete", []).append(mid)
    save_data(d)

def answer_callback(cid):
    try:
        requests.post(f"{API}/answerCallbackQuery", json={"callback_query_id": cid}, timeout=10)
    except:
        pass

def main_menu(session):
    return {"inline_keyboard": [
        [{"text": "📈 Forex mercado real", "callback_data": f"menu_forex:{session}"}],
        [{"text": "📊 Estadísticas", "callback_data": f"stats:{session}"}],
        [{"text": "🧹 Limpiar chat", "callback_data": f"reset:{session}"}]
    ]}

def forex_menu(session):
    items = list(PAIRS.items())
    rows = []
    for i in range(0, len(items), 2):
        row = []
        for code, info in items[i:i+2]:
            row.append({"text": info["name"], "callback_data": f"pair:{code}:{session}"})
        rows.append(row)
    rows.append([{"text": "⬅️ Volver", "callback_data": f"back:{session}"}])
    return {"inline_keyboard": rows}

def expiry_menu(pair, session):
    return {"inline_keyboard": [
        [{"text": "1 minuto", "callback_data": f"expiry:{pair}:1:{session}"}],
        [{"text": "3 minutos", "callback_data": f"expiry:{pair}:3:{session}"}],
        [{"text": "5 minutos", "callback_data": f"expiry:{pair}:5:{session}"}],
        [{"text": "⬅️ Volver", "callback_data": f"menu_forex:{session}"}]
    ]}

def result_keyboard(signal_id, session):
    return {"inline_keyboard": [
        [
            {"text": "✅ WIN", "callback_data": f"win:{signal_id}:{session}"},
            {"text": "❌ LOSS", "callback_data": f"loss:{signal_id}:{session}"}
        ],
        [{"text": "📊 Estadísticas", "callback_data": f"stats:{session}"}]
    ]}

def stats_text():
    d = load_data()
    wins = d.get("wins", 0)
    losses = d.get("losses", 0)
    closed = wins + losses
    rate = round((wins / closed) * 100, 2) if closed else 0
    pair = PAIRS.get(d.get("selected_pair"), {}).get("name", "Ninguno")
    expiry = d.get("selected_expiry") or "No seleccionada"
    return f"""📊 <b>Estadísticas El_Caballo_AI_Pro</b>

⭐ Señales totales: <b>{d.get("signals", 0)}</b>
✅ WIN: <b>{wins}</b>
❌ LOSS: <b>{losses}</b>
🎯 Win rate real: <b>{rate}%</b>

📌 Par activo:
<b>{pair}</b>

⏱ Expiración activa:
<b>{expiry} minuto(s)</b>
"""

def ema(values, length):
    if not values:
        return 0
    length = min(length, len(values))
    k = 2 / (length + 1)
    result = values[0]
    for v in values[1:]:
        result = v * k + result * (1 - k)
    return result

def rsi(closes, length=14):
    if len(closes) < length + 1:
        return 50
    gains, losses = [], []
    for i in range(1, len(closes)):
        diff = closes[i] - closes[i-1]
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
        trs.append(max(
            highs[i] - lows[i],
            abs(highs[i] - closes[i-1]),
            abs(lows[i] - closes[i-1])
        ))
    return sum(trs[-length:]) / length

def macd(closes):
    vals = []
    for i in range(35, len(closes)+1):
        part = closes[:i]
        vals.append(ema(part[-35:], 12) - ema(part[-35:], 26))
    line = vals[-1] if vals else 0
    signal = ema(vals[-9:], 9) if len(vals) >= 9 else line
    return line, signal

def fetch_candles(symbol):
    if not TWELVE_API_KEY:
        raise Exception("Falta TWELVE_API_KEY en Railway Variables")
    r = requests.get(
        "https://api.twelvedata.com/time_series",
        params={
            "symbol": symbol,
            "interval": "1min",
            "outputsize": 220,
            "apikey": TWELVE_API_KEY
        },
        timeout=20
    ).json()
    if "values" not in r:
        raise Exception(str(r))
    candles = list(reversed(r["values"]))
    return {
        "open": [float(x["open"]) for x in candles],
        "high": [float(x["high"]) for x in candles],
        "low": [float(x["low"]) for x in candles],
        "close": [float(x["close"]) for x in candles]
    }

def analyze_pair(pair_code, expiry):
    info = PAIRS[pair_code]
    c = fetch_candles(info["symbol"])
    o, h, l, close = c["open"], c["high"], c["low"], c["close"]

    last = close[-1]
    open_last = o[-1]

    ema9 = ema(close[-60:], 9)
    ema21 = ema(close[-60:], 21)
    ema50 = ema(close[-100:], 50)
    ema200 = ema(close[-220:], 200)

    rsi_v = rsi(close, 14)
    macd_l, macd_s = macd(close)
    atr_v = atr(h, l, close, 14)

    atr_list = [atr(h[:i], l[:i], close[:i], 14) for i in range(30, len(close))]
    atr_avg = sum(atr_list[-30:]) / len(atr_list[-30:]) if atr_list else atr_v
    volatility = round(max(1, min(100, (atr_v / atr_avg) * 60))) if atr_avg else 50

    support = min(l[-25:])
    resistance = max(h[-25:])
    candle_range = h[-1] - l[-1]
    body = abs(last - open_last)
    body_ratio = body / candle_range if candle_range else 0

    bull = last > open_last and body_ratio >= 0.45
    bear = last < open_last and body_ratio >= 0.45

    near_support = last <= support + atr_v * 0.8
    near_resistance = last >= resistance - atr_v * 0.8

    up_exhausted = close[-1] > close[-2] > close[-3] > close[-4]
    down_exhausted = close[-1] < close[-2] < close[-3] < close[-4]

    buy = 0
    sell = 0

    buy += 16 if ema9 > ema21 else 0
    sell += 16 if ema9 < ema21 else 0

    buy += 12 if ema50 > ema200 else 0
    sell += 12 if ema50 < ema200 else 0

    buy += 12 if last > ema50 else 0
    sell += 12 if last < ema50 else 0

    buy += 14 if 45 < rsi_v < 68 else 0
    sell += 14 if 32 < rsi_v < 55 else 0

    buy += 16 if macd_l > macd_s else 0
    sell += 16 if macd_l < macd_s else 0

    buy += 14 if bull else 0
    sell += 14 if bear else 0

    buy += 8 if near_support else 0
    sell += 8 if near_resistance else 0

    buy -= 12 if rsi_v > 75 else 0
    sell -= 12 if rsi_v < 25 else 0

    buy -= 10 if up_exhausted else 0
    sell -= 10 if down_exhausted else 0

    buy = max(1, min(95, buy))
    sell = max(1, min(95, sell))

    if buy > sell:
        direction = "BUY"
        strength = buy
        opposite = sell
    else:
        direction = "SELL"
        strength = sell
        opposite = buy

    diff = abs(buy - sell)
    reversal = round(max(5, min(60, (opposite / max(strength + opposite, 1)) * 100 + (10 if diff < 15 else 0))))

    if strength < 70 or diff < 25 or reversal > 42:
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
        "strength": round(strength),
        "reversal": reversal,
        "volatility": volatility,
        "buy": round(buy),
        "sell": round(sell),
        "recommendation": recommendation
    }

def signal_text(s):
    return f"""🖤💛 <b>El_Caballo_AI_Pro</b>

🔍 Análisis terminado para <b>{s["pair_name"]}</b>

{s["title"]}
📊 <b>{s["pair_name"]}</b>

⏱ Expiración: <b>{s["expiry"]} minuto(s)</b>
🎯 Fuerza de señal según mercado: <b>{s["strength"]}/100</b>
🔄 Riesgo de reversión: <b>{s["reversal"]}/100</b>
📈 Volatilidad: <b>{s["volatility"]}/100</b>

📊 Fuerza compra: <b>{s["buy"]}/100</b>
📊 Fuerza venta: <b>{s["sell"]}/100</b>

{s["recommendation"]}
"""

def register_signal(s):
    d = load_data()
    sid = str(int(time.time() * 1000))
    d["signals"] += 1
    d["history"].append({
        "id": sid,
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        "pair": s["pair_name"],
        "direction": s["direction"],
        "expiry": s["expiry"],
        "strength": s["strength"],
        "reversal": s["reversal"],
        "volatility": s["volatility"],
        "result": "PENDING"
    })
    save_data(d)
    return sid

def run_analysis(pair, expiry, session):
    try:
        time.sleep(10)
        s = analyze_pair(pair, expiry)
        clean_chat()
        if s["signal_type"] == "TRADE":
            sid = register_signal(s)
            mid = send_message(signal_text(s), result_keyboard(sid, session))
        else:
            mid = send_message(signal_text(s), main_menu(session))
        remember_message(mid)
    except Exception as e:
        clean_chat()
        mid = send_message(f"⚠️ Error analizando el mercado:\n<code>{str(e)}</code>", main_menu(session))
        remember_message(mid)

def update_result(sid, result):
    d = load_data()
    for item in d["history"]:
        if item["id"] == sid:
            if item["result"] != "PENDING":
                return False
            item["result"] = result
            if result == "WIN":
                d["wins"] += 1
            else:
                d["losses"] += 1
            save_data(d)
            return True
    return False

def valid_session(session):
    return session == load_data().get("session")

def handle_callback(cb):
    answer_callback(cb["id"])
    chat_id = cb["message"]["chat"]["id"]
    msg_id = cb["message"]["message_id"]
    action = cb["data"].split(":")
    d = load_data()

    cmd = action[0]
    session = action[-1] if len(action) > 1 else ""

    if cmd not in ["reset"] and not valid_session(session):
        edit_message(chat_id, msg_id, "⚠️ Este botón es viejo. Escribe /start para abrir el menú nuevo.")
        return

    remember_message(msg_id)

    if cmd == "reset":
        clean_chat()
        session = new_session()
        mid = send_message("🖤💛 <b>El_Caballo_AI_Pro</b>\n\nSelecciona una opción:", main_menu(session))
        remember_message(mid)

    elif cmd == "menu_forex":
        edit_message(chat_id, msg_id, "📈 <b>Selecciona el par Forex mercado real:</b>", forex_menu(session))

    elif cmd == "back":
        edit_message(chat_id, msg_id, "🖤💛 <b>El_Caballo_AI_Pro</b>\n\nSelecciona una opción:", main_menu(session))

    elif cmd == "pair":
        pair = action[1]
        d["selected_pair"] = pair
        save_data(d)
        edit_message(chat_id, msg_id, f"⏱ <b>Selecciona expiración para {PAIRS[pair]['name']}:</b>", expiry_menu(pair, session))

    elif cmd == "expiry":
        pair = action[1]
        expiry = action[2]
        d["selected_pair"] = pair
        d["selected_expiry"] = expiry
        save_data(d)
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
        sid = action[1]
        ok = update_result(sid, "WIN")
        msg = "✅ Resultado guardado como WIN." if ok else "⚠️ Esta señal ya fue marcada."
        edit_message(chat_id, msg_id, msg + "\n\n" + stats_text(), main_menu(session))

    elif cmd == "loss":
        sid = action[1]
        ok = update_result(sid, "LOSS")
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
    while True:
        try:
            params = {"timeout": 30}
            if last_update_id is not None:
                params["offset"] = last_update_id + 1
            r = requests.get(f"{API}/getUpdates", params=params, timeout=35)
            for u in r.json().get("result", []):
                last_update_id = u["update_id"]
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
