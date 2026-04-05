# 🚀 PRO Multi-Asset AI Signal Bot (Gold + BTC + Oil)

import yfinance as yf
import pandas as pd
from datetime import datetime, timezone
import time
import threading
import requests

# ---------------- CONFIG ----------------
SYMBOLS = {
    "GOLD": "GC=F",
    "BTC": "BTC-USD",
    "OIL": "CL=F"
}

ATR_PERIOD = 14
MIN_CONFIDENCE = 75
SIGNAL_COOLDOWN = 300  # seconds between signals

TELEGRAM_TOKEN = "YOUR_TOKEN"
CHAT_ID = "YOUR_CHAT_ID"

last_signal_time = 0
update_offset = None

# ---------------- HELPERS ----------------
def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": message})
    except:
        pass

def is_weekend():
    return datetime.utcnow().weekday() >= 5

def get_active_symbols():
    if is_weekend():
        return ["BTC"]  # 🔥 always active
    return ["GOLD", "OIL"]  # weekdays

def get_data(symbol, period="2d", interval="1m"):
    try:
        df = yf.download(symbol, period=period, interval=interval, auto_adjust=True)
        df.dropna(inplace=True)
        return df
    except:
        return None

def atr(df):
    tr = pd.concat([
        df['High'] - df['Low'],
        abs(df['High'] - df['Close'].shift()),
        abs(df['Low'] - df['Close'].shift())
    ], axis=1).max(axis=1)
    return tr.rolling(ATR_PERIOD).mean()

# ---------------- SMART LOGIC ----------------
def detect_bos(df):
    last = df['Close'].iloc[-1]
    high = df['High'].iloc[-3:-1].max()
    low = df['Low'].iloc[-3:-1].min()

    if last > high:
        return "BUY"
    elif last < low:
        return "SELL"
    return None

def detect_ob(df):
    last = df.iloc[-1]
    body = abs(last['Close'] - last['Open'])
    rng = last['High'] - last['Low']

    if rng == 0:
        return None

    if body / rng > 0.7:
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
    if momentum > atr_val: score += 15

    return min(score, 100)

def calculate_sl_tp(price, atr_val, direction):
    if direction == "BUY":
        return price - atr_val, price + (1.5 * atr_val)
    else:
        return price + atr_val, price - (1.5 * atr_val)

# ---------------- SIGNAL ENGINE ----------------
def generate_signal():
    global last_signal_time

    if time.time() - last_signal_time < SIGNAL_COOLDOWN:
        return

    for asset in get_active_symbols():
        symbol = SYMBOLS[asset]

        df_m1 = get_data(symbol, "1d", "1m")
        df_m15 = get_data(symbol, "5d", "15m")

        if df_m1 is None or df_m15 is None:
            continue

        atr_val = atr(df_m1).iloc[-1]
        if pd.isna(atr_val):
            continue

        bos = detect_bos(df_m1)
        ob = detect_ob(df_m1)
        trend = "BUY" if df_m15['Close'].iloc[-1] > df_m15['Close'].iloc[-3] else "SELL"
        momentum = momentum_strength(df_m1)

        confidence = calculate_confidence(bos, ob, trend, momentum, atr_val)

        if confidence < MIN_CONFIDENCE:
            continue

        direction = bos if bos else trend

        asset_name = {
            "GOLD": "🥇 Gold",
            "BTC": "🪙 BTC (Weekend)",
            "OIL": "🛢️ Oil"
        }[asset]

        send_telegram(f"⚡ Be ready! {asset_name} strong signal forming...")

        time.sleep(2)

        price = df_m1['Close'].iloc[-1]
        sl, tp = calculate_sl_tp(price, atr_val, direction)

        msg = (
            f"🚀 {asset_name} SIGNAL 🚀\n"
            f"Direction: {direction}\n"
            f"Entry: {price:.2f}\n"
            f"SL: {sl:.2f} | TP: {tp:.2f}\n"
            f"Confidence: {confidence}% 🔥"
        )

        send_telegram(msg)

        last_signal_time = time.time()
        break

# ---------------- COMMAND ----------------
def check_commands():
    global update_offset

    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
    if update_offset:
        url += f"?offset={update_offset}"

    res = requests.get(url).json()

    for upd in res.get("result", []):
        update_offset = upd["update_id"] + 1

        if "message" in upd:
            chat_id = upd["message"]["chat"]["id"]
            text = upd["message"].get("text", "")

            if text.lower() == "/test":
                send_telegram("✅ PRO BOT ACTIVE (AI + Multi-Asset)")

# ---------------- THREADS ----------------
def run_signals():
    while True:
        try:
            generate_signal()
        except Exception as e:
            print("Signal Error:", e)
        time.sleep(30)

def run_commands():
    while True:
        check_commands()
        time.sleep(2)

# ---------------- RUN ----------------
if __name__ == "__main__":
    print("🚀 PRO AI Signal Bot Running...")

    threading.Thread(target=run_signals, daemon=True).start()
    threading.Thread(target=run_commands, daemon=True).start()

    while True:
        time.sleep(1)
