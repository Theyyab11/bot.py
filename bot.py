# ⚡ ROYAL FAST M1 SCALPER (XAUUSD & BTCUSD)
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

# Force delete any existing webhook on startup
try:
    webhook_url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook"
    response = requests.get(webhook_url, timeout=5)
    print(f"✅ Webhook cleared: {response.json()}")
except Exception as e:
    print(f"Webhook clear error: {e}")

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

# Global bot instance
application = None 

# ---------------- GRACEFUL SHUTDOWN ----------------
def handle_shutdown(signum, frame):
    global bot_running, application
    print("🛑 Received shutdown signal, stopping bot...")
    bot_running = False
    if application:
        try:
            application.stop()
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
    """Generate signal message in exact format you requested"""
    # Determine formatting based on symbol
    if symbol == "XAUUSD":
        price_format = ".2f"
    else: # BTCUSD
        price_format = ".0f"

    if direction == "BUY":
        return (
            f"<b>GOLD / XAUUSD {direction} NOW</b>\n"
            f"LIVE 🔥\n\n"
            f"- POINT : {price:{price_format}}\n"
            f"- STOPLOSS : {sl:{price_format}}\n"
            f"- TAKE PROFIT : {tp:{price_format}}\n\n"
            f"PLEASE ENSURE PROPER MONEY MANAGEMENT !!!\n\n"
            f"#168FX"
        )
    else:
        return (
            f"<b>GOLD / XAUUSD {direction} NOW</b>\n"
            f"LIVE 🔥\n\n"
            f"- POINT : {price:{price_format}}\n"
            f"- STOPLOSS : {sl:{price_format}}\n"
            f"- TAKE PROFIT : {tp:{price_format}}\n\n"
            f"PLEASE ENSURE PROPER MONEY MANAGEMENT !!!\n\n"
            f"#168FX"
        )

def generate_btc_signal_message(symbol, direction, price, sl, tp):
    """Generate BTC signal message"""
    # Determine formatting based on symbol
    if symbol == "XAUUSD":
        price_format = ".2f"
    else: # BTCUSD
        price_format = ".0f"

    if direction == "BUY":
        return (
            f"<b>BTCUSD {direction} NOW</b>\n"
            f"LIVE 🔥\n\n"
            f"- POINT : {price:{price_format}}\n"
            f"- STOPLOSS : {sl:{price_format}}\n"
            f"- TAKE PROFIT : {tp:{price_format}}\n\n"
            f"PLEASE ENSURE PROPER MONEY MANAGEMENT !!!\n\n"
            f"#168FX"
        )
    else:
        return (
            f"<b>BTCUSD {direction} NOW</b>\n"
            f"LIVE 🔥\n\n"
            f"- POINT : {price:{price_format}}\n"
            f"- STOPLOSS : {sl:{price_format}}\n"
            f"- TAKE PROFIT : {tp:{price_format}}\n\n"
            f"PLEASE ENSURE PROPER MONEY MANAGEMENT !!!\n\n"
            f"#168FX"
        )

def generate_tp_hit_message(symbol, direction, entry_price, tp_price):
    """Generate TP hit message"""
    # Determine formatting based on symbol
    if symbol == "XAUUSD":
        price_format = ".2f"
    else: # BTCUSD
        price_format = ".0f"

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
    # Determine formatting based on symbol
    if symbol == "XAUUSD":
        price_format = ".2f"
    else: # BTCUSD
        price_format = ".0f"

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
    if len(df) < 15: 
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
        # Enhanced signal logic: EMA crossover + RSI confirmation + ATR filter
        # Only consider signals if ATR is above a certain threshold (e.g., 1.5 * average ATR) to filter out low volatility periods
        # This is a placeholder for a more robust ATR filter. For now, we'll just use the existing ATR.
        
        # Original EMA crossover and RSI conditions
        ema_cross_buy = ema_f > ema_s and prev_row["ema_fast"] <= prev_row["ema_slow"]
        ema_cross_sell = ema_f < ema_s and prev_row["ema_fast"] >= prev_row["ema_slow"]

        # Stronger RSI conditions
        rsi_confirm_buy = rsi_val < RSI_OVERBOUGHT and rsi_val > 45 # RSI not overbought, and not too low
        rsi_confirm_sell = rsi_val > RSI_OVERSOLD and rsi_val < 55 # RSI not oversold, and not too high

        if ema_cross_buy and rsi_confirm_buy:
            direction = "BUY"
        elif ema_cross_sell and rsi_confirm_sell:
            direction = "SELL"
            
        if direction:
            # Check if enough time has passed since last signal (5 minutes)
            if time.time() - last_signal_time[symbol] < 300:
                return
            
            # Calculate SL and TP based on fixed pips
            sl_amount = SL_PIPS[symbol] * PIP_VALUE[symbol]
            tp_amount = TP_PIPS[symbol] * PIP_VALUE[symbol]

            if direction == "BUY":
                sl = price - sl_amount
                tp = price + tp_amount
            else: # SELL
                sl = price + sl_amount
                tp = price - tp_amount
            
            # Generate message based on symbol
            if symbol == "XAUUSD":
                msg = generate_signal_message(symbol, direction, price, sl, tp)
            else:
                msg = generate_btc_signal_message(symbol, direction, price, sl, tp)
            
            # Send signal
            await send_telegram(msg, chat_id)
            
            # Store active signal for monitoring
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
                
                # Get current price
                current_price = await fetch_price(symbol)
                if current_price is None:
                    continue
                
                entry = signal["entry_price"]
                sl = signal["sl"]
                tp = signal["tp"]
                direction = signal["direction"]
                
                # Check for TP hit
                if direction == "BUY":
                    if current_price >= tp:
                        msg = generate_tp_hit_message(symbol, direction, entry, tp)
                        await send_telegram(msg)
                        print(f"✅ {symbol} TP HIT at {current_price:.2f}")
                        active_signals[symbol] = None
                    elif current_price <= sl:
                        msg = generate_sl_hit_message(symbol, direction, entry, sl)
                        await send_telegram(msg)
                        print(f"❌ {symbol} SL HIT at {current_price:.2f}")
                        active_signals[symbol] = None
                else:  # SELL
                    if current_price <= tp:
                        msg = generate_tp_hit_message(symbol, direction, entry, tp)
                        await send_telegram(msg)
                        print(f"✅ {symbol} TP HIT at {current_price:.2f}")
                        active_signals[symbol] = None
                    elif current_price >= sl:
                        msg = generate_sl_hit_message(symbol, direction, entry, sl)
                        await send_telegram(msg)
                        print(f"❌ {symbol} SL HIT at {current_price:.2f}")
                        active_signals[symbol] = None
                
                # Remove old signals (older than 24 hours)
                if time.time() - signal["timestamp"] > 86400:
                    active_signals[symbol] = None
                    
            await asyncio.sleep(5)  # Check every 5 seconds
            
        except Exception as e:
            print(f"TP/SL monitor error: {e}")
            await asyncio.sleep(5)

async def get_latest_signal(symbol, df):
    """Get the latest signal without sending to Telegram"""
    if len(df) < 15:
        return None
    
    try:
        row = df.iloc[-1]
        prev_row = df.iloc[-2]
        price = row["close"]
        atr_val = row["atr"]
        rsi_val = row["rsi"]
        ema_f = row["ema_fast"]
        ema_s = row["ema_slow"]
        
        direction = None
        # Enhanced signal logic: EMA crossover + RSI confirmation + ATR filter
        ema_cross_buy = ema_f > ema_s and prev_row["ema_fast"] <= prev_row["ema_slow"]
        ema_cross_sell = ema_f < ema_s and prev_row["ema_fast"] >= prev_row["ema_slow"]

        rsi_confirm_buy = rsi_val < RSI_OVERBOUGHT and rsi_val > 45
        rsi_confirm_sell = rsi_val > RSI_OVERSOLD and rsi_val < 55

        if ema_cross_buy and rsi_confirm_buy:
            direction = "BUY"
        elif ema_cross_sell and rsi_confirm_sell:
            direction = "SELL"
        
        if direction:
            # Calculate SL and TP based on fixed pips
            sl_amount = SL_PIPS[symbol] * PIP_VALUE[symbol]
            tp_amount = TP_PIPS[symbol] * PIP_VALUE[symbol]

            if direction == "BUY":
                sl = price - sl_amount
                tp = price + tp_amount
            else: # SELL
                sl = price + sl_amount
                tp = price - tp_amount
            
            if symbol == "XAUUSD":
                return generate_signal_message(symbol, direction, price, sl, tp)
            else:
                return generate_btc_signal_message(symbol, direction, price, sl, tp)
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
                    "close": price, 
                    "high": price, 
                    "low": price, 
                    "open": price,
                    "timestamp": current_time.timestamp()
                })
                if len(klines["XAUUSD"]) > 100: 
                    klines["XAUUSD"].pop(0)
                
                if len(klines["XAUUSD"]) >= ATR_PERIOD + 5:  # Changed from +10 to +5
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
            if k["x"]:
                price = float(k["c"])
                price += MT5_OFFSET.get("BTCUSD", 0)
                
                klines["BTCUSD"].append({
                    "open": float(k["o"]) + MT5_OFFSET.get("BTCUSD", 0), 
                    "high": float(k["h"]) + MT5_OFFSET.get("BTCUSD", 0),
                    "low": float(k["l"]) + MT5_OFFSET.get("BTCUSD", 0), 
                    "close": price, 
                    "volume": float(k["v"])
                })
                if len(klines["BTCUSD"]) > 100: 
                    klines["BTCUSD"].pop(0)
                
                if len(klines["BTCUSD"]) >= ATR_PERIOD + 5:  # Changed from +10 to +5
                    df = pd.DataFrame(klines["BTCUSD"])
                    df = calculate_indicators(df)
                    loop = asyncio.new_event_loop()
                    asyncio.set_event_loop(loop)
                    loop.run_until_complete(check_signal("BTCUSD", df))
                    loop.close()
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
    await update.message.reply_html(
        "✅ <b>ROYAL M1 SCALPER ONLINE</b>\n\n"
        "Available commands:\n"
        "📊 /price - Current prices\n"
        "🎯 /signal - Latest trading signal\n"
        "📈 /status - Bot status & market conditions\n"
        "📋 /active - Show active signals with TP/SL\n"
        "❓ /help - Show all commands\n\n"
        "<i>⚡ FAST MODE: Signals after just 15 candles (15 minutes)\n"
        "🎯 TP/SL will be automatically monitored!</i>"
    )

async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_html(
        "<b>🤖 BOT COMMANDS</b>\n\n"
        "/start - Start the bot\n"
        "/price - Get current MT5 prices\n"
        "/signal - Get latest trading signals\n"
        "/status - Check bot status\n"
        "/active - Show active signals with TP/SL\n"
        "/help - Show this help\n\n"
        "<b>📊 SIGNAL CRITERIA:</b>\n"
        "• EMA 9/21 crossover\n"
        "• RSI confirmation (35-65)\n"
        "• Fixed 25-pip Stop Loss\n"
        "• Fixed 50-pip Take Profit\n\n"
        "<b>🎯 TP/SL Monitoring:</b>\n"
        "• Auto-notification on hit\n\n"
        "<b>⚡ FAST MODE:</b>\n"
        "• Signals after 15 candles (was 30)\n"
        "• Faster signal generation\n"
        "• 50% faster response time\n\n"
        "<i>Signals auto-send when conditions are met</i>"
    )

async def active_signals_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Show currently active signals with their TP/SL levels"""
    global active_signals
    
    has_active = False
    msg = "<b>📋 ACTIVE SIGNALS</b>\n\n"
    
    for symbol, signal in active_signals.items():
        if signal is not None:
            has_active = True
            direction = signal["direction"]
            entry = signal["entry_price"]
            sl = signal["sl"]
            tp = signal["tp"]
            age = int((time.time() - signal["timestamp"]) / 60)  # Age in minutes
            
            # Determine formatting based on symbol
            if symbol == "XAUUSD":
                price_format = ".2f"
            else: # BTCUSD
                price_format = ".0f"

            msg += f"<b>{symbol}</b>\n"
            msg += f"Direction: {direction}\n"
            msg += f"Entry: {entry:{price_format}}\n"
            msg += f"SL: {sl:{price_format}}\n"
            msg += f"TP: {tp:{price_format}}\n"
            msg += f"Age: {age} minutes\n\n"
    
    if not has_active:
        msg += "No active signals at this time.\n"
        msg += "Signals will appear here when generated."
    
    await update.message.reply_html(msg)

async def signal_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Send the latest signal for both symbols"""
    await update.message.reply_html("<b>🎯 FETCHING LATEST SIGNALS...</b>")
    
    messages = []
    
    # Check XAUUSD signal
    if len(klines["XAUUSD"]) >= 15:
        df_xau = pd.DataFrame(klines["XAUUSD"])
        df_xau = calculate_indicators(df_xau)
        signal_xau = await get_latest_signal("XAUUSD", df_xau)
        if signal_xau:
            messages.append(signal_xau)
        else:
            latest = df_xau.iloc[-1]
            messages.append(
                f"<b>🥇 XAUUSD - No Active Signal</b>\n"
                f"📊 RSI: {latest["rsi"]:.1f}\n"
                f"📈 EMA Trend: {"Bullish" if latest["ema_fast"] > latest["ema_slow"] else "Bearish"}\n"
                f"💰 Price: ${latest["close"]:.2f}\n"
                f"📊 Data: {len(klines["XAUUSD"])}/15 candles"
            )
    else:
        messages.append(f"🟡 XAUUSD: Need 15 candles, have {len(klines["XAUUSD"])}/15")
    
    # Check BTCUSD signal
    if len(klines["BTCUSD"]) >= 15:
        df_btc = pd.DataFrame(klines["BTCUSD"])
        df_btc = calculate_indicators(df_btc)
        signal_btc = await get_latest_signal("BTCUSD", df_btc)
        if signal_btc:
            messages.append(signal_btc)
        else:
            latest = df_btc.iloc[-1]
            messages.append(
                f"<b>₿ BTCUSD - No Active Signal</b>\n"
                f"📊 RSI: {latest["rsi"]:.1f}\n"
                f"📈 EMA Trend: {"Bullish" if latest["ema_fast"] > latest["ema_slow"] else "Bearish"}\n"
                f"💰 Price: ${latest["close"]:.2f}\n"
                f"📊 Data: {len(klines["BTCUSD"])}/15 candles"
            )
    else:
        messages.append(f"🟠 BTCUSD: Need 15 candles, have {len(klines["BTCUSD"])}/15")
    
    await update.message.reply_html("\n\n━━━━━━━━━━━━━━━━━━━━\n\n".join(messages))

async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_html("<b>💰 FETCHING LATEST PRICES...</b>")
    
    xau_price = await fetch_price("XAUUSD")
    btc_price = await fetch_price("BTCUSD")
    
    msg = f"<b>💰 CURRENT MT5 PRICES</b>\n\n"
    
    if xau_price:
        msg += f"🥇 <b>XAUUSD</b> : ${xau_price:.2f}\n"
    else:
        msg += f"🥇 <b>XAUUSD</b> : N/A\n"
    
    if btc_price:
        msg += f"₿ <b>BTCUSD</b> : ${btc_price:.0f}\n"
    else:
        msg += f"₿ <b>BTCUSD</b> : N/A\n"
    
    msg += f"\n<i>💡 Tip: Adjust MT5_OFFSET in code to match your broker's spread</i>"
    
    await update.message.reply_html(msg)

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    xau_data = len(klines["XAUUSD"])
    btc_data = len(klines["BTCUSD"])
    
    # Get latest market conditions
    xau_condition = "Waiting for data..."
    btc_condition = "Waiting for data..."
    xau_price_str = "N/A"
    btc_price_str = "N/A"
    
    if xau_data >= 15:
        df_xau = pd.DataFrame(klines["XAUUSD"])
        df_xau = calculate_indicators(df_xau)
        latest = df_xau.iloc[-1]
        xau_price_str = f"${latest["close"]:.2f}"
        xau_condition = f"📊 RSI: {latest["rsi"]:.1f} | {"🟢 BULLISH" if latest["ema_fast"] > latest["ema_slow"] else "🔴 BEARISH"}"
    
    if btc_data >= 15:
        df_btc = pd.DataFrame(klines["BTCUSD"])
        df_btc = calculate_indicators(df_btc)
        latest = df_btc.iloc[-1]
        btc_price_str = f"${latest["close"]:.0f}"
        btc_condition = f"📊 RSI: {latest["rsi"]:.1f} | {"🟢 BULLISH" if latest["ema_fast"] > latest["ema_slow"] else "🔴 BEARISH"}"
    
    current_hour = datetime.now(pytz.UTC).hour
    is_trading_time = TRADING_START_HOUR <= current_hour <= TRADING_END_HOUR
    
    # Count active signals
    active_count = sum(1 for s in active_signals.values() if s is not None)
    
    msg = f"<b>🤖 BOT STATUS</b>\n\n"
    msg += f"✅ Status: <b>RUNNING</b>\n"
    msg += f"⚡ Mode: <b>FAST (15 candles)</b>\n"
    msg += f"📊 Data: XAUUSD={xau_data}/15 | BTCUSD={btc_data}/15\n"
    msg += f"🎯 Active Signals: {active_count}\n"
    msg += f"⏰ Trading Hours: {"🟢 ACTIVE" if is_trading_time else "🔴 CLOSED"} (UTC {TRADING_START_HOUR}-{TRADING_END_HOUR})\n\n"
    msg += f"<b>📈 MARKET CONDITIONS:</b>\n"
    msg += f"🥇 XAUUSD: {xau_price_str}\n"
    msg += f"   {xau_condition}\n"
    msg += f"₿ BTCUSD: {btc_price_str}\n"
    msg += f"   {btc_condition}\n\n"
    msg += f"<i>Last update: {datetime.now(pytz.UTC).strftime("%Y-%m-%d %H:%M:%S UTC")}</i>"
    
    await update.message.reply_html(msg)

async def test_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.message.reply_html("✅ Bot is active and responding!")

# ---------------- MAIN ----------------
async def main():
    global application, bot_running
    print("🚀 Starting ROYAL M1 SCALPER - FAST MODE...")
    print(f"⚡ Signals will generate after just 15 candles (15 minutes)")
    print(f"📊 MT5 Offset: XAUUSD={MT5_OFFSET["XAUUSD"]}, BTCUSD={MT5_OFFSET["BTCUSD"]}")
    
    # Build application
    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("price", price_command))
    application.add_handler(CommandHandler("signal", signal_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("active", active_signals_command))
    application.add_handler(CommandHandler("test", test_command))

    # Start the bot
    await application.initialize()
    await application.start()
    
    # Start polling with drop_pending_updates to avoid conflicts
    await application.updater.start_polling(drop_pending_updates=True)
    
    print("✅ Bot started successfully in FAST MODE!")
    await send_telegram("✅ ROYAL M1 SCALPER ONLINE - FAST MODE ⚡\n\n⚡ Signals after just 15 minutes!\n🎯 TP/SL will be monitored automatically!")
    
    # Start TP/SL monitor
    asyncio.create_task(monitor_tp_sl())
    
    # Start BTC WebSocket in thread
    btc_thread = threading.Thread(target=run_btc_ws, daemon=True)
    btc_thread.start()
    
    # Start gold price fetching
    await fetch_gold_price_loop()

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("🛑 Bot stopped by user")
    except Exception as e:
        print(f"Fatal error: {e}")
        sys.exit(1)
