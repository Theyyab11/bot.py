# 🚀 VIP PRO ELITE SIGNAL BOT (NO AUTO TRADING - HIGH ACCURACY)

import requests
import pandas as pd
import time
import threading
from datetime import datetime
import pytz

# ---------------- CONFIG ----------------
SCALPING_SYMBOLS = ["XAU/USD", "BTC/USD"]
FUTURES_SYMBOLS = ["BONK/USDT"]
SPOT_SYMBOLS = ["ETH/USDT", "SOL/USDT"]

API_KEY = "ab9ad3eac834482c84366b4e57ffefa7"

TELEGRAM_TOKEN = "8601674578:AAHycLEx-6M_r_JHFuS96oKuLTBJqefwKnk"
CHAT_ID = "992623579"  # VIP channel/group ID

ATR_PERIOD = 14
MIN_CONFIDENCE = 90  # PRO signals only

last_signal = {}
last_sl_tp = {}
update_offset = None
# ---------------- TELEGRAM ----------------
def send_telegram(msg):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": msg})
    except Exception as e:
        print("Telegram error:", e)

# ---------------- SESSION FILTER ----------------
def is_killzone():
    dubai = pytz.timezone("Asia/Dubai")
    hour = datetime.now(dubai).hour
    return (11 <= hour <= 14) or (16 <= hour <= 19)

# ---------------- DATA ----------------
def fetch_data(symbol, interval):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={interval}&outputsize=50&apikey={API_KEY}"
    try:
        res = requests.get(url, timeout=5).json()
        if "values" not in res:
            return None
        df = pd.DataFrame(res["values"])[::-1]
        df[['open','high','low','close']] = df[['open','high','low','close']].astype(float)
        return df
    except:
        return None

# ---------------- INDICATORS ----------------
def atr(df):
    tr = pd.concat([
        df['high'] - df['low'],
        abs(df['high'] - df['close'].shift()),
        abs(df['low'] - df['close'].shift())
    ], axis=1).max(axis=1)
    return tr.rolling(ATR_PERIOD).mean()

def rsi(df, period=14):
    delta = df['close'].diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = -delta.clip(upper=0).rolling(period).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def ema(df, period=50):
    return df['close'].ewm(span=period).mean()

def momentum(df):
    return abs(df['close'].iloc[-1] - df['close'].iloc[-5])

# ---------------- SMART MONEY ----------------
def detect_bos(df):
    try:
        last = df['close'].iloc[-1]
        high = df['high'].iloc[-3:-1].max()
        low = df['low'].iloc[-3:-1].min()
        if last > high: return "BUY"
        if last < low: return "SELL"
    except:
        pass
    return None

def detect_ob(df):
    try:
        last = df.iloc[-1]
        body = abs(last['close'] - last['open'])
        rng = last['high'] - last['low']
        if rng == 0: return None
        if body / rng > 0.6:
            return "BUY" if last['close'] > last['open'] else "SELL"
    except:
        pass
    return None

# ---------------- SIGNAL ENGINE ----------------
def generate_signal(symbol, interval, label):
    df = fetch_data(symbol, interval)
    if df is None or df.empty:
        return

    atr_val = atr(df).iloc[-1]
    if pd.isna(atr_val) or atr_val == 0:
        return

    ema50 = ema(df, 50).iloc[-1]
    rsi_val = rsi(df).iloc[-1]
    price = df['close'].iloc[-1]

    trend_dir = "BUY" if price > ema50 else "SELL"
    mom = momentum(df)

    bos = detect_bos(df)
    ob = detect_ob(df)

    valid = (trend_dir == "BUY" and rsi_val < 70) or (trend_dir == "SELL" and rsi_val > 30)

    confidence = 0
    if bos: confidence += 25
    if ob: confidence += 25
    if bos == ob: confidence += 20
    if valid: confidence += 20
    if mom > (0.8 * atr_val): confidence += 10

    if confidence < MIN_CONFIDENCE:
        return

    direction = bos if bos else trend_dir
    key = f"{symbol}_{label}"

    # Only send new signal if direction changed
    if last_signal.get(key) == direction:
        # Check SL/TP hit simulation
        check_sl_tp(symbol, price, label)
        return

    # ENTRY ZONE
    entry_low = price - (0.2 * atr_val)
    entry_high = price + (0.2 * atr_val)

    if direction == "BUY":
        sl = price - 0.6 * atr_val
        tp = price + 1.2 * atr_val
    else:
        sl = price + 0.6 * atr_val
        tp = price - 1.2 * atr_val

    # Save last SL/TP for tracking
    last_sl_tp[key] = {'sl': sl, 'tp': tp}

    msg = (
        f"🚀 VIP PRO SIGNAL\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📊 {symbol} ({label})\n"
        f"📍 {direction}\n"
        f"🎯 Entry Zone: {entry_low:.2f} - {entry_high:.2f}\n"
        f"🛑 SL: {sl:.2f}\n"
        f"💰 TP: {tp:.2f}\n"
        f"⚡ Confidence: {confidence}%\n"
        f"━━━━━━━━━━━━━━━"
    )

    send_telegram(msg)
    last_signal[key] = direction

# ---------------- SL/TP CHECK ----------------
def check_sl_tp(symbol, price, label):
    key = f"{symbol}_{label}"
    if key not in last_sl_tp:
        return

    sl = last_sl_tp[key]['sl']
    tp = last_sl_tp[key]['tp']

    if price <= sl:
        send_telegram(f"⚠️ SL HIT for {symbol} ({label}) at {price:.2f}")
        last_sl_tp.pop(key)
    elif price >= tp:
        send_telegram(f"✅ TP HIT for {symbol} ({label}) at {price:.2f}")
        last_sl_tp.pop(key)

# ---------------- LOOPS ----------------
def run_scalping():
    while True:
        if is_killzone():
            for s in SCALPING_SYMBOLS:
                generate_signal(s, "1min", "SCALPING")
        time.sleep(60)

def run_futures():
    while True:
        for s in FUTURES_SYMBOLS:
            generate_signal(s, "30min", "FUTURES (3x)")
        time.sleep(1800)

def run_spot():
    while True:
        for s in SPOT_SYMBOLS:
            generate_signal(s, "1h", "SPOT")
        time.sleep(3600)

# ---------------- COMMANDS ----------------
def check_commands():
    global update_offset
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        if update_offset:
            url += f"?offset={update_offset}"

        res = requests.get(url, timeout=5).json()
        for upd in res.get("result", []):
            if "message" in upd:
                text = upd["message"].get("text", "").lower()

                if text == "/test":
                    send_telegram("🔥 VIP PRO BOT ACTIVE")

            update_offset = upd["update_id"] + 1
    except:
        pass

def run_commands():
    while True:
        check_commands()
        time.sleep(2)

# ---------------- START ----------------
if __name__ == "__main__":
    print("🚀 VIP PRO BOT RUNNING...")

    threading.Thread(target=run_scalping, daemon=True).start()
    threading.Thread(target=run_futures, daemon=True).start()
    threading.Thread(target=run_spot, daemon=True).start()
    threading.Thread(target=run_commands, daemon=True).start()

    while True:
        time.sleep(1)
