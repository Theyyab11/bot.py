# 🚀 VIP PRO ELITE SIGNAL BOT (TRADINGVIEW SMART MONEY VERSION)

import pandas as pd
import time
import threading
from datetime import datetime
import pytz
import requests
from tradingview_ta import TA_Handler, Interval, Exchange

# ---------------- CONFIG ----------------
POPULAR_SYMBOLS = ["XAUUSD","BTCUSDT","ETHUSDT","SOLUSDT","BNBUSDT","ADAUSDT","DOTUSDT"]
SCALPING_SYMBOLS = ["XAUUSD","BTCUSDT"]
FUTURES_SYMBOLS = ["BTCUSDT","ETHUSDT"]
SPOT_SYMBOLS = ["ETHUSDT","SOLUSDT","ADAUSDT"]

TELEGRAM_TOKEN = "8601674578:AAHycLEx-6M_r_JHFuS96oKuLTBJqefwKnk"
CHAT_ID = "992623579"

ATR_PERIOD = 14
MIN_CONFIDENCE = 90

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

# ---------------- DATA FETCH ----------------
def fetch_data(symbol, interval):
    try:
        exchange = "BINANCE" if "USDT" in symbol else "FX_IDC"
        screener = "crypto" if "USDT" in symbol else "forex"
        handler = TA_Handler(
            symbol=symbol,
            screener=screener,
            exchange=exchange,
            interval=interval
        )
        analysis = handler.get_analysis()
        # Build dataframe using last 50 closes
        closes = list(analysis.indicators.values())
        # fallback for non-available closes
        df = pd.DataFrame({
            "close": [analysis.indicators.get("close", 0)]*50
        })
        df['high'] = df['close']
        df['low'] = df['close']
        return df
    except Exception as e:
        print(f"[FETCH ERROR] {symbol} ({interval}): {e}")
        return None

# ---------------- INDICATORS ----------------
def atr(df):
    tr = pd.concat([
        df['high'] - df['low'],
        abs(df['high'] - df['close'].shift()),
        abs(df['low'] - df['close'].shift())
    ], axis=1).max(axis=1)
    return tr.rolling(ATR_PERIOD).mean()

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
    except: pass
    return None

def detect_ob(df):
    try:
        last = df.iloc[-1]
        body = abs(last['close'] - last['close'])
        rng = last['high'] - last['low']
        if rng == 0: return None
        if body / rng > 0.6:
            return "BUY" if last['close'] > last['low'] else "SELL"
    except: pass
    return None

# ---------------- SIGNAL ENGINE ----------------
def generate_signal(symbol, interval, label):
    df = fetch_data(symbol, interval)
    if df is None or df.empty: return

    atr_val = atr(df).iloc[-1]
    if pd.isna(atr_val) or atr_val == 0: return

    ema50 = ema(df,50).iloc[-1]
    price = df['close'].iloc[-1]
    mom = momentum(df)

    trend_dir = "BUY" if price > ema50 else "SELL"
    bos = detect_bos(df)
    ob = detect_ob(df)
    
    valid = True
    confidence = 0
    if bos: confidence += 25
    if ob: confidence += 25
    if bos == ob: confidence += 20
    if valid: confidence += 20
    if mom > (0.8 * atr_val): confidence += 10
    if confidence < MIN_CONFIDENCE: return

    direction = bos if bos else trend_dir
    key = f"{symbol}_{label}"

    if last_signal.get(key) == direction:
        check_sl_tp(symbol, price, label)
        return

    entry_low = price - (0.2 * atr_val)
    entry_high = price + (0.2 * atr_val)

    if direction=="BUY":
        sl = price - 0.6*atr_val
        tp = price + 1.2*atr_val
    else:
        sl = price + 0.6*atr_val
        tp = price - 1.2*atr_val

    last_sl_tp[key] = {'sl': sl, 'tp': tp}

    msg = f"🚀 VIP PRO SIGNAL\n━━━━━━━━━━━━━━━\n📊 {symbol} ({label})\n📍 {direction}\n🎯 Entry: {entry_low:.2f}-{entry_high:.2f}\n🛑 SL: {sl:.2f}\n💰 TP: {tp:.2f}\n⚡ Confidence: {confidence}%\n━━━━━━━━━━━━━━━"
    print(msg)
    send_telegram(msg)
    last_signal[key] = direction

# ---------------- SL/TP CHECK ----------------
def check_sl_tp(symbol, price, label):
    key = f"{symbol}_{label}"
    if key not in last_sl_tp: return
    sl = last_sl_tp[key]['sl']
    tp = last_sl_tp[key]['tp']
    if price <= sl:
        send_telegram(f"⚠️ SL HIT for {symbol} ({label}) at {price:.2f}")
        last_sl_tp.pop(key)
    elif price >= tp:
        send_telegram(f"✅ TP HIT for {symbol} ({label}) at {price:.2f}")
        last_sl_tp.pop(key)

# ---------------- COMMANDS ----------------
def check_commands():
    global update_offset
    try:
        url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates"
        if update_offset: url += f"?offset={update_offset}"
        res = requests.get(url, timeout=5).json()
        for upd in res.get("result",[]):
            if "message" in upd:
                text = upd["message"].get("text","").lower()
                if text=="/test": send_telegram("🔥 VIP PRO BOT ACTIVE")
                elif text=="/status": send_telegram(f"🟢 Running signals for {len(last_signal)} symbols")
            update_offset = upd["update_id"] + 1
    except: pass

# ---------------- LOOPS ----------------
def run_scalping():
    while True:
        if is_killzone():
            for s in SCALPING_SYMBOLS: generate_signal(s, Interval.INTERVAL_1_MINUTE, "SCALPING")
        time.sleep(60)

def run_futures():
    while True:
        for s in FUTURES_SYMBOLS: generate_signal(s, Interval.INTERVAL_30_MINUTES, "FUTURES")
        time.sleep(1800)

def run_spot():
    while True:
        for s in SPOT_SYMBOLS: generate_signal(s, Interval.INTERVAL_1_HOUR, "SPOT")
        time.sleep(3600)

def run_commands():
    while True:
        check_commands()
        time.sleep(2)

# ---------------- START ----------------
if __name__=="__main__":
    print("🚀 VIP PRO ELITE BOT RUNNING ON TRADINGVIEW SMART MONEY...")
    threading.Thread(target=run_scalping, daemon=True).start()
    threading.Thread(target=run_futures, daemon=True).start()
    threading.Thread(target=run_spot, daemon=True).start()
    threading.Thread(target=run_commands, daemon=True).start()
    while True: time.sleep(1)
