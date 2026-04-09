# ⚡ ROYAL FAST M1 SCALPER (XAUUSD & BTCUSD)
# 🎯 REAL-TIME ACCURACY: BINANCE WEBSOCKET + GOLD-API.COM (NO KEY REQUIRED)

import websocket
import json
import threading
import time
import pandas as pd
import requests
from datetime import datetime
import pytz
from telegram import Update
from telegram.ext import Updater, CommandHandler, CallbackContext

# ---------------- CONFIG ----------------
TELEGRAM_TOKEN = "8601674578:AAHycLEx-6M_r_JHFuS96oKuLTBJqefwKnk"
CHAT_ID = "992623579"

# Scalping Parameters
ATR_PERIOD = 14
EMA_FAST = 9
EMA_SLOW = 21
RSI_PERIOD = 7
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

# Trading Hours (UTC) - 10 AM GMT+4 is 6 AM UTC
TRADING_START_HOUR = 6
TRADING_END_HOUR = 22

# Data Storage
klines = {"BTCUSD": [], "XAUUSD": []}
last_signal_time = {"BTCUSD": 0, "XAUUSD": 0}

# Global bot instance for sending messages
bot_instance = None

# ---------------- TELEGRAM ----------------
def send_telegram(msg, chat_id=CHAT_ID):
    global bot_instance
    if bot_instance:
        try:
            bot_instance.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")
        except Exception as e:
            print(f"Telegram send error: {e}")
    else:
        # Fallback if bot_instance is not yet initialized (e.g., initial online message)
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            requests.post(url, data={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"})
        except Exception as e:
            print(f"Telegram fallback send error: {e}")

# ---------------- INDICATORS ----------------
def calculate_indicators(df):
    # ATR
    tr = pd.concat([
        df["high"] - df["low"],
        abs(df["high"] - df["close"].shift()),
        abs(df["low"] - df["close"].shift())
    ], axis=1).max(axis=1)
    df["atr"] = tr.rolling(ATR_PERIOD).mean()

    # EMA
    df["ema_fast"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
    df["ema_slow"] = df["close"].ewm(span=EMA_SLOW, adjust=False).mean()

    # RSI
    delta = df["close"].diff()
    gain = (delta.where(delta > 0, 0)).ewm(span=RSI_PERIOD, adjust=False).mean()
    loss = (-delta.where(delta < 0, 0)).ewm(span=RSI_PERIOD, adjust=False).mean()
    rs = gain / loss
    df["rsi"] = 100 - (100 / (1 + rs))

    return df

# ---------------- SIGNAL ENGINE ----------------
def generate_signal_message(symbol, direction, price, sl, tp):
    return (
        f"<b>{symbol} {direction} NOW</b> 🔥\n\n"
        f"» POINT      : {price:.2f}\n"
        f"» STOPLOSS   : {sl:.2f}\n"
        f"» TAKE PROFIT : {tp:.2f}\n\n"
        f"<i>PLEASE ENSURE PROPER MONEY MANAGEMENT</i> ‼️\n"
        f"#168FX"
    )

def check_signal(symbol, df, chat_id=CHAT_ID):
    global last_signal_time
    
    if len(df) < 30: return
    
    row = df.iloc[-1]
    prev_row = df.iloc[-2]
    
    price = row["close"]
    atr_val = row["atr"]
    rsi_val = row["rsi"]
    ema_f = row["ema_fast"]
    ema_s = row["ema_slow"]
    
    # M1 Scalping Logic: EMA Cross + RSI Confirmation
    direction = None
    if ema_f > ema_s and prev_row["ema_fast"] <= prev_row["ema_slow"] and rsi_val < 65:
        direction = "BUY"
    elif ema_f < ema_s and prev_row["ema_fast"] >= prev_row["ema_slow"] and rsi_val > 35:
        direction = "SELL"
        
    if direction:
        # Avoid duplicate signals within 5 minutes for M1
        if time.time() - last_signal_time[symbol] < 300:
            return
            
        # SL/TP for Scalping (Tight)
        if direction == "BUY":
            sl = price - (1.5 * atr_val)
            tp = price + (2.0 * atr_val)
        else:
            sl = price + (1.5 * atr_val)
            tp = price - (2.0 * atr_val)
            
        msg = generate_signal_message(symbol, direction, price, sl, tp)
        send_telegram(msg, chat_id)
        last_signal_time[symbol] = time.time()

# ---------------- DATA FETCHING ----------------
def fetch_gold_price():
    while True:
        try:
            url = "https://api.gold-api.com/price/XAU/USD"
            res = requests.get(url).json()
            if "price" in res:
                price = float(res["price"])
                # Build M1 candles from prices
                klines["XAUUSD"].append({
                    "close": price, "high": price, "low": price, "open": price
                })
                if len(klines["XAUUSD"]) > 100: klines["XAUUSD"].pop(0)
                df = pd.DataFrame(klines["XAUUSD"])
                df = calculate_indicators(df)
                check_signal("XAUUSD", df)
            time.sleep(60) # Recommended interval to avoid IP block
        except Exception as e:
            print(f"Gold fetch error: {e}")
            time.sleep(60)

def on_btc_message(ws, message):
    data = json.loads(message)
    if "k" in data:
        k = data["k"]
        if k["x"]: # Candle closed
            klines["BTCUSD"].append({
                "open": float(k["o"]),
                "high": float(k["h"]),
                "low": float(k["l"]),
                "close": float(k["c"]),
                "volume": float(k["v"])
            })
            if len(klines["BTCUSD"]) > 100: klines["BTCUSD"].pop(0)
            df = pd.DataFrame(klines["BTCUSD"])
            df = calculate_indicators(df)
            check_signal("BTCUSD", df)

def run_btc_ws():
    ws_url = "wss://fstream.binance.com/ws/btcusdt@kline_1m"
    ws = websocket.WebSocketApp(ws_url, on_message=on_btc_message)
    ws.run_forever()

# ---------------- TELEGRAM COMMAND HANDLERS ----------------
def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_html("✅ ROYAL M1 SCALPER ONLINE - REAL-TIME MODE")

def test_command(update: Update, context: CallbackContext) -> None:
    update.message.reply_html("Bot is active and responding!")

def signal_command(update: Update, context: CallbackContext) -> None:
    # Force a signal check for both symbols
    for symbol in klines:
        if len(klines[symbol]) > 30:
            df = pd.DataFrame(klines[symbol])
            df = calculate_indicators(df)
            # Temporarily set last_signal_time to 0 to force a signal
            original_last_signal_time = last_signal_time[symbol]
            last_signal_time[symbol] = 0
            check_signal(symbol, df, update.message.chat_id)
            last_signal_time[symbol] = original_last_signal_time # Restore original
        else:
            update.message.reply_html(f"Not enough data for {symbol} to generate a signal yet.")

def price_command(update: Update, context: CallbackContext) -> None:
    # Get current prices for both symbols
    xau_price = klines["XAUUSD"][-1]["close"] if klines["XAUUSD"] else "N/A"
    btc_price = klines["BTCUSD"][-1]["close"] if klines["BTCUSD"] else "N/A"
    msg = (
        f"<b>CURRENT PRICES</b>\n\n"
        f"» XAUUSD : {xau_price:.2f}\n"
        f"» BTCUSD : {btc_price:.2f}"
    )
    update.message.reply_html(msg)

# ---------------- START ----------------
if __name__ == "__main__":
    print("🚀 ROYAL FAST M1 SCALPER STARTING...")
    
    # Initialize Telegram Updater and Dispatcher
    updater = Updater(TELEGRAM_TOKEN)
    dispatcher = updater.dispatcher
    bot_instance = updater.bot # Set global bot instance

    # Add command handlers
    dispatcher.add_handler(CommandHandler("start", start))
    dispatcher.add_handler(CommandHandler("test", test_command))
    dispatcher.add_handler(CommandHandler("signal", signal_command))
    dispatcher.add_handler(CommandHandler("price", price_command))

    # Start the Telegram bot in a separate thread
    updater_thread = threading.Thread(target=updater.start_polling, daemon=True)
    updater_thread.start()

    # Send initial online message
    send_telegram("✅ ROYAL M1 SCALPER ONLINE - REAL-TIME MODE")
    
    # Start BTC WebSocket
    threading.Thread(target=run_btc_ws, daemon=True).start()
    
    # Start Gold REST Fetcher
    threading.Thread(target=fetch_gold_price, daemon=True).start()
    
    # Keep the main thread alive
    updater_thread.join() # This will keep the main thread alive as long as the updater is running
