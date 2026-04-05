# 🚀 PRO FAST AI SNIPER BOT (Multi-Asset: Gold + BTC + Oil + Forex + Indices)

import yfinance as yf
import pandas as pd
from datetime import datetime
import time
import threading
import requests

# ---------------- CONFIG ----------------
SYMBOLS = {
    "GOLD": "GC=F",
    "BTC": "BTC-USD",
    "OIL": "CL=F",
    "ETH": "ETH-USD",
    "EURUSD": "EURUSD=X",
    "GBPUSD": "GBPUSD=X",
    "USDJPY": "JPY=X",
    "NASDAQ": "^IXIC",
    "SP500": "^GSPC"
}

ATR_PERIOD = 14
MIN_CONFIDENCE = 70   # sniper mode strength
COOLDOWN_PER_ASSET = 120  # seconds per asset

TELEGRAM_TOKEN = "8601674578:AAHycLEx-6M_r_JHFuS96oKuLTBJqefwKnk"
CHAT_ID = "992623579"

last_signal_time = {key: 0 for key in SYMBOLS}
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
        return ["BTC", "ETH"]  # weekends only crypto
    return ["GOLD", "OIL", "EURUSD", "GBPUSD", "USDJPY", "NASDAQ", "SP500"]

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

# ---------------- LOGIC ----------------
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
    if momentum > (0.8 * atr_val): score += 15
    return min(score, 100)

def calculate_sl_tp(price, atr_val, direction):
    if direction == "BUY":
        return price - atr_val, price + (1.5 * atr_val)
    else:
        return price + atr_val, price - (1.5 * atr_val)

# ---------------- SNIPER SIGNAL ----------------
def generate_signal():
    best_signal = None
    best_score = 0
    best_asset = None

    for asset in get_active_symbols():
        if time.time() - last_signal_time[asset] < COOLDOWN_PER_ASSET:
            continue

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

        if confidence > best_score:
            best_score = confidence
            best_asset = asset
            best_signal = {
                "direction": bos if bos else trend,
                "price": df_m1['Close'].iloc[-1],
                "atr": atr_val,
                "confidence": confidence
            }

    if best_signal and best_score >= MIN_CONFIDENCE:
        asset_name = {
            "GOLD": "🥇 Gold",
            "BTC": "🪙 BTC",
            "ETH": "💎 ETH",
            "OIL": "🛢️ Oil",
            "EURUSD": "💱 EURUSD",
            "GBPUSD": "💱 GBPUSD",
            "USDJPY": "💱 USDJPY",
            "NASDAQ": "📈 NASDAQ",
            "SP500": "📊 S&P 500"
        }[best_asset]

        send_telegram(f"🎯 SNIPER ALERT: {asset_name} BEST setup detected...")
        time.sleep(1)

        sl, tp = calculate_sl_tp(
            best_signal["price"],
            best_signal["atr"],
            best_signal["direction"]
        )

        msg = (
            f"🎯 SNIPER SIGNAL 🎯\n"
            f"Asset: {asset_name}\n"
            f"Direction: {best_signal['direction']}\n"
            f"Entry: {best_signal['price']:.2f}\n"
            f"SL: {sl:.2f} | TP: {tp:.2f}\n"
            f"Confidence: {best_signal['confidence']}% 🔥"
        )

        send_telegram(msg)
        last_signal_time[best_asset] = time.time()

# ---------------- COMMANDS FIX ----------------
def check_commands():
    global update_offset
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        if update_offset:
            url += f"?offset={update_offset}"
        res = requests.get(url, timeout=10).json()
        for upd in res.get("result", []):
            if "message" in upd:
                text = upd["message"].get("text", "").lower()
                chat_id = upd["message"]["chat"]["id"]

                if text == "/test":
                    send_telegram("✅ FAST PRO SNIPER BOT ACTIVE 🔥")
                if text == "/force":
                    send_telegram("⚡ FORCED SNIPER SIGNAL TEST...")
                    generate_signal()

            update_offset = upd["update_id"] + 1
    except:
        pass  # ignore network errors

# ---------------- THREADS ----------------
def run_signals():
    while True:
        try:
            generate_signal()
        except Exception as e:
            print("Signal Error:", e)
        time.sleep(10)

def run_commands():
    while True:
        check_commands()
        time.sleep(2)

# ---------------- RUN ----------------
if __name__ == "__main__":
    print("🚀 FAST PRO SNIPER BOT RUNNING...")

    # Ignore all old messages at startup
    try:
        res = requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates", timeout=10).json()
        if "result" in res and len(res["result"]) > 0:
            update_offset = res["result"][-1]["update_id"] + 1
    except:
        update_offset = None

    threading.Thread(target=run_signals, daemon=True).start()
    threading.Thread(target=run_commands, daemon=True).start()

    while True:
        time.sleep(1)
