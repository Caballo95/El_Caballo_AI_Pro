import os
import time
import json
import requests
import pandas as pd
from pathlib import Path
from datetime import datetime

BOT_TOKEN = os.getenv("BOT_TOKEN")
CHAT_ID = os.getenv("CHAT_ID")
API = f"https://api.telegram.org/bot{BOT_TOKEN}"

LEARNING_FILE = "learning_data.json"
last_update_id = None

FOREX_PAIRS = {
    "EUR_USD": {"name": "EUR/USD", "symbol": "EURUSD=X"},
    "AUD_USD": {"name": "AUD/USD", "symbol": "AUDUSD=X"},
    "AUD_CAD": {"name": "AUD/CAD", "symbol": "AUDCAD=X"},
    "AUD_CHF": {"name": "AUD/CHF", "symbol": "AUDCHF=X"},
    "AUD_NZD": {"name": "AUD/NZD", "symbol": "AUDNZD=X"},
}


def default_learning_data():
    return {
        "total_signals": 0,
        "wins": 0,
        "losses": 0,
        "pairs": {},
        "strategies": {},
        "indicators": {},
        "expiries": {},
        "markets": {},
        "history": []
    }


def load_learning_data():
    if Path(LEARNING_FILE).exists():
        try:
            with open(LEARNING_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = default_learning_data()
    else:
        data = default_learning_data()

    base = default_learning_data()
    for key, value in base.items():
        if key not in data:
            data[key] = value

    return data


def save_learning_data(data):
    with open(LEARNING_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


learning_data = load_learning_data()


def send_message(text, keyboard=None):
    data = {
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML"
    }

    if keyboard:
        data["reply_markup"] = keyboard

    try:
        return requests.post(f"{API}/sendMessage", json=data, timeout=10).json()
    except Exception as e:
        print("SEND_ERROR:", e)
        return None


def edit_message(chat_id, message_id, text, keyboard=None):
    data = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text,
        "parse_mode": "HTML"
    }

    if keyboard:
        data["reply_markup"] = keyboard

    try:
        return requests.post(f"{API}/editMessageText", json=data, timeout=10).json()
    except Exception as e:
        print("EDIT_ERROR:", e)
        return None


def answer_callback(callback_id):
    try:
        requests.post(
            f"{API}/answerCallbackQuery",
            json={"callback_query_id": callback_id},
            timeout=10
        )
    except Exception as e:
        print("CALLBACK_ERROR:", e)


def main_menu():
    return {
        "inline_keyboard": [
            [{"text": "📈 Forex mercado real", "callback_data": "menu_forex"}],
            [{"text": "🌙 OTC", "callback_data": "menu_otc"}],
            [{"text": "📊 Estadísticas", "callback_data": "stats"}]
        ]
    }


def forex_menu():
    return {
        "inline_keyboard": [
            [{"text": "EUR/USD", "callback_data": "pair_EUR_USD"}],
            [{"text": "AUD/USD", "callback_data": "pair_AUD_USD"}],
            [{"text": "AUD/CAD", "callback_data": "pair_AUD_CAD"}],
            [{"text": "AUD/CHF", "callback_data": "pair_AUD_CHF"}],
            [{"text": "AUD/NZD", "callback_data": "pair_AUD_NZD"}],
            [{"text": "⬅️ Volver", "callback_data": "back_main"}]
        ]
    }


def expiry_menu(pair):
    return {
        "inline_keyboard": [
            [{"text": "1 minuto", "callback_data": f"expiry_{pair}_1"}],
            [{"text": "2 minutos", "callback_data": f"expiry_{pair}_2"}],
            [{"text": "3 minutos", "callback_data": f"expiry_{pair}_3"}],
            [{"text": "5 minutos", "callback_data": f"expiry_{pair}_5"}],
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


def pair_name(pair):
    return FOREX_PAIRS.get(pair, {}).get("name", pair.replace("_", "/"))


def get_forex_data(pair):
    info = FOREX_PAIRS.get(pair)
    if not info:
        return None

    symbol = info["symbol"]
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"range": "1d", "interval": "1m"}
    headers = {"User-Agent": "Mozilla/5.0"}

    try:
        r = requests.get(url, params=params, headers=headers, timeout=8)
        data = r.json()
        result = data["chart"]["result"][0]
        quote = result["indicators"]["quote"][0]

        df = pd.DataFrame({
            "open": quote["open"],
            "high": quote["high"],
            "low": quote["low"],
            "close": quote["close"],
            "volume": quote.get("volume", [])
        }).dropna()

        if len(df) < 60:
            return None

        return df

    except Exception as e:
        print("DATA_ERROR:", e)
        return None


def calculate_rsi(close, length=7):
    delta = close.diff()
    gain = delta.where(delta > 0, 0).rolling(length).mean()
    loss = -delta.where(delta < 0, 0).rolling(length).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))


def calculate_atr(df, length=14):
    high_low = df["high"] - df["low"]
    high_close = (df["high"] - df["close"].shift()).abs()
    low_close = (df["low"] - df["close"].shift()).abs()
    true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return true_range.rolling(length).mean()


def analyze_real_market(pair):
    df = get_forex_data(pair)

    if df is None or df.empty:
        return None

    df["ema9"] = df["close"].ewm(span=9, adjust=False).mean()
    df["ema21"] = df["close"].ewm(span=21, adjust=False).mean()
    df["ema50"] = df["close"].ewm(span=50, adjust=False).mean()
    df["rsi"] = calculate_rsi(df["close"], 7)

    ema12 = df["close"].ewm(span=12, adjust=False).mean()
    ema26 = df["close"].ewm(span=26, adjust=False).mean()
    df["macd"] = ema12 - ema26
    df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
    df["atr"] = calculate_atr(df, 14)

    last = df.iloc[-1]
    prev = df.iloc[-2]

    candle_range = last["high"] - last["low"]
    body = abs(last["close"] - last["open"])
    body_ratio = body / candle_range if candle_range > 0 else 0

    atr_now = last["atr"]
    atr_avg = df["atr"].tail(30).mean()
    volatility = int(min(100, max(1, round((atr_now / atr_avg) * 60)))) if atr_avg and atr_avg > 0 else 50

    support = df["low"].tail(25).min()
    resistance = df["high"].tail(25).max()

    near_support = last["close"] <= support + (atr_now * 0.8) if atr_now > 0 else False
    near_resistance = last["close"] >= resistance - (atr_now * 0.8) if atr_now > 0 else False

    buy_score = 0
    sell_score = 0

    if last["ema9"] > last["ema21"] > last["ema50"]:
        buy_score += 30

    if last["ema9"] < last["ema21"] < last["ema50"]:
        sell_score += 30

    if 52 <= last["rsi"] <= 72:
        buy_score += 20

    if 28 <= last["rsi"] <= 48:
        sell_score += 20

    if last["macd"] > last["macd_signal"]:
        buy_score += 20

    if last["macd"] < last["macd_signal"]:
        sell_score += 20

    if last["close"] > prev["close"] and body_ratio >= 0.35:
        buy_score += 15

    if last["close"] < prev["close"] and body_ratio >= 0.35:
        sell_score += 15

    if near_support:
        buy_score += 10

    if near_resistance:
        sell_score += 10

    if volatility >= 35:
        buy_score += 5
        sell_score += 5

    if buy_score >= 75 and buy_score > sell_score:
        confidence = min(94, buy_score)
        return {
            "direction": "BUY",
            "confidence": confidence,
            "reversal": 100 - confidence,
            "volatility": volatility,
            "strategy": "Forex Real V1",
            "indicators": {
                "ema9": round(float(last["ema9"]), 6),
                "ema21": round(float(last["ema21"]), 6),
                "ema50": round(float(last["ema50"]), 6),
                "rsi7": round(float(last["rsi"]), 2),
                "macd": round(float(last["macd"]), 6),
                "macd_signal": round(float(last["macd_signal"]), 6),
                "atr": round(float(atr_now), 6),
                "body_ratio": round(float(body_ratio), 2),
                "support": round(float(support), 6),
                "resistance": round(float(resistance), 6)
            }
        }

    if sell_score >= 75 and sell_score > buy_score:
        confidence = min(94, sell_score)
        return {
            "direction": "SELL",
            "confidence": confidence,
            "reversal": 100 - confidence,
            "volatility": volatility,
            "strategy": "Forex Real V1",
            "indicators": {
                "ema9": round(float(last["ema9"]), 6),
                "ema21": round(float(last["ema21"]), 6),
                "ema50": round(float(last["ema50"]), 6),
                "rsi7": round(float(last["rsi"]), 2),
                "macd": round(float(last["macd"]), 6),
                "macd_signal": round(float(last["macd_signal"]), 6),
                "atr": round(float(atr_now), 6),
                "body_ratio": round(float(body_ratio), 2),
                "support": round(float(support), 6),
                "resistance": round(float(resistance), 6)
            }
        }

    return None


def register_signal(pair, analysis, expiry):
    signal_id = str(int(time.time() * 1000))

    signal_data = {
        "id": signal_id,
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "market": "FOREX_REAL",
        "pair": pair_name(pair),
        "pair_code": pair,
        "direction": analysis["direction"],
        "expiry": str(expiry),
        "confidence": analysis["confidence"],
        "reversal": analysis["reversal"],
        "volatility": analysis["volatility"],
        "result": "PENDING",
        "strategy": analysis["strategy"],
        "indicators": analysis["indicators"]
    }

    learning_data["total_signals"] = learning_data.get("total_signals", 0) + 1
    learning_data["history"].append(signal_data)
    save_learning_data(learning_data)

    return signal_id


def generate_signal(pair, expiry):
    analysis = analyze_real_market(pair)

    if analysis is None:
        send_message(
            f"⚠️ <b>{pair_name(pair)}</b>\n\nNo hay entrada fuerte ahora.\nEl bot espera una mejor oportunidad.",
            main_menu()
        )
        return

    direction = analysis["direction"]
    confidence = analysis["confidence"]
    reversal = analysis["reversal"]
    volatility = analysis["volatility"]

    signal_text = "🟢 COMPRA ARRIBA" if direction == "BUY" else "🔴 VENTA ABAJO"

    signal_id = register_signal(pair, analysis, expiry)

    text = f"""🖤💛 <b>El_Caballo_AI_Pro</b>

{signal_text}
📊 <b>{pair_name(pair)}</b>

⏱ Expiración: <b>{expiry} minutos</b>
🎯 Confianza: <b>{confidence}%</b>
🔄 Probabilidad de reversión: <b>{reversal}%</b>
📈 Volatilidad: <b>{volatility}/100</b>

🕐 Hora de entrada: <b>AHORA</b>"""

    send_message(text, result_keyboard(signal_id))


def ensure_stat_group(group_name, key):
    if group_name not in learning_data:
        learning_data[group_name] = {}

    if key not in learning_data[group_name]:
        learning_data[group_name][key] = {"wins": 0, "losses": 0}


def add_result_to_group(group_name, key, result):
    ensure_stat_group(group_name, key)

    if result == "WIN":
        learning_data[group_name][key]["wins"] += 1
    elif result == "LOSS":
        learning_data[group_name][key]["losses"] += 1


def update_result(signal_id, result):
    found = False

    for item in learning_data.get("history", []):
        if item.get("id") == signal_id and item.get("result") == "PENDING":
            item["result"] = result
            found = True

            if result == "WIN":
                learning_data["wins"] = learning_data.get("wins", 0) + 1
            elif result == "LOSS":
                learning_data["losses"] = learning_data.get("losses", 0) + 1

            add_result_to_group("pairs", item.get("pair", "UNKNOWN"), result)
            add_result_to_group("strategies", item.get("strategy", "UNKNOWN"), result)
            add_result_to_group("expiries", str(item.get("expiry", "0")), result)
            add_result_to_group("markets", item.get("market", "UNKNOWN"), result)

            for indicator_name in item.get("indicators", {}).keys():
                add_result_to_group("indicators", indicator_name, result)

            break

    save_learning_data(learning_data)
    return found


def group_stats_text(title, group):
    text = f"\n<b>{title}</b>\n"
    data = learning_data.get(group, {})

    if not data:
        text += "Sin datos todavía.\n"
        return text

    for name, values in list(data.items())[:10]:
        wins = values.get("wins", 0)
        losses = values.get("losses", 0)
        total = wins + losses
        rate = round((wins / total) * 100, 2) if total > 0 else 0
        text += f"{name}: {wins}W / {losses}L — {rate}%\n"

    return text


def stats_text():
    total = learning_data.get("total_signals", 0)
    wins = learning_data.get("wins", 0)
    losses = learning_data.get("losses", 0)
    closed = wins + losses
    win_rate = round((wins / closed) * 100, 2) if closed > 0 else 0

    text = f"""📊 <b>Estadísticas El_Caballo_AI_Pro</b>

⭐ Señales totales: <b>{total}</b>
✅ WIN: <b>{wins}</b>
❌ LOSS: <b>{losses}</b>
🎯 Win rate: <b>{win_rate}%</b>
"""

    text += group_stats_text("📌 Pares", "pairs")
    text += group_stats_text("🧠 Estrategias", "strategies")
    text += group_stats_text("⏱ Expiraciones", "expiries")

    return text


def handle_callback(callback):
    data = callback["data"]
    callback_id = callback["id"]
    chat_id = callback["message"]["chat"]["id"]
    message_id = callback["message"]["message_id"]

    answer_callback(callback_id)

    if data == "menu_forex":
        edit_message(chat_id, message_id, "📈 <b>Selecciona un par Forex mercado real:</b>", forex_menu())

    elif data == "menu_otc":
        edit_message(
            chat_id,
            message_id,
            "🌙 <b>OTC todavía no está conectado a datos reales.</b>\n\nPrimero trabajaremos Forex real.",
            main_menu()
        )

    elif data == "stats":
        edit_message(chat_id, message_id, stats_text(), main_menu())

    elif data == "back_main":
        edit_message(chat_id, message_id, "🖤💛 <b>El_Caballo_AI_Pro</b>\n\nSelecciona una opción:", main_menu())

    elif data.startswith("pair_"):
        pair = data.replace("pair_", "")
        edit_message(chat_id, message_id, f"⏱ <b>Selecciona expiración para {pair_name(pair)}:</b>", expiry_menu(pair))

    elif data.startswith("expiry_"):
        parts = data.split("_")
        expiry = parts[-1]
        pair = "_".join(parts[1:-1])

        edit_message(chat_id, message_id, f"🔎 Analizando <b>{pair_name(pair)}</b>...", main_menu())
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

    params = {"timeout": 30}

    if last_update_id is not None:
        params["offset"] = last_update_id + 1

    try:
        r = requests.get(f"{API}/getUpdates", params=params, timeout=35)
        updates = r.json().get("result", [])

        for update in updates:
            last_update_id = update["update_id"]

            if "callback_query" in update:
                handle_callback(update["callback_query"])

            elif "message" in update:
                handle_message(update["message"])

    except Exception as e:
        print("GET_UPDATES_ERROR:", e)
        time.sleep(5)


def main():
    print("El_Caballo_AI_Pro Forex Real activo")

    while True:
        get_updates()
        time.sleep(2)


if __name__ == "__main__":
    main()
