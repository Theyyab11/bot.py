# 📌 Institutional Gold Futures GC=F Signal Bot → Safe Scalping Alerts
# ✅ Works with GC=F on Yahoo, auto-checks for data, fully synchronous, deployable on Railway

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, time as dt_time, timezone
import time
import requests

# ---------------- CONFIG ----------------
SYMBOL = "GC=F"           # Gold Futures (reliable symbol)
TIMEFRAME = "1m"
TIMEFRAME_M15 = "15m"
ATR_PERIOD = 14
TP_ATR = 1.5
SL_ATR = 1
KILL_ZONES = [("09:00", "11:00"), ("13:00", "15:00")]

TELEGRAM_TOKEN = "8601674578:AAHycLEx-6M_r_JHFuS96oKuLTBJqefwKnk"
CHAT_ID = "992623579"
update_offset = None

# ---------------- HELPERS ----------------
def send_telegram(message, chat_id=CHAT_ID):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": chat_id, "text": message})
    except Exception as e:
        print(f"⚠️ Telegram send failed: {e}")

def get_data(symbol, period="2d", interval="1m"):
    try:
        df = yf.download(symbol, period=period, interval=interval, auto_adjust=True)
        if df.empty:
            print(f"⚠️ No data for {symbol}, skipping...")
            return None
        df.dropna(inplace=True)
        return df
    except Exception as e:
        print(f"⚠️ Error fetching {symbol}: {e}")
        return None

def atr(df, period=14):
    high_low = df['High'] - df['Low']
    high_close = abs(df['High'] - df['Close'].shift())
    low_close = abs(df['Low'] - df['Close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    return tr.rolling(period).mean()

def in_kill_zone():
    now = datetime.now(timezone.utc).time()
    for start, end in KILL_ZONES:
        start_t = dt_time(int(start.split(":")[0]), int(start.split(":")[1]))
        end_t = dt_time(int(end.split(":")[0]), int(end.split(":")[1]))
        if start_t <= now <= end_t:
            return True
    return False

# ---------------- STRATEGY DETECTION ----------------
def detect_bos(df):
    if len(df) < 3:
        return None
    last_close = df['Close'].iloc[-1]
    prev_high = df['High'].iloc[-3:-1].max()
    prev_low = df['Low'].iloc[-3:-1].min()
    if pd.isna(last_close) or pd.isna(prev_high) or pd.isna(prev_low):
        return None
    if last_close > prev_high:
        return "BOS_UP"
    elif last_close < prev_low:
        return "BOS_DOWN"
    return None

def detect_order_block(df):
    if len(df) < 1:
        return None
    last = df.iloc[-1]
    body = abs(last['Close'] - last['Open'])
    candle_range = last['High'] - last['Low']
    if candle_range == 0:
        return None
    if body / candle_range > 0.7:
        return "BUY_OB" if last['Close'] > last['Open'] else "SELL_OB"
    return None

def calculate_sl_tp(price, atr_value, direction):
    if direction == "BUY":
        sl = price - SL_ATR * atr_value
        tp = price + TP_ATR * atr_value
    else:
        sl = price + SL_ATR * atr_value
        tp = price - TP_ATR * atr_value
    return sl, tp

# ---------------- SIGNAL GENERATOR ----------------
def generate_signal():
    if not in_kill_zone():
        print("⏱️ Outside Kill Zones.")
        return

    df_m1 = get_data(SYMBOL, period="1d", interval="1m")
    df_m15 = get_data(SYMBOL, period="5d", interval="15m")

    if df_m1 is None or df_m15 is None:
        print("❌ Skipping signal: No data available.")
        return

    try:
        atr_m1 = atr(df_m1, ATR_PERIOD).iloc[-1]
    except Exception:
        print("⚠️ ATR calculation failed: insufficient data.")
        return

    bos_signal = detect_bos(df_m1)
    ob_signal = detect_order_block(df_m1)
    trend_m15 = "BUY" if df_m15['Close'].iloc[-1] > df_m15['Close'].iloc[-3] else "SELL"

    direction = None
    risk_percent = 50

    if bos_signal and ob_signal:
        if bos_signal == "BOS_UP" and ob_signal == "BUY_OB" and trend_m15 == "BUY":
            direction = "BUY"
            risk_percent = 85
        elif bos_signal == "BOS_DOWN" and ob_signal == "SELL_OB" and trend_m15 == "SELL":
            direction = "SELL"
            risk_percent = 85
        else:
            direction = "BUY" if trend_m15 == "BUY" else "SELL"
            risk_percent = 40

    if direction:
        send_telegram("⚡ Be ready! Potential Gold signal detected. Monitoring M1...")
        time.sleep(10)
        price = df_m1['Close'].iloc[-1]
        sl, tp = calculate_sl_tp(price, atr_m1, direction)
        message = (
            f"💰 Gold Futures Signal 💰\n"
            f"Direction: {direction}\n"
            f"Entry: {price:.2f}\n"
            f"SL: {sl:.2f} | TP: {tp:.2f}\n"
            f"Risk: {risk_percent}% {'✅ Safe' if risk_percent>=70 else '⚠️ Risky'}\n"
            f"Kill Zone: Active 🔥"
        )
        send_telegram(message)
        print("✅ Signal sent!")
    else:
        print("❌ No valid signal now.")

# ---------------- TEST SIGNAL ----------------
def generate_test_signal(chat_id):
    message = (
        "💰 Gold Signal (TEST) 💰\n"
        "Direction: BUY\n"
        "Entry: 1965.50\n"
        "SL: 1960.50 | TP: 1975.50\n"
        "Risk: 80% ✅ Safe\n"
        "Kill Zone: Active 🔥\n"
        "This is a test example signal"
    )
    send_telegram(message, chat_id)
    print("✅ Test signal sent!")

# ---------------- TELEGRAM COMMAND CHECK ----------------
def check_for_commands():
    global update_offset
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?timeout=10"
    if update_offset:
        url += f"&offset={update_offset}"
    try:
        response = requests.get(url).json()
        for update in response.get("result", []):
            update_offset = update["update_id"] + 1
            if "message" in update:
                chat_id = update["message"]["chat"]["id"]
                text = update["message"].get("text", "")
                if text.lower() == "/test":
                    generate_test_signal(chat_id)
    except Exception as e:
        print(f"⚠️ Telegram command check failed: {e}")

# ---------------- RUN ----------------
if __name__ == "__main__":
    print("📡 Gold Smart Risk Signal Bot Running...")
    while True:
        try:
            generate_signal()
            check_for_commands()
        except Exception as e:
            print("⚠️ Runtime error:", e)
        time.sleep(60)  # 1-minute loop
