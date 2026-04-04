# 📌 Institutional XAUUSD Signal Bot → Sends BUY/SELL signals to Telegram
# ✅ Features: M1 + M5 trend filter, BOS, Order Blocks, ATR-based SL/TP, Kill Zones
# 🚀 Sends daily signals to your Telegram bot

import yfinance as yf
import pandas as pd
import numpy as np
import datetime
import time
import requests

# ---------------- CONFIG ----------------
SYMBOL = "XAUUSD=X"
TIMEFRAME = "1m"  # Primary chart
TIMEFRAME_M5 = "5m"  # Secondary chart
ATR_PERIOD = 14
TP_ATR = 1.5
SL_ATR = 1
KILL_ZONES = [("09:00", "11:00"), ("13:00", "15:00")]  # London + NY in UTC

TELEGRAM_TOKEN = "8601674578:AAHycLEx-6M_r_JHFuS96oKuLTBJqefwKnk"
CHAT_ID = "992623579"

# ---------------- HELPERS ----------------
def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    payload = {"chat_id": CHAT_ID, "text": message}
    requests.post(url, data=payload)

def get_data(symbol, period="2d", interval="1m"):
    df = yf.download(symbol, period=period, interval=interval, auto_adjust=True)
    df.dropna(inplace=True)
    return df

def atr(df, period=14):
    high_low = df['High'] - df['Low']
    high_close = np.abs(df['High'] - df['Close'].shift())
    low_close = np.abs(df['Low'] - df['Close'].shift())
    tr = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
    atr = tr.rolling(period).mean()
    return atr

def in_kill_zone():
    now = datetime.datetime.utcnow().time()
    for start, end in KILL_ZONES:
        start_t = datetime.time(int(start.split(":")[0]), int(start.split(":")[1]))
        end_t = datetime.time(int(end.split(":")[0]), int(end.split(":")[1]))
        if start_t <= now <= end_t:
            return True
    return False

def detect_bos(df):
    if len(df) < 3:
        return None
    if df['Close'].iloc[-1] > df['High'].iloc[-3:-1].max():
        return "BOS_UP"
    elif df['Close'].iloc[-1] < df['Low'].iloc[-3:-1].min():
        return "BOS_DOWN"
    return None

def detect_order_block(df):
    last = df.iloc[-1]
    body = abs(last['Close'] - last['Open'])
    candle_range = last['High'] - last['Low']
    if candle_range == 0:
        return None
    if body / candle_range > 0.7:
        if last['Close'] > last['Open']:
            return "BUY_OB"
        else:
            return "SELL_OB"
    return None

def calculate_sl_tp(price, atr_value, direction):
    if direction == "BUY":
        sl = price - SL_ATR * atr_value
        tp = price + TP_ATR * atr_value
    else:
        sl = price + SL_ATR * atr_value
        tp = price - TP_ATR * atr_value
    return sl, tp

# ---------------- MAIN ----------------
def generate_signal():
    if not in_kill_zone():
        print("⏱️ Outside Kill Zones. No signals now.")
        return

    df_m1 = get_data(SYMBOL, period="1d", interval="1m")
    df_m5 = get_data(SYMBOL, period="5d", interval="5m")
    atr_m1 = atr(df_m1, ATR_PERIOD).iloc[-1]

    bos_signal = detect_bos(df_m1)
    ob_signal = detect_order_block(df_m1)

    trend = "BUY" if df_m5['Close'].iloc[-1] > df_m5['Close'].iloc[-5] else "SELL"

    direction = None
    if bos_signal and ob_signal:
        if bos_signal == "BOS_UP" and ob_signal == "BUY_OB" and trend == "BUY":
            direction = "BUY"
        elif bos_signal == "BOS_DOWN" and ob_signal == "SELL_OB" and trend == "SELL":
            direction = "SELL"

    if direction:
        price = df_m1['Close'].iloc[-1]
        sl, tp = calculate_sl_tp(price, atr_m1, direction)
        message = (
            f"💰 XAUUSD SIGNAL 💰\n"
            f"Direction: {direction}\n"
            f"Entry: {price:.2f}\n"
            f"SL: {sl:.2f} | TP: {tp:.2f}\n"
            f"Kill Zone: Active 🔥"
        )
        send_telegram(message)
        print("✅ Signal sent to Telegram!")
    else:
        print("❌ No valid signal now.")

# ---------------- RUN ----------------
if __name__ == "__main__":
    print("📡 XAUUSD Telegram Signal Bot Running...")
    while True:
        generate_signal()
        time.sleep(3600)  # Check every 1 hour (you can adjust)
