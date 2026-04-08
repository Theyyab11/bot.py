# 🚀 XAUUSD ELITE M1 AUTOPILOT SNIPER BOT (ALPHA VANTAGE VERSION)

import requests
import pandas as pd
import time
import threading
from datetime import datetime
import pytz

# ---------------- CONFIG ----------------
SYMBOL = "XAUUSD"
API_KEY = "LYL856NCQDQ4PJAH"  # Your new Alpha Vantage API Key
TELEGRAM_TOKEN = "8601674578:AAHycLEx-6M_r_JHFuS96oKuLTBJqefwKnk"
CHAT_ID = "992623579"

ATR_PERIOD = 14
EMA_FAST = 20
EMA_SLOW = 50
MIN_CONFIDENCE = 90

# Trading hours (UTC)
# 10 AM GMT+4 is 6 AM UTC
TRADING_START_HOUR = 6
TRADING_END_HOUR = 17   # 5 PM GMT+4 is 1 PM UTC

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

# ---------------- DATA ----------------
def fetch_data(retries=3, delay=1):
    for attempt in range(retries):
        try:
            # Using TIME_SERIES_DAILY for Alpha Vantage Free Tier
            url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={SYMBOL}&apikey={API_KEY}"
            res = requests.get(url, timeout=10).json()
            
            if "Time Series (Daily)" not in res:
                print(f"Attempt {attempt+1}: Alpha Vantage error or limit reached: {res.get('Note', 'Unknown error')}")
                time.sleep(delay)
                continue
                
            # Convert to DataFrame
            raw_data = res["Time Series (Daily)"]
            df = pd.DataFrame.from_dict(raw_data, orient='index')
            df.index = pd.to_datetime(df.index)
            df = df.sort_index() # oldest to newest
            
            # Rename columns to match original script
            df = df.rename(columns={
                "1. open": "open",
                "2. high": "high",
                "3. low": "low",
                "4. close": "close",
                "5. volume": "volume"
            })
            
            for col in ["open","high","low","close"]:
                df[col] = df[col].astype(float)
                
            return df
        except Exception as e:
            print(f"Attempt {attempt+1}: Fetch error:", e)
            time.sleep(delay)
    return None

# ---------------- INDICATORS ----------------
def atr(df):
    tr = pd.concat([
        df["high"] - df["low"],
        abs(df["high"] - df["close"].shift()),
        abs(df["low"] - df["close"].shift())
    ], axis=1).max(axis=1)
    return tr.rolling(ATR_PERIOD).mean()

def ema(df, period):
    return df["close"].ewm(span=period).mean()

def momentum(df):
    # Daily momentum (last 5 days)
    return abs(df["close"].iloc[-1] - df["close"].iloc[-5])

# ---------------- SIGNAL ENGINE ----------------
def generate_signal(be_ready=False):
    global last_signal, last_sl_tp
    
    # Time-based filter
    now_utc = datetime.now(pytz.utc)
    if not (TRADING_START_HOUR <= now_utc.hour < TRADING_END_HOUR):
        if not be_ready:
            print(f"Current UTC hour {now_utc.hour} is outside trading hours ({TRADING_START_HOUR}-{TRADING_END_HOUR}). Skipping.")
        return

    df = fetch_data()
    if df is None or df.empty: return

    atr_val = atr(df).iloc[-1]
    if pd.isna(atr_val) or atr_val == 0: return

    ema_fast = ema(df, EMA_FAST).iloc[-1]
    ema_slow = ema(df, EMA_SLOW).iloc[-1]
    price = df["close"].iloc[-1]
    mom = momentum(df)

    direction = "BUY" if ema_fast > ema_slow else "SELL"

    # --- Improved Confidence Calculation ---
    confidence = 70
    if mom > 0.5 * atr_val: confidence += 10
    if mom > 0.8 * atr_val: confidence += 10
    if (direction=="BUY" and price > ema_slow) or (direction=="SELL" and price < ema_slow): confidence += 10

    # Price-EMA Cross confirmation
    if direction == "BUY" and df['close'].iloc[-2] <= ema_slow and price > ema_slow:
        confidence += 5
    elif direction == "SELL" and df['close'].iloc[-2] >= ema_slow and price < ema_slow:
        confidence += 5

    if confidence < MIN_CONFIDENCE: return

    if be_ready:
        send_telegram(f"⚠️ BE READY — {direction} ZONE NOW! Prepare!")
        return

    entry_low = price - 0.05 * atr_val
    entry_high = price + 0.05 * atr_val

    if direction == "BUY":
        sl = price - 0.5 * atr_val
        tp = price + 1.5 * atr_val
    else:
        sl = price + 0.5 * atr_val
        tp = price - 1.5 * atr_val

    msg = (
        f"🚀 ELITE GOLD DAILY SIGNAL (AV)\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📊 XAUUSD (Daily)\n"
        f"📍 {direction}\n"
        f"🎯 Entry: {entry_low:.2f} - {entry_high:.2f}\n"
        f"🛑 SL: {sl:.2f}\n"
        f"💰 TP: {tp:.2f}\n"
        f"⚡ Confidence: {confidence}%\n"
        f"━━━━━━━━━━━━━━━"
    )

    send_telegram(msg)
    last_signal = direction
    last_sl_tp = {"sl": sl, "tp": tp, "direction": direction, "entry_low": entry_low, "entry_high": entry_high}

# ---------------- TP/SL MONITOR ----------------
def monitor_tp_sl():
    global last_sl_tp
    while True:
        if last_sl_tp is None: 
            time.sleep(1)
            continue
        df = fetch_data()
        if df is None or df.empty:
            time.sleep(1)
            continue
        price = df["close"].iloc[-1]
        sl = last_sl_tp["sl"]
        tp = last_sl_tp["tp"]
        direction = last_sl_tp["direction"]

        if direction == "BUY":
            if price <= sl:
                send_telegram(f"❌ BUY SL HIT at {price:.2f}")
                last_sl_tp = None
            elif price >= tp:
                send_telegram(f"✅ BUY TP HIT at {price:.2f}")
                last_sl_tp = None
        else:
            if price >= sl:
                send_telegram(f"❌ SELL SL HIT at {price:.2f}")
                last_sl_tp = None
            elif price <= tp:
                send_telegram(f"✅ SELL TP HIT at {price:.2f}")
                last_sl_tp = None
        time.sleep(60)  # Daily check, every minute is enough

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
                    send_telegram("🔥 ELITE GOLD AV BOT ACTIVE")
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

def check_commands_loop():
    while True:
        check_commands()
        time.sleep(2)

# ---------------- AUTO LOOP ----------------
def run_auto_scalper():
    while True:
        generate_signal(be_ready=True)
        time.sleep(10)
        generate_signal(be_ready=False)
        time.sleep(3600) # Check every hour for daily signals

# ---------------- START ----------------
if __name__ == "__main__":
    print("🚀 ELITE GOLD AV BOT RUNNING...")
    threading.Thread(target=run_auto_scalper, daemon=True).start()
    threading.Thread(target=check_commands_loop, daemon=True).start()
    threading.Thread(target=monitor_tp_sl, daemon=True).start()
    while True:
        time.sleep(1)
