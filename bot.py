# ⚡ ROYAL FAST M1 SCALPER (XAUUSD & BTCUSD) - V3
# 🎯 WITH TP/SL TRACKING AND SIGNAL MANAGEMENT
# ⚡ FASTER SIGNALS - Only 15 candles needed

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
import signal
import sys
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ---------------- CONFIG ----------------
TELEGRAM_TOKEN = "8601674578:AAHycLEx-6M_r_JHFuS96oKuLTBJqefwKnk"
CHAT_ID = "992623579"

# MT5 Price Offset (adjust these to match your broker)
MT5_OFFSET = {
    "XAUUSD": 0.20,
    "BTCUSD": 0.20
}

# Scalping Parameters
ATR_PERIOD = 14
EMA_FAST = 9
EMA_SLOW = 21
RSI_PERIOD = 7
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30
ADX_PERIOD = 14
ADX_THRESHOLD = 25 # Only trade when trend is strong
VOLUME_THRESHOLD_MULTIPLIER = 1.5 # Volume must be 1.5x average for confirmation

# New: Fixed SL/TP in pips
SL_PIPS = {
    "XAUUSD": 25,  # 25 pips for XAUUSD
    "BTCUSD": 25   # 25 pips for BTCUSD
}
TP_PIPS = {
    "XAUUSD": 50,  # 50 pips for XAUUSD
    "BTCUSD": 50   # 50 pips for BTCUSD
}

# Pip value for calculations
PIP_VALUE = {
    "XAUUSD": 0.1, # 1 pip = $0.1 for XAUUSD
    "BTCUSD": 1.0  # 1 pip = $1.0 for BTCUSD
}

# Trading Hours (UTC)
TRADING_START_HOUR = 6
TRADING_END_HOUR = 22

# Data Storage
klines = {"BTCUSD": [], "XAUUSD": []}
last_signal_time = {"BTCUSD": 0, "XAUUSD": 0}
bot_running = True

# Track active signals for TP/SL monitoring
active_signals = {
    "XAUUSD": None,
    "BTCUSD": None
}

# Global bot instance and event loop
application = None 
main_loop = None

# ---------------- GRACEFUL SHUTDOWN ----------------
def handle_shutdown(signum, frame):
    global bot_running, application, main_loop
    print("🛑 Received shutdown signal, stopping bot...")
    bot_running = False
    if application and main_loop:
        try:
            # Schedule the stop in the main loop
            main_loop.call_soon_threadsafe(lambda: asyncio.create_task(application.stop()))
        except:
            pass
    sys.exit(0)

signal.signal(signal.SIGINT, handle_shutdown)
signal.signal(signal.SIGTERM, handle_shutdown)

# ---------------- PRICE FETCHING ----------------
async def fetch_price(symbol):
    """Fetch current price from reliable source"""
    try:
        if symbol == "XAUUSD":
            url = "https://api.gold-api.com/price/XAU/USD"
            res = requests.get(url, timeout=5).json()
            if "price" in res:
                price = float(res["price"])
                price += MT5_OFFSET.get("XAUUSD", 0)
                return price
            return None
            
        elif symbol == "BTCUSD":
            url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
            res = requests.get(url, timeout=5).json()
            price = float(res["price"])
            price += MT5_OFFSET.get("BTCUSD", 0)
            return price
    except Exception as e:
        print(f"Error fetching {symbol}: {e}")
        return None

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
            requests.post(url, data={"chat_id": chat_id, "text": msg, "parse_mode": "HTML"}, timeout=5)
        except Exception as e:
            print(f"Telegram fallback send error: {e}")

# ---------------- INDICATORS ----------------
def calculate_indicators(df):
    try:
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
        
        # ADX (Simple version)
        df["dm_plus"] = df["high"].diff().apply(lambda x: x if x > 0 else 0)
        df["dm_minus"] = -df["low"].diff().apply(lambda x: x if x < 0 else 0)
        df["plus_di"] = 100 * (df["dm_plus"].ewm(span=ADX_PERIOD, adjust=False).mean() / df["atr"])
        df["minus_di"] = 100 * (df["dm_minus"].ewm(span=ADX_PERIOD, adjust=False).mean() / df["atr"])
        df["dx"] = 100 * abs(df["plus_di"] - df["minus_di"]) / (df["plus_di"] + df["minus_di"])
        df["adx"] = df["dx"].ewm(span=ADX_PERIOD, adjust=False).mean()

        if "volume" in df.columns:
            df["avg_volume"] = df["volume"].rolling(ADX_PERIOD).mean()
        
    except Exception as e:
        print(f"Indicator calculation error: {e}")
    return df

# ---------------- SIGNAL ENGINE ----------------
def generate_signal_message(symbol, direction, price, sl, tp):
    """Generate signal message in exact format you requested"""
    if symbol == "XAUUSD":
        price_format = ".2f"
        symbol_name = "GOLD / XAUUSD"
    else: # BTCUSD
        price_format = ".0f"
        symbol_name = "BTCUSD"

    return (
        f"<b>{symbol_name} {direction} NOW</b>\n"
        f"LIVE 🔥\n\n"
        f"- POINT : {price:{price_format}}\n"
        f"- STOPLOSS : {sl:{price_format}}\n"
        f"- TAKE PROFIT : {tp:{price_format}}\n\n"
        f"PLEASE ENSURE PROPER MONEY MANAGEMENT !!!\n\n"
        f"#168FX"
    )

def generate_tp_hit_message(symbol, direction, entry_price, tp_price):
    """Generate TP hit message"""
    price_format = ".2f" if symbol == "XAUUSD" else ".0f"
    profit = abs(tp_price - entry_price)
    return (
        f"✅ <b>{symbol} TAKE PROFIT HIT!</b> ✅\n\n"
        f"Direction: {direction}\n"
        f"Entry: {entry_price:{price_format}}\n"
        f"TP Hit: {tp_price:{price_format}}\n"
        f"Profit: +{profit:{price_format}} points\n\n"
        f"#168FX #PROFIT"
    )

def generate_sl_hit_message(symbol, direction, entry_price, sl_price):
    """Generate SL hit message"""
    price_format = ".2f" if symbol == "XAUUSD" else ".0f"
    loss = abs(sl_price - entry_price)
    return (
        f"❌ <b>{symbol} STOPLOSS HIT!</b> ❌\n\n"
        f"Direction: {direction}\n"
        f"Entry: {entry_price:{price_format}}\n"
        f"SL Hit: {sl_price:{price_format}}\n"
        f"Loss: -{loss:{price_format}} points\n\n"
        f"#168FX #STOPLOSS"
    )

async def check_signal(symbol, df, chat_id=CHAT_ID):
    global last_signal_time, active_signals
    if len(df) < max(ATR_PERIOD, EMA_SLOW, RSI_PERIOD, ADX_PERIOD) + 1: 
        return
    
    try:
        row = df.iloc[-1]
        prev_row = df.iloc[-2]
        price = row["close"]
        rsi_val = row["rsi"]
        ema_f = row["ema_fast"]
        ema_s = row["ema_slow"]
        adx_val = row["adx"]
        
        direction = None
        ema_cross_buy = ema_f > ema_s and prev_row["ema_fast"] <= prev_row["ema_slow"]
        ema_cross_sell = ema_f < ema_s and prev_row["ema_fast"] >= prev_row["ema_slow"]
        rsi_confirm_buy = 45 < rsi_val < 65
        rsi_confirm_sell = 35 < rsi_val < 55
        adx_confirm = adx_val > ADX_THRESHOLD

        volume_confirm = True
        if symbol == "BTCUSD" and "volume" in df.columns and "avg_volume" in df.columns:
            if not df["avg_volume"].empty and df.iloc[-1]["volume"] > (df.iloc[-1]["avg_volume"] * VOLUME_THRESHOLD_MULTIPLIER):
                volume_confirm = True
            else:
                volume_confirm = False
        
        if ema_cross_buy and rsi_confirm_buy and adx_confirm and volume_confirm:
            direction = "BUY"
        elif ema_cross_sell and rsi_confirm_sell and adx_confirm and volume_confirm:
            direction = "SELL"
            
        if direction:
            if time.time() - last_signal_time[symbol] < 300:
                return
            
            sl_amount = SL_PIPS[symbol] * PIP_VALUE[symbol]
            tp_amount = TP_PIPS[symbol] * PIP_VALUE[symbol]

            if direction == "BUY":
                sl = price - sl_amount
                tp = price + tp_amount
            else: # SELL
                sl = price + sl_amount
                tp = price - tp_amount
            
            msg = generate_signal_message(symbol, direction, price, sl, tp)
            await send_telegram(msg, chat_id)
            
            active_signals[symbol] = {
                "direction": direction,
                "entry_price": price,
                "sl": sl,
                "tp": tp,
                "timestamp": time.time(),
                "symbol": symbol
            }
            
            last_signal_time[symbol] = time.time()
            print(f"📊 New {symbol} {direction} signal at {price:.2f}, SL: {sl:.2f}, TP: {tp:.2f}")
            
    except Exception as e:
        print(f"Signal check error: {e}")

async def monitor_tp_sl():
    """Monitor active signals for TP/SL hits"""
    global active_signals
    while bot_running:
        try:
            for symbol, signal in list(active_signals.items()):
                if signal is None:
                    continue
                current_price = await fetch_price(symbol)
                if current_price is None:
                    continue
                entry = signal["entry_price"]
                sl = signal["sl"]
                tp = signal["tp"]
                direction = signal["direction"]
                if direction == "BUY":
                    if current_price >= tp:
                        msg = generate_tp_hit_message(symbol, direction, entry, tp)
                        await send_telegram(msg)
                        active_signals[symbol] = None
                    elif current_price <= sl:
                        msg = generate_sl_hit_message(symbol, direction, entry, sl)
                        await send_telegram(msg)
                        active_signals[symbol] = None
                else:  # SELL
                    if current_price <= tp:
                        msg = generate_tp_hit_message(symbol, direction, entry, tp)
                        await send_telegram(msg)
                        active_signals[symbol] = None
                    elif current_price >= sl:
                        msg = generate_sl_hit_message(symbol, direction, entry, sl)
                        await send_telegram(msg)
                        active_signals[symbol] = None
                if time.time() - signal["timestamp"] > 86400:
                    active_signals[symbol] = None
            await asyncio.sleep(5)
        except Exception as e:
            print(f"TP/SL monitor error: {e}")
            await asyncio.sleep(5)

async def get_latest_signal(symbol, df):
    """Get the latest signal without sending to Telegram"""
    if len(df) < max(ATR_PERIOD, EMA_SLOW, RSI_PERIOD, ADX_PERIOD) + 1:
        return None
    try:
        row = df.iloc[-1]
        prev_row = df.iloc[-2]
        price = row["close"]
        rsi_val = row["rsi"]
        ema_f = row["ema_fast"]
        ema_s = row["ema_slow"]
        adx_val = row["adx"]
        direction = None
        ema_cross_buy = ema_f > ema_s and prev_row["ema_fast"] <= prev_row["ema_slow"]
        ema_cross_sell = ema_f < ema_s and prev_row["ema_fast"] >= prev_row["ema_slow"]
        rsi_confirm_buy = 45 < rsi_val < 65
        rsi_confirm_sell = 35 < rsi_val < 55
        adx_confirm = adx_val > ADX_THRESHOLD
        volume_confirm = True
        if symbol == "BTCUSD" and "volume" in df.columns and "avg_volume" in df.columns:
            if not df["avg_volume"].empty and df.iloc[-1]["volume"] > (df.iloc[-1]["avg_volume"] * VOLUME_THRESHOLD_MULTIPLIER):
                volume_confirm = True
            else:
                volume_confirm = False
        if ema_cross_buy and rsi_confirm_buy and adx_confirm and volume_confirm:
            direction = "BUY"
        elif ema_cross_sell and rsi_confirm_sell and adx_confirm and volume_confirm:
            direction = "SELL"
        if direction:
            sl_amount = SL_PIPS[symbol] * PIP_VALUE[symbol]
            tp_amount = TP_PIPS[symbol] * PIP_VALUE[symbol]
            sl = price - sl_amount if direction == "BUY" else price + sl_amount
            tp = price + tp_amount if direction == "BUY" else price - tp_amount
            return generate_signal_message(symbol, direction, price, sl, tp)
        return None
    except Exception as e:
        print(f"Signal generation error: {e}")
        return None

# ---------------- DATA FETCHING ----------------
async def fetch_gold_price_loop():
    global bot_running
    while bot_running:
        try:
            price = await fetch_price("XAUUSD")
            if price:
                current_time = datetime.now(pytz.UTC)
                klines["XAUUSD"].append({
                    "close": price, "high": price, "low": price, "open": price,
                    "timestamp": current_time.timestamp(), "volume": 0
                })
                if len(klines["XAUUSD"]) > 100: klines["XAUUSD"].pop(0)
                if len(klines["XAUUSD"]) >= max(ATR_PERIOD, EMA_SLOW, RSI_PERIOD, ADX_PERIOD) + 1:
                    df = pd.DataFrame(klines["XAUUSD"])
                    df = calculate_indicators(df)
                    await check_signal("XAUUSD", df)
            await asyncio.sleep(60)
        except Exception as e:
            print(f"Gold fetch error: {e}")
            await asyncio.sleep(60)

def on_btc_message(ws, message):
    global main_loop
    try:
        data = json.loads(message)
        if "k" in data and data["k"]["x"]:
            k = data["k"]
            price = float(k["c"]) + MT5_OFFSET.get("BTCUSD", 0)
            klines["BTCUSD"].append({
                "open": float(k["o"]) + MT5_OFFSET.get("BTCUSD", 0), 
                "high": float(k["h"]) + MT5_OFFSET.get("BTCUSD", 0),
                "low": float(k["l"]) + MT5_OFFSET.get("BTCUSD", 0), 
                "close": price, "volume": float(k["v"]), "timestamp": time.time()
            })
            if len(klines["BTCUSD"]) > 100: klines["BTCUSD"].pop(0)
            if len(klines["BTCUSD"]) >= max(ATR_PERIOD, EMA_SLOW, RSI_PERIOD, ADX_PERIOD) + 1:
                df = pd.DataFrame(klines["BTCUSD"])
                df = calculate_indicators(df)
                # Safely run the async check_signal in the main loop from the thread
                if main_loop:
                    main_loop.call_soon_threadsafe(lambda: asyncio.create_task(check_signal("BTCUSD", df)))
    except Exception as e:
        print(f"BTC message error: {e}")

def run_btc_ws():
    while bot_running:
        try:
            ws_url = "wss://fstream.binance.com/ws/btcusdt@kline_1m"
            ws = websocket.WebSocketApp(ws_url, on_message=on_btc_message)
            ws.run_forever()
        except Exception as e:
            print(f"BTC WebSocket error: {e}, reconnecting in 5 seconds...")
            time.sleep(5)

# ---------------- COMMAND HANDLERS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_html("✅ <b>ROYAL M1 SCALPER ONLINE</b>\n\n/price | /signal | /status | /active | /help")

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_html("<b>🤖 BOT COMMANDS</b>\n\n/start | /price | /signal | /status | /active | /help")

async def active_signals_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    global active_signals
    msg = "<b>📋 ACTIVE SIGNALS</b>\n\n"
    has_active = False
    for symbol, signal in list(active_signals.items()):
        if signal:
            has_active = True
            price_format = ".2f" if symbol == "XAUUSD" else ".0f"
            msg += f"<b>{symbol}</b>: {signal['direction']} @ {signal['entry_price']:{price_format}}\nSL: {signal['sl']:{price_format}} | TP: {signal['tp']:{price_format}}\n\n"
    if not has_active: msg += "No active signals."
    await update.message.reply_html(msg)

async def signal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_html("<b>🎯 FETCHING LATEST SIGNALS...</b>")
    messages = []
    for symbol in ["XAUUSD", "BTCUSD"]:
        if len(klines[symbol]) >= max(ATR_PERIOD, EMA_SLOW, RSI_PERIOD, ADX_PERIOD) + 1:
            df = pd.DataFrame(klines[symbol])
            df = calculate_indicators(df)
            signal_msg = await get_latest_signal(symbol, df)
            messages.append(signal_msg if signal_msg else f"<b>{symbol}</b>: No Signal")
        else:
            messages.append(f"🟡 {symbol}: Waiting for data...")
    await update.message.reply_html("\n\n".join(messages))

async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    xau = await fetch_price("XAUUSD")
    btc = await fetch_price("BTCUSD")
    msg = f"<b>💰 PRICES</b>\n\nXAUUSD: ${xau:.2f}\nBTCUSD: ${btc:.0f}"
    await update.message.reply_html(msg)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    msg = f"<b>🤖 BOT STATUS: RUNNING</b>\n\n"
    for symbol in ["XAUUSD", "BTCUSD"]:
        data_len = len(klines[symbol])
        msg += f"📊 {symbol}: {data_len} candles\n"
    await update.message.reply_html(msg)

# ---------------- MAIN ----------------
async def main():
    global application, bot_running, main_loop
    main_loop = asyncio.get_running_loop()
    print("🚀 Starting ROYAL M1 SCALPER V3...")
    
    try:
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook", timeout=5)
        requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset=-1&limit=1", timeout=5)
    except: pass
    
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("price", price_command))
    application.add_handler(CommandHandler("signal", signal_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("active", active_signals_command))

    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    
    print("✅ Bot started successfully!")
    await send_telegram("✅ ROYAL M1 SCALPER V3 ONLINE")
    
    asyncio.create_task(monitor_tp_sl())
    threading.Thread(target=run_btc_ws, daemon=True).start()
    await fetch_gold_price_loop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Bot stopped")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
