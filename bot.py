# 🚀 XAUUSD ELITE SNIPER BOT (TWELVEDATA LIVE MARKET)

import requests
import pandas as pd
import time
import threading
from datetime import datetime
import pytz

# ---------------- CONFIG ----------------
SYMBOL = "XAU/USD"   # Gold
API_KEY = "ab9ad3eac834482c84366b4e57ffefa7"  # Twelve Data API key
TELEGRAM_TOKEN = "8601674578:AAHycLEx-6M_r_JHFuS96oKuLTBJqefwKnk"
CHAT_ID = "992623579"

ATR_PERIOD = 14
EMA_FAST = 20
EMA_SLOW = 50
MIN_CONFIDENCE = 90

last_signal = None
last_sl_tp = None
update_offset = None

# ---------------- TELEGRAM ----------------
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except Exception as e:
        print("Telegram error:", e)

# ---------------- SESSION ----------------
def is_killzone():
    dubai = pytz.timezone("Asia/Dubai")
    hour = datetime.now(dubai).hour
    return (11 <= hour <= 14) or (16 <= hour <= 19)

# ---------------- DATA ----------------
def fetch_data():
    try:
        url = f"https://api.twelvedata.com/time_series?symbol={SYMBOL}&interval=1min&outputsize=100&apikey={API_KEY}"
        res = requests.get(url).json()
        if "values" not in res:
            print("Market data unavailable or API limit reached:", res)
            return None
        df = pd.DataFrame(res["values"])
        df = df[::-1]  # oldest to newest
        df["open"] = df["open"].astype(float)
        df["high"] = df["high"].astype(float)
        df["low"] = df["low"].astype(float)
        df["close"] = df["close"].astype(float)
        return df
    except Exception as e:
        print("Fetch error:", e)
        return None

# ---------------- INDICATORS ----------------
def atr(df):
    tr = pd.concat([
        df['high'] - df['low'],
        abs(df['high'] - df['close'].shift()),
        abs(df['low'] - df['close'].shift())
    ], axis=1).max(axis=1)
    return tr.rolling(ATR_PERIOD).mean()

def ema(df, period):
    return df['close'].ewm(span=period).mean()

def momentum(df):
    return abs(df['close'].iloc[-1] - df['close'].iloc[-5])

# ---------------- SIGNAL ENGINE ----------------
def generate_signal():
    global last_signal, last_sl_tp

    df = fetch_data()
    if df is None or df.empty:
        send_telegram("⚠️ Market data unavailable for XAUUSD")
        return

    atr_val = atr(df).iloc[-1]
    if pd.isna(atr_val) or atr_val == 0:
        return

    ema_fast = ema(df, EMA_FAST).iloc[-1]
    ema_slow = ema(df, EMA_SLOW).iloc[-1]
    price = df['close'].iloc[-1]
    mom = momentum(df)

    # Trend filter: EMA fast > EMA slow = BUY, EMA fast < EMA slow = SELL
    direction = "BUY" if ema_fast > ema_slow else "SELL"

    # Confidence calculation
    confidence = 70
    if mom > 0.5 * atr_val: confidence += 10
    if mom > 0.8 * atr_val: confidence += 10
    if (direction=="BUY" and price>ema_slow) or (direction=="SELL" and price<ema_slow): confidence += 10

    if confidence < MIN_CONFIDENCE:
        return

    # 🚨 BE READY ALERT
    if last_signal != direction:
        send_telegram("⚠️ ELITE SNIPER ALERT - GOLD SETUP FORMING... Get ready!")

    # Dynamic SL/TP based on ATR
    if direction == "BUY":
        sl = price - 0.5 * atr_val
        tp = price + 1.5 * atr_val
    else:
        sl = price + 0.5 * atr_val
        tp = price - 1.5 * atr_val

    entry_low = price - 0.1 * atr_val
    entry_high = price + 0.1 * atr_val

    # SEND SIGNAL
    msg = (
        f"🚀 ELITE GOLD SNIPER SIGNAL\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📊 XAUUSD (1M)\n"
        f"📍 {direction}\n"
        f"🎯 Entry: {entry_low:.2f} - {entry_high:.2f}\n"
        f"🛑 SL: {sl:.2f}\n"
        f"💰 TP: {tp:.2f}\n"
        f"⚡ Confidence: {confidence}%\n"
        f"━━━━━━━━━━━━━━━"
    )

    send_telegram(msg)
    last_signal = direction
    last_sl_tp = {"sl": sl, "tp": tp}

# ---------------- TELEGRAM COMMANDS ----------------
def check_commands():
    global update_offset
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        if update_offset: url += f"?offset={update_offset}"
        res = requests.get(url, timeout=5).json()
        for upd in res.get("result", []):
            if "message" in upd:
                text = upd["message"].get("text", "").lower()
                if text == "/test":
                    send_telegram("🔥 ELITE GOLD SNIPER BOT ACTIVE")
                elif text == "/signal":
                    generate_signal()
                elif text == "/price":
                    df = fetch_data()
                    if df is not None:
                        send_telegram(f"💰 XAUUSD Price: {df['close'].iloc[-1]:.2f}")
                    else:
                        send_telegram("⚠️ Market data unavailable")
            update_offset = upd["update_id"] + 1
    except Exception as e:
        print("Command error:", e)

# ---------------- LOOP ----------------
def run_bot():
    while True:
        if is_killzone():
            generate_signal()
        time.sleep(60)

def run_commands():
    while True:
        check_commands()
        time.sleep(2)

# ---------------- START ----------------
if __name__ == "__main__":
    print("🚀 ELITE GOLD SNIPER BOT RUNNING...")
    threading.Thread(target=run_bot, daemon=True).start()
    threading.Thread(target=run_commands, daemon=True).start()
    while True: time.sleep(1)
