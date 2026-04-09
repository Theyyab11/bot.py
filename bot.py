# ⚡ ROYAL FAST M1 SCALPER (XAUUSD & BTCUSD)
# 🎯 REAL-TIME ACCURACY: BINANCE WEBSOCKET + GOLD-API.COM

# ⚡ ROYAL FAST M1 SCALPER (XAUUSD & BTCUSD)
# 🎯 REAL-TIME ACCURACY: BINANCE WEBSOCKET + GOLD-API.COM

import websocket
import json
import threading
import time
import pandas as pd
import requests
from datetime import datetime
import pytz
import asyncio
import os
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ---------------- CONFIG ----------------
TELEGRAM_TOKEN = "8601674578:AAHycLEx-6M_r_JHFuS96oKuLTBJqefwKnk"  # Hardcoded


# Optional: Print to confirm
print(f"Using token: {TELEGRAM_TOKEN[:10]}...")  # Shows first 10 chars

# Rest of your code continues...
CHAT_ID = "992623579"

# Check if token exists
if not TELEGRAM_TOKEN:
    print("❌ CRITICAL ERROR: TELEGRAM_TOKEN environment variable not set!")
    print("Please add it in Railway dashboard: Variables tab → Add TELEGRAM_TOKEN")
    exit(1)

print(f"✅ Token loaded successfully (length: {len(TELEGRAM_TOKEN)})")

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
application = None 
bot_running = True

# ---------------- TELEGRAM ----------------
async def send_telegram(msg, chat_id=CHAT_ID):
    global application
    if application:
        try:
            await application.bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")
        except Exception as e:
            print(f"Telegram send error: {e}")
    else:
        try:
            url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
            requests.post(url, data={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"})
        except Exception as e:
            print(f"Telegram fallback send error: {e}")

# ---------------- INDICATORS ----------------
def calculate_indicators(df):
    try:
        tr = pd.concat([
            df["high"] - df["low"],
            abs(df["high"] - df["close"].shift()),
            abs(df["low"] - df["close"].shift())
        ], axis=1).max(axis=1)
        df["atr"] = tr.rolling(ATR_PERIOD).mean()
        df["ema_fast"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
        df["ema_slow"] = df["close"].ewm(span=EMA_SLOW, adjust=False).mean()
        delta = df["close"].diff()
        gain = (delta.where(delta > 0, 0)).ewm(span=RSI_PERIOD, adjust=False).mean()
        loss = (-delta.where(delta < 0, 0)).ewm(span=RSI_PERIOD, adjust=False).mean()
        rs = gain / loss
        df["rsi"] = 100 - (100 / (1 + rs))
    except Exception as e:
        print(f"Indicator calculation error: {e}")
    return df

# ---------------- SIGNAL ENGINE ----------------
def generate_signal_message(symbol, direction, price, sl, tp):
    return (
        f"<b>{symbol} {direction} NOW</b> 🔥\n\n"
        f"» POINT      : {price:.2f}\n"
        f"» STOPLOSS   : {sl:.2f}\n"
        f"» TAKE PROFIT : OPEN\n\n"
        f"<i>PLEASE ENSURE PROPER MONEY MANAGEMENT</i> ‼️\n"
        f"#168FX"
    )

async def check_signal(symbol, df, chat_id=CHAT_ID):
    global last_signal_time
    if len(df) < 30: 
        return
    
    try:
        row = df.iloc[-1]
        prev_row = df.iloc[-2]
        price = row["close"]
        atr_val = row["atr"]
        rsi_val = row["rsi"]
        ema_f = row["ema_fast"]
        ema_s = row["ema_slow"]
        
        direction = None
        if ema_f > ema_s and prev_row["ema_fast"] <= prev_row["ema_slow"] and rsi_val < 65:
            direction = "BUY"
        elif ema_f < ema_s and prev_row["ema_fast"] >= prev_row["ema_slow"] and rsi_val > 35:
            direction = "SELL"
            
        if direction:
            if time.time() - last_signal_time[symbol] < 300:
                return
            if direction == "BUY":
                sl = price - (1.5 * atr_val)
            else:
                sl = price + (1.5 * atr_val)
                
            msg = generate_signal_message(symbol, direction, price, sl, "OPEN")
            await send_telegram(msg, chat_id)
            last_signal_time[symbol] = time.time()
    except Exception as e:
        print(f"Signal check error: {e}")

# ---------------- DATA FETCHING ----------------
async def fetch_gold_price_loop():
    global bot_running
    while bot_running:
        try:
            url = "https://api.gold-api.com/price/XAU/USD"
            res = requests.get(url).json()
            if "price" in res:
                price = float(res["price"])
                current_time = datetime.now(pytz.UTC)
                klines["XAUUSD"].append({
                    "close": price, 
                    "high": price, 
                    "low": price, 
                    "open": price,
                    "timestamp": current_time.timestamp()
                })
                if len(klines["XAUUSD"]) > 100: 
                    klines["XAUUSD"].pop(0)
                
                if len(klines["XAUUSD"]) >= ATR_PERIOD + 10:
                    df = pd.DataFrame(klines["XAUUSD"])
                    df = calculate_indicators(df)
                    await check_signal("XAUUSD", df)
            await asyncio.sleep(60)
        except Exception as e:
            print(f"Gold fetch error: {e}")
            await asyncio.sleep(60)

def on_btc_message(ws, message):
    try:
        data = json.loads(message)
        if "k" in data:
            k = data["k"]
            if k["x"]:  # Only process closed candles
                klines["BTCUSD"].append({
                    "open": float(k["o"]), 
                    "high": float(k["h"]),
                    "low": float(k["l"]), 
                    "close": float(k["c"]), 
                    "volume": float(k["v"])
                })
                if len(klines["BTCUSD"]) > 100: 
                    klines["BTCUSD"].pop(0)
                
                if len(klines["BTCUSD"]) >= ATR_PERIOD + 10:
                    df = pd.DataFrame(klines["BTCUSD"])
                    df = calculate_indicators(df)
                    # Create new event loop for async
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(check_signal("BTCUSD", df))
                    loop.close()
    except Exception as e:
        print(f"BTC message error: {e}")

def run_btc_ws():
    ws_url = "wss://fstream.binance.com/ws/btcusdt@kline_1m"
    ws = websocket.WebSocketApp(ws_url, on_message=on_btc_message)
    ws.run_forever()

# ---------------- COMMAND HANDLERS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_html("✅ ROYAL M1 SCALPER ONLINE\n\nUse /price to see current prices\nUse /status to check bot status")

async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_html("✅ Bot is active and responding!")

async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    xau_price = klines["XAUUSD"][-1]["close"] if klines["XAUUSD"] else "N/A"
    btc_price = klines["BTCUSD"][-1]["close"] if klines["BTCUSD"] else "N/A"
    msg = f"<b>CURRENT PRICES</b>\n\n» XAUUSD : {xau_price}\n» BTCUSD : {btc_price}"
    await update.message.reply_html(msg)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    xau_data = len(klines["XAUUSD"])
    btc_data = len(klines["BTCUSD"])
    msg = f"<b>BOT STATUS</b>\n\n» XAUUSD Data Points: {xau_data}\n» BTCUSD Data Points: {btc_data}\n» Bot is running normally"
    await update.message.reply_html(msg)

# ---------------- MAIN ----------------
async def main():
    global application
    print("Starting ROYAL M1 SCALPER...")
    
    # Build application
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("test", test_command))
    application.add_handler(CommandHandler("price", price_command))
    application.add_handler(CommandHandler("status", status_command))

    # Start polling in a separate thread
    await application.initialize()
    await application.start()
    
    # Start update polling
    asyncio.create_task(application.updater.start_polling())
    
    print("Bot started successfully!")
    await send_telegram("✅ ROYAL M1 SCALPER ONLINE - REAL-TIME MODE")
    
    # Start BTC WebSocket in thread
    btc_thread = threading.Thread(target=run_btc_ws, daemon=True)
    btc_thread.start()
    
    # Start gold price fetching
    await fetch_gold_price_loop()

if __name__ == "__main__":
    # Run the main function
    asyncio.run(main())
