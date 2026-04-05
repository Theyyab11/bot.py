# 🚀 FAST PRO SNIPER BOT (TwelveData Live Prices, Scalping Mode)

import requests
import pandas as pd
import time
import threading

# ---------------- CONFIG ----------------
SYMBOLS = ["XAU/USD", "BTC/USD"]  # Exness symbols
INTERVAL = "1min"                 # live price interval
ATR_PERIOD = 14
MIN_CONFIDENCE = 85               # strong sniper signal
COOLDOWN_PER_ASSET = 60           # 1 min per asset (fast scalping)

TELEGRAM_TOKEN = "8601674578:AAHycLEx-6M_r_JHFuS96oKuLTBJqefwKnk"
CHAT_ID = "992623579"
TWELVEDATA_API_KEY = "ab9ad3eac834482c84366b4e57ffefa7"

last_signal_time = {symbol: 0 for symbol in SYMBOLS}
update_offset = None

# ---------------- HELPERS ----------------
def send_telegram(message):
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
        requests.post(url, data={"chat_id": CHAT_ID, "text": message})
    except Exception as e:
        print("Telegram error:", e)

def fetch_data(symbol):
    url = f"https://api.twelvedata.com/time_series?symbol={symbol}&interval={INTERVAL}&outputsize=30&apikey={TWELVEDATA_API_KEY}"
    try:
        res = requests.get(url, timeout=5).json()
        if "values" not in res:
            print(f"Fetch error ({symbol}):", res)
            return None
        df = pd.DataFrame(res["values"])[::-1]  # oldest -> newest
        df[['open','high','low','close']] = df[['open','high','low','close']].astype(float)
        return df
    except Exception as e:
        print(f"Fetch error ({symbol}):", e)
        return None

def atr(df):
    tr = pd.concat([
        df['high'] - df['low'],
        abs(df['high'] - df['close'].shift()),
        abs(df['low'] - df['close'].shift())
    ], axis=1).max(axis=1)
    return tr.rolling(ATR_PERIOD).mean()

# ---------------- SIGNAL LOGIC ----------------
def detect_bos(df):
    try:
        last = df['close'].iloc[-1]
        high = df['high'].iloc[-3:-1].max()
        low = df['low'].iloc[-3:-1].min()
        if last > high: return "BUY"
        if last < low: return "SELL"
    except: pass
    return None

def detect_ob(df):
    try:
        last = df.iloc[-1]
        body = abs(last['close'] - last['open'])
        rng = last['high'] - last['low']
        if rng == 0: return None
        if body / rng > 0.6:
            return "BUY" if last['close'] > last['open'] else "SELL"
    except: pass
    return None

def momentum_strength(df):
    try:
        if len(df['close']) < 5: return 0
        return abs(df['close'].iloc[-1] - df['close'].iloc[-5])
    except:
        return 0

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
        return price - 0.5*atr_val, price + atr_val  # tight SL/TP for scalping
    else:
        return price + 0.5*atr_val, price - atr_val

# ---------------- SNIPER SIGNAL ----------------
def generate_signal():
    signal_sent = False
    for symbol in SYMBOLS:
        try:
            if time.time() - last_signal_time.get(symbol, 0) < COOLDOWN_PER_ASSET:
                continue

            df = fetch_data(symbol)
            if df is None or df.empty: continue

            atr_val = atr(df).iloc[-1]
            if pd.isna(atr_val) or atr_val == 0: continue

            bos = detect_bos(df)
            ob = detect_ob(df)
            trend = "BUY" if df['close'].iloc[-1] > df['close'].iloc[-3] else "SELL"
            momentum = momentum_strength(df)
            confidence = calculate_confidence(bos, ob, trend, momentum, atr_val)

            if confidence >= MIN_CONFIDENCE:
                direction = bos if bos else trend
                price = df['close'].iloc[-1]
                sl, tp = calculate_sl_tp(price, atr_val, direction)

                msg = (
                    f"🎯 SNIPER SIGNAL 🎯\n"
                    f"Asset: {symbol}\n"
                    f"Direction: {direction}\n"
                    f"Entry: {price:.2f}\n"
                    f"SL: {sl:.2f} | TP: {tp:.2f}\n"
                    f"Confidence: {confidence}% 🔥"
                )
                send_telegram(msg)
                last_signal_time[symbol] = time.time()
                signal_sent = True
        except Exception as e:
            print(f"Signal error ({symbol}):", e)

    if not signal_sent:
        send_telegram("⏳ I am currently sniping...")

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
                    send_telegram("✅ FAST PRO SNIPER BOT ACTIVE 🔥")
            update_offset = upd["update_id"] + 1
    except:
        pass

# ---------------- THREADS ----------------
def run_signals():
    while True:
        generate_signal()
        time.sleep(60)  # 1-minute scalping scan

def run_commands():
    while True:
        check_commands()
        time.sleep(2)

# ---------------- RUN ----------------
if __name__ == "__main__":
    print("🚀 FAST PRO SNIPER BOT RUNNING...")
    threading.Thread(target=run_signals, daemon=True).start()
    threading.Thread(target=run_commands, daemon=True).start()
    while True:
        time.sleep(1)
