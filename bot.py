# 🚀 EXNESS-LIKE SNIPER BOT (XAUUSD + BTCUSD)

import requests
import pandas as pd
import time
import threading
from datetime import datetime

# ---------------- CONFIG ----------------
SYMBOLS = {
    "XAUUSD": "XAUUSD",
    "BTCUSD": "BTCUSD"
}

ATR_PERIOD = 14
MIN_CONFIDENCE = 70
COOLDOWN = 300  # 5 min

TELEGRAM_TOKEN = "8601674578:AAHycLEx-6M_r_JHFuS96oKuLTBJqefwKnk"
CHAT_ID = "992623579"

last_signal_time = {symbol: 0 for symbol in SYMBOLS}

# ---------------- HELPERS ----------------
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except Exception as e:
        print("Telegram error:", e)

def fetch_tradingview(symbol, interval="1"):
    """
    Fetch live price bars from TradingView public JSON.
    Interval in minutes: "1", "5", "15", etc.
    Returns pandas DataFrame with Open, High, Low, Close
    """
    try:
        url = f"https://tvc4.forexpros.com/68b9f27a1bb11e1f1aXXXX/1/{symbol}/history?resolution={interval}&from={int(time.time())-3600}&to={int(time.time())}"
        # Note: Replace with a valid TradingView endpoint or use a free API like TwelveData.
        # For now, using a placeholder
        res = requests.get(url, timeout=5)
        data = res.json()
        df = pd.DataFrame({
            "Open": data["o"],
            "High": data["h"],
            "Low": data["l"],
            "Close": data["c"]
        })
        return df
    except Exception as e:
        print(f"Fetch error ({symbol}):", e)
        return None

def atr(df):
    tr = pd.concat([
        df['High'] - df['Low'],
        abs(df['High'] - df['Close'].shift()),
        abs(df['Low'] - df['Close'].shift())
    ], axis=1).max(axis=1)
    return tr.rolling(ATR_PERIOD).mean()

def detect_bos(df):
    last = df['Close'].iloc[-1]
    high = df['High'].iloc[-3:-1].max()
    low = df['Low'].iloc[-3:-1].min()
    if last > high: return "BUY"
    elif last < low: return "SELL"
    return None

def detect_ob(df):
    last = df.iloc[-1]
    body = abs(last['Close'] - last['Open'])
    rng = last['High'] - last['Low']
    if rng == 0: return None
    if body / rng > 0.6:
        return "BUY" if last['Close'] > last['Open'] else "SELL"
    return None

def momentum_strength(df):
    return abs(df['Close'].iloc[-1] - df['Close'].iloc[-5])

def calculate_confidence(bos, ob, trend, momentum, atr_val):
    score = 0
    if bos: score += 25
    if ob: score += 25
    if bos == ob: score += 20
    if trend == bos: score += 15
    if momentum > 0.8 * atr_val: score += 15
    return min(score, 100)

def calculate_sl_tp(price, atr_val, direction):
    if direction == "BUY":
        return price - atr_val, price + 1.5*atr_val
    else:
        return price + atr_val, price - 1.5*atr_val

# ---------------- SIGNAL ----------------
def generate_signal():
    signal_sent = False
    for symbol in SYMBOLS:
        if time.time() - last_signal_time[symbol] < COOLDOWN:
            continue
        df = fetch_tradingview(symbol)
        if df is None or len(df) < ATR_PERIOD:
            continue
        atr_val = atr(df).iloc[-1]
        bos = detect_bos(df)
        ob = detect_ob(df)
        trend = "BUY" if df['Close'].iloc[-1] > df['Close'].iloc[-3] else "SELL"
        momentum = momentum_strength(df)
        confidence = calculate_confidence(bos, ob, trend, momentum, atr_val)
        if confidence >= MIN_CONFIDENCE:
            direction = bos if bos else trend
            price = df['Close'].iloc[-1]
            sl, tp = calculate_sl_tp(price, atr_val, direction)
            msg = f"🎯 SNIPER SIGNAL 🎯\nSymbol: {symbol}\nDirection: {direction}\nEntry: {price}\nSL: {sl}\nTP: {tp}\nConfidence: {confidence}%"
            send_telegram(msg)
            last_signal_time[symbol] = time.time()
            signal_sent = True
    if not signal_sent:
        send_telegram("⏳ I am currently sniping...")

# ---------------- THREADS ----------------
def run_signals():
    while True:
        generate_signal()
        time.sleep(300)  # 5 min

def run_commands():
    while True:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
            res = requests.get(url, timeout=5).json()
            for upd in res.get("result", []):
                if "message" in upd:
                    text = upd["message"].get("text", "").lower()
                    if text == "/test":
                        send_telegram("✅ FAST PRO SNIPER BOT ACTIVE 🔥")
        except:
            pass
        time.sleep(2)

# ---------------- RUN ----------------
if __name__ == "__main__":
    threading.Thread(target=run_signals, daemon=True).start()
    threading.Thread(target=run_commands, daemon=True).start()
    while True:
        time.sleep(1)
