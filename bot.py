
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

# Indicator Periods
ATR_PERIOD = 14
EMA_FAST = 20
EMA_SLOW = 50

# Signal Confidence
MIN_CONFIDENCE = 75 # Lowered for more signals, will be adjusted by new logic

# Trading hours (UTC) - 10 AM GMT+4 is 6 AM UTC, 5 PM GMT+4 is 1 PM UTC
TRADING_START_HOUR = 6
TRADING_END_HOUR = 17

# Global variables for signal tracking
last_signal_time = None
last_signal_direction = None
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
def fetch_data(retries=5, delay=5):
    for attempt in range(retries):
        try:
            # Using TIME_SERIES_DAILY for Alpha Vantage Free Tier
            # Note: For true multi-timeframe analysis, a different API or paid Alpha Vantage plan would be needed.
            # This bot will use daily data and simulate shorter timeframe concepts where possible.
            url = f"https://www.alphavantage.co/query?function=TIME_SERIES_DAILY&symbol={SYMBOL}&apikey={API_KEY}&outputsize=full"
            res = requests.get(url, timeout=15).json()
            
            if "Time Series (Daily)" not in res:
                print(f"Attempt {attempt+1}: Alpha Vantage error or limit reached: {res.get("Note", "Unknown error")}")
                time.sleep(delay)
                continue
                
            raw_data = res["Time Series (Daily)"]
            df = pd.DataFrame.from_dict(raw_data, orient='index')
            df.index = pd.to_datetime(df.index)
            df = df.sort_index() # oldest to newest
            
            df = df.rename(columns={
                "1. open": "open",
                "2. high": "high",
                "3. low": "low",
                "4. close": "close",
                "5. volume": "volume"
            })
            
            for col in ["open","high","low","close"]:
                df[col] = df[col].astype(float)
            
            # Ensure enough data for indicators
            if len(df) < max(ATR_PERIOD, EMA_SLOW) + 5: # +5 for trendline/zone analysis
                print(f"Not enough data for analysis. Need at least {max(ATR_PERIOD, EMA_SLOW) + 5} days.")
                return None

            return df
        except requests.exceptions.RequestException as e:
            print(f"Attempt {attempt+1}: Network or API request error: {e}")
            time.sleep(delay)
        except Exception as e:
            print(f"Attempt {attempt+1}: Data processing error: {e}")
            time.sleep(delay)
    send_telegram("⚠️ Critical Error: Failed to fetch market data after multiple attempts.")
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
    return df["close"].ewm(span=period, adjust=False).mean()

def rsi(df, period=14):
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).ewm(span=period, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(span=period, adjust=False).mean()
    rs = gain / loss
    return 100 - (100 / (1 + rs))

def is_uptrend(df, periods=5):
    # Simple uptrend: higher lows and higher highs over recent periods
    if len(df) < periods:
        return False
    recent_df = df.iloc[-periods:]
    return all(recent_df["low"].diff().dropna() > 0) and all(recent_df["high"].diff().dropna() > 0)

def is_downtrend(df, periods=5):
    # Simple downtrend: lower highs and lower lows over recent periods
    if len(df) < periods:
        return False
    recent_df = df.iloc[-periods:]
    return all(recent_df["low"].diff().dropna() < 0) and all(recent_df["high"].diff().dropna() < 0)

def find_zones(df, window=10, threshold_atr_multiplier=1.5):
    # Identify potential supply/demand zones based on price consolidation or strong reversals
    # This is a simplified approach for daily data
    zones = []
    atr_val = atr(df).iloc[-1] # Use latest ATR for dynamic threshold
    if pd.isna(atr_val) or atr_val == 0: return []

    for i in range(window, len(df) - 1):
        # Check for consolidation (low volatility)
        high_range = df["high"].iloc[i-window:i].max()
        low_range = df["low"].iloc[i-window:i].min()
        if (high_range - low_range) < (threshold_atr_multiplier * atr_val):
            # Potential zone identified
            zone_avg = (high_range + low_range) / 2
            zone_size = (high_range - low_range) / 2
            zones.append({"type": "consolidation", "level": zone_avg, "range": zone_size})

        # Check for strong reversal (simplified: large candle after trend)
        # This is more complex and usually requires more advanced pattern recognition
        # For now, we'll focus on consolidation zones.

    return zones

# ---------------- SIGNAL ENGINE ----------------
def generate_signal(force_signal=False):
    global last_signal_time, last_signal_direction, last_sl_tp
    
    now_utc = datetime.now(pytz.utc)
    # Only generate signals within trading hours and once per hour for daily data
    if not force_signal and not (TRADING_START_HOUR <= now_utc.hour < TRADING_END_HOUR):
        print(f"Current UTC hour {now_utc.hour} is outside trading hours ({TRADING_START_HOUR}-{TRADING_END_HOUR}). Skipping signal generation.")
        return

    # Prevent duplicate signals within a short period (e.g., 30 minutes for daily data context)
    if not force_signal and last_signal_time and (now_utc - last_signal_time).total_seconds() < 1800: # 30 minutes
        print("Skipping signal generation: Too soon since last signal.")
        return

    df = fetch_data()
    if df is None or df.empty: 
        print("Failed to get data for signal generation.")
        return

    atr_val = atr(df).iloc[-1]
    if pd.isna(atr_val) or atr_val == 0: 
        print("ATR value is not valid.")
        return

    ema_fast = ema(df, EMA_FAST).iloc[-1]
    ema_slow = ema(df, EMA_SLOW).iloc[-1]
    price = df["close"].iloc[-1]
    
    current_trend = "UPTREND" if is_uptrend(df) else ("DOWNTREND" if is_downtrend(df) else "SIDEWAYS")
    zones = find_zones(df)

    # Determine primary direction based on EMA cross
    primary_direction = "BUY" if ema_fast > ema_slow else "SELL"

    # --- Enhanced Confidence and Entry Logic ---
    confidence = 50 # Base confidence
    analysis_text = []

    rsi_val = rsi(df).iloc[-1]
    if pd.isna(rsi_val): return # Not enough data for RSI


    # EMA Cross Confirmation
    if primary_direction == "BUY" and df["close"].iloc[-2] <= ema_slow and price > ema_slow:
        confidence += 15
        analysis_text.append("EMA Crossover (Bullish)")
    elif primary_direction == "SELL" and df["close"].iloc[-2] >= ema_slow and price < ema_slow:
        confidence += 15
        analysis_text.append("EMA Crossover (Bearish)")
    else:
        # If no fresh EMA cross, reduce confidence or adjust logic
        primary_direction = "NONE" # No strong EMA signal

    if primary_direction == "NONE":
        print("No strong EMA crossover signal.")
        return # No signal if no strong EMA cross

    # Trend Confirmation
    if primary_direction == "BUY" and current_trend == "UPTREND":
        confidence += 20
        analysis_text.append("Confirmed Uptrend")
    elif primary_direction == "SELL" and current_trend == "DOWNTREND":
        confidence += 20
        analysis_text.append("Confirmed Downtrend")
    else:
        # If trend doesn't align with EMA, reduce confidence significantly
        confidence -= 10
        analysis_text.append(f"Trend ({current_trend}) not fully aligned with EMA signal.")

    # Zone Interaction (Simplified: check if price is near a recent zone)
    zone_found = False
    for zone in zones:
        if abs(price - zone["level"]) < (zone["range"] + 0.5 * atr_val): # Price near a zone
            confidence += 15
            analysis_text.append(f"Price near a consolidation zone ({zone["level"]:.2f})")
            zone_found = True
            break
    if not zone_found:
        analysis_text.append("No clear zone interaction.")

    # RSI Confirmation
    if primary_direction == "BUY" and rsi_val < 40: # Oversold for buy
        confidence += 10
        analysis_text.append(f"RSI ({rsi_val:.2f}) indicates oversold conditions.")
    elif primary_direction == "SELL" and rsi_val > 60: # Overbought for sell
        confidence += 10
        analysis_text.append(f"RSI ({rsi_val:.2f}) indicates overbought conditions.")
    else:
        analysis_text.append(f"RSI ({rsi_val:.2f}) is neutral.")

    if confidence < MIN_CONFIDENCE:
        if force_signal and confidence >= 60: # Allow slightly lower confidence for forced signals
            analysis_text.append(f"Forced signal: Confidence {confidence}% (below standard minimum {MIN_CONFIDENCE}% but still strong).")
        else:
            print(f"Confidence {confidence}% below minimum {MIN_CONFIDENCE}%. Skipping signal.")
            if force_signal:
                send_telegram(f"⚠️ No strong signal found at this moment. Current confidence: {confidence}%")
            return

    # --- Signal Generation ---
    direction = primary_direction
    
    # Entry, SL, TP based on ATR and 168fx Royal style (multiple TPs)
    entry_buffer = 0.1 * atr_val # Small buffer around current price for entry zone
    entry_low = price - entry_buffer
    entry_high = price + entry_buffer

    if direction == "BUY":
        sl = price - 1.0 * atr_val # Wider SL
        tp1 = price + 1.0 * atr_val
        tp2 = price + 2.0 * atr_val
        tp3 = price + 3.0 * atr_val
    else:
        sl = price + 1.0 * atr_val # Wider SL
        tp1 = price - 1.0 * atr_val
        tp2 = price - 2.0 * atr_val
        tp3 = price - 3.0 * atr_val

    # Ensure SL/TP are reasonable (e.g., not too close to entry)
    min_sl_distance = 0.5 * atr_val
    if direction == "BUY" and (price - sl) < min_sl_distance: sl = price - min_sl_distance
    if direction == "SELL" and (sl - price) < min_sl_distance: sl = price + min_sl_distance

    # Prevent sending the same signal multiple times if conditions haven\'t changed significantly
    if not force_signal and last_signal_direction == direction and last_sl_tp and \
       abs(last_sl_tp["entry_low"] - entry_low) < (0.1 * atr_val) and \
       abs(last_sl_tp["entry_high"] - entry_high) < (0.1 * atr_val):
        print("Similar signal already sent recently. Skipping.")
        return
    msg = (
        f"🚀 ROYAL XAUUSD ELITE SIGNAL\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📊 Asset: {SYMBOL} (GOLD)\n"
        f"🕒 Timeframe: Daily (Simulated H1/H4 concepts)\n"
        f"💡 Type: {direction} ZONE\n"
        f"\n"
        f"📍 Entry: {entry_low:.2f} - {entry_high:.2f}\n"
        f"🎯 TP 1: {tp1:.2f}\n"
        f"🎯 TP 2: {tp2:.2f}\n"
        f"🎯 TP 3: {tp3:.2f}\n"
        f"🛑 SL: {sl:.2f}\n"
        f"\n"
        f"🔍 Analysis: {'; '.join(analysis_text)}. Confidence: {confidence}%\n"
        f"━━━━━━━━━━━━━━━"
    )

    send_telegram(msg)
    last_signal_time = now_utc
    last_signal_direction = direction
    last_sl_tp = {"sl": sl, "tp1": tp1, "tp2": tp2, "tp3": tp3, "direction": direction, "entry_low": entry_low, "entry_high": entry_high}
    print(f"Signal sent: {direction} at {price:.2f} with confidence {confidence}%")

# ---------------- TP/SL MONITOR ----------------
def monitor_tp_sl():
    global last_sl_tp
    while True:
        if last_sl_tp is None: 
            time.sleep(5) # Check more frequently for TP/SL
            continue
        df = fetch_data()
        if df is None or df.empty:
            time.sleep(5)
            continue
        price = df["close"].iloc[-1]
        sl = last_sl_tp["sl"]
        tp1 = last_sl_tp["tp1"]
        tp2 = last_sl_tp["tp2"]
        tp3 = last_sl_tp["tp3"]
        direction = last_sl_tp["direction"]

        # Simplified TP/SL monitoring for daily data
        # In a real-time scenario, this would need to check every tick/candle
        if direction == "BUY":
            if price <= sl:
                send_telegram(f"❌ BUY SL HIT at {price:.2f}")
                last_sl_tp = None
            elif price >= tp3: # Check highest TP first
                send_telegram(f"✅ BUY TP3 HIT at {price:.2f}")
                last_sl_tp = None
            elif price >= tp2:
                send_telegram(f"✅ BUY TP2 HIT at {price:.2f}")
                # Optionally, move SL to breakeven or TP1 here
            elif price >= tp1:
                send_telegram(f"✅ BUY TP1 HIT at {price:.2f}")
                # Optionally, move SL to breakeven
        else: # SELL
            if price >= sl:
                send_telegram(f"❌ SELL SL HIT at {price:.2f}")
                last_sl_tp = None
            elif price <= tp3:
                send_telegram(f"✅ SELL TP3 HIT at {price:.2f}")
                last_sl_tp = None
            elif price <= tp2:
                send_telegram(f"✅ SELL TP2 HIT at {price:.2f}")
            elif price <= tp1:
                send_telegram(f"✅ SELL TP1 HIT at {price:.2f}")
        time.sleep(60)  # Check every minute

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
                    send_telegram("🔥 ROYAL XAUUSD ELITE BOT ACTIVE")
                elif text == "/signal":
                    send_telegram("🔍 Analyzing chart for a strong signal...")
                    generate_signal(force_signal=True)
                elif text == "/price":
                    df = fetch_data()
                    if df is not None:
                        send_telegram(f"💰 XAUUSD Price: {df["close"].iloc[-1]:.2f}")
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
def run_auto_signaler():
    while True:
        # The 'be_ready' concept is removed as signals are now more precise
        # Signals will be generated only when conditions are met
        generate_signal()
        time.sleep(300) # Check for new signals every 5 minutes

# ---------------- START ----------------
if __name__ == "__main__":
    print("🚀 ROYAL XAUUSD ELITE BOT RUNNING...")
    threading.Thread(target=run_auto_signaler, daemon=True).start()
    threading.Thread(target=check_commands_loop, daemon=True).start()
    threading.Thread(target=monitor_tp_sl, daemon=True).start()
    while True:
        time.sleep(1)
