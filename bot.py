# 👑 ROYAL ULTIMATE SNIPER M1 SCALPER (XAUUSD & BTCUSD) - V5
# 🎯 EXNESS PRICE SYNC | 20+ PIP TPs | 35-PIP SL | LAYERING (DCA)
# 🚀 CONFLICT-PROOF STARTUP | PREDICTIVE ALERTS

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
import logging
from telegram import Update
from telegram.ext import ApplicationBuilder, CommandHandler, ContextTypes

# ---------------- LOGGING ----------------
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# ---------------- CONFIG ----------------
TELEGRAM_TOKEN = "8601674578:AAHycLEx-6M_r_JHFuS96oKuLTBJqefwKnk"
CHAT_ID = "992623579"

# 💎 EXNESS PRICE SYNC (Adjust these to match your Exness terminal exactly)
EXNESS_OFFSET = {
    "XAUUSD": 0.15,  # Add/Subtract to match Exness Gold price
    "BTCUSD": 5.00   # Add/Subtract to match Exness Bitcoin price
}

# Scalping Parameters
ATR_PERIOD = 14
EMA_FAST = 9
EMA_SLOW = 21
RSI_PERIOD = 7
ADX_PERIOD = 14
ADX_THRESHOLD = 35 # High threshold for "Ultimate Sniper"
VOLUME_THRESHOLD_MULTIPLIER = 2.5 # High volume for sniper signals

# TP/SL Strategy (in pips)
TP_LEVELS = [20, 40, 60, 80, 100] # TPs from 20 pips and above
SL_PIPS = 35 # Strict 35-pip SL

# Layering (DCA) Parameters
LAYERING_DRAWDOWN_PIPS = 15 # Add a layer if price goes 15 pips against us
MAX_LAYERS = 2 # Max 2 additional layers per signal

# Pip value for calculations
PIP_VALUE = {"XAUUSD": 0.1, "BTCUSD": 1.0}

# Data Storage
klines = {"BTCUSD": [], "XAUUSD": []}
last_signal_time = {"BTCUSD": 0, "XAUUSD": 0}
pre_signal_sent = {"BTCUSD": False, "XAUUSD": False}
bot_running = True

# Track active signals for TP/SL monitoring
active_signals = {"XAUUSD": None, "BTCUSD": None}

# Global bot instance and event loop
application = None 
main_loop = None

# ---------------- PRICE FETCHING ----------------
async def fetch_price(symbol):
    try:
        if symbol == "XAUUSD":
            url = "https://api.gold-api.com/price/XAU/USD"
            res = requests.get(url, timeout=5).json()
            if "price" in res:
                return float(res["price"]) + EXNESS_OFFSET.get("XAUUSD", 0)
        elif symbol == "BTCUSD":
            url = "https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT"
            res = requests.get(url, timeout=5).json()
            if "price" in res:
                return float(res["price"]) + EXNESS_OFFSET.get("BTCUSD", 0)
    except Exception as e:
        logger.error(f"Error fetching {symbol}: {e}")
    return None

# ---------------- TELEGRAM ----------------
async def send_telegram(msg, chat_id=CHAT_ID):
    global application
    if application:
        try:
            await application.bot.send_message(chat_id=chat_id, text=msg, parse_mode="HTML")
        except Exception as e:
            logger.error(f"Telegram send error: {e}")

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
        
        # ADX
        df["dm_plus"] = df["high"].diff().apply(lambda x: x if x > 0 else 0)
        df["dm_minus"] = -df["low"].diff().apply(lambda x: x if x < 0 else 0)
        df["plus_di"] = 100 * (df["dm_plus"].ewm(span=ADX_PERIOD, adjust=False).mean() / df["atr"])
        df["minus_di"] = 100 * (df["dm_minus"].ewm(span=ADX_PERIOD, adjust=False).mean() / df["atr"])
        df["dx"] = 100 * abs(df["plus_di"] - df["minus_di"]) / (df["plus_di"] + df["minus_di"])
        df["adx"] = df["dx"].ewm(span=ADX_PERIOD, adjust=False).mean()

        if "volume" in df.columns:
            df["avg_volume"] = df["volume"].rolling(ADX_PERIOD).mean()
    except Exception as e:
        logger.error(f"Indicator calculation error: {e}")
    return df

# ---------------- SIGNAL ENGINE ----------------
def generate_ultimate_sniper_message(symbol, direction, price, sl, tps):
    price_format = ".2f" if symbol == "XAUUSD" else ".0f"
    p_str = f"{price:{price_format}}" if price is not None else "N/A"
    sl_str = f"{sl:{price_format}}" if sl is not None else "N/A"
    tp_lines = []
    for i, tp in enumerate(tps):
        tp_str = f"{tp:{price_format}}" if tp is not None else "N/A"
        tp_lines.append(f"🎯 TP {i+1}: {tp_str}")
    tp_text = "\n".join(tp_lines)
    
    return (
        f"<b>🔥 ULTIMATE SNIPER {symbol} {direction} NOW</b>\n"
        f"ENTRY: {p_str}\n\n"
        f"{tp_text}\n"
        f"🛑 SL: {sl_str}\n\n"
        f"⚡ <i>Exness Price Sync Active</i>\n"
        f"#168FX #ULTIMATE"
    )

async def check_signal(symbol, df):
    global last_signal_time, active_signals, pre_signal_sent
    if len(df) < 30: return
    
    try:
        row = df.iloc[-1]
        prev_row = df.iloc[-2]
        price = row["close"]
        ema_f, ema_s = row["ema_fast"], row["ema_slow"]
        adx_val = row["adx"]
        rsi_val = row["rsi"]
        
        # 1. PRE-SIGNAL LOGIC
        ema_diff = abs(ema_f - ema_s)
        prev_ema_diff = abs(prev_row["ema_fast"] - prev_row["ema_slow"])
        if ema_diff < prev_ema_diff * 0.4 and not pre_signal_sent[symbol] and active_signals[symbol] is None:
            await send_telegram(f"⏳ <b>Be ready: {symbol} signal in 30-60 seconds</b>")
            pre_signal_sent[symbol] = True

        # 2. ULTIMATE SNIPER ENTRY
        direction = None
        ema_cross_buy = ema_f > ema_s and prev_row["ema_fast"] <= prev_row["ema_slow"]
        ema_cross_sell = ema_f < ema_s and prev_row["ema_fast"] >= prev_row["ema_slow"]
        
        if ema_cross_buy and adx_val > ADX_THRESHOLD and rsi_val > 55:
            direction = "BUY"
        elif ema_cross_sell and adx_val > ADX_THRESHOLD and rsi_val < 45:
            direction = "SELL"

        if direction:
            if active_signals[symbol] is not None:
                await send_telegram(f"⚠️ <b>Collect your layers — a new strong {symbol} signal is coming.</b>")
                return

            pip = PIP_VALUE[symbol]
            tps = [price + (tp_pip * pip) if direction == "BUY" else price - (tp_pip * pip) for tp_pip in TP_LEVELS]
            sl = price - (SL_PIPS * pip) if direction == "BUY" else price + (SL_PIPS * pip)
            
            msg = generate_ultimate_sniper_message(symbol, direction, price, sl, tps)
            await send_telegram(msg)
            
            active_signals[symbol] = {
                "direction": direction, "entry": price, "sl": sl, "tps": tps,
                "tp_hit": [False] * 5, "breakeven": False, "layers": 0, "timestamp": time.time()
            }
            pre_signal_sent[symbol] = False
            
    except Exception as e:
        logger.error(f"Signal check error: {e}")

# ---------------- MONITORING ----------------
async def monitor_tp_sl():
    global active_signals
    while bot_running:
        try:
            for symbol, signal_data in list(active_signals.items()):
                if signal_data is None: continue
                
                current_price = await fetch_price(symbol)
                if current_price is None: continue
                
                direction = signal_data["direction"]
                entry = signal_data["entry"]
                pip = PIP_VALUE[symbol]
                
                # 1. LAYERING (DCA) LOGIC
                drawdown = (entry - current_price) if direction == "BUY" else (current_price - entry)
                if drawdown >= (LAYERING_DRAWDOWN_PIPS * pip) and signal_data["layers"] < MAX_LAYERS:
                    signal_data["layers"] += 1
                    price_format = ".2f" if symbol == "XAUUSD" else ".0f"
                    await send_telegram(f"💎 <b>{symbol} DRAWDOWN: Add Layer {signal_data['layers']} @ {current_price:{price_format}}</b>\n<i>Getting more profit from down!</i>")
                
                # 2. TP TRACKING
                for i, tp in enumerate(signal_data["tps"]):
                    if not signal_data["tp_hit"][i]:
                        hit = (direction == "BUY" and current_price >= tp) or (direction == "SELL" and current_price <= tp)
                        if hit:
                            signal_data["tp_hit"][i] = True
                            await send_telegram(f"✅ <b>{symbol} TP {i+1} HIT! (+{TP_LEVELS[i]} pips)</b>")
                            if i == 0 and not signal_data["breakeven"]:
                                signal_data["sl"] = entry
                                signal_data["breakeven"] = True
                                await send_telegram(f"🛡️ <b>{symbol} SL moved to Breakeven.</b>")
                
                # 3. SL TRACKING
                sl_hit = (direction == "BUY" and current_price <= signal_data["sl"]) or (direction == "SELL" and current_price >= signal_data["sl"])
                if sl_hit:
                    await send_telegram(f"❌ <b>{symbol} SL HIT (-35 pips).</b>")
                    active_signals[symbol] = None
                
                if all(signal_data["tp_hit"]):
                    await send_telegram(f"💰 <b>{symbol} ALL TPs HIT! Signal Closed.</b>")
                    active_signals[symbol] = None

            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Monitor error: {e}")
            await asyncio.sleep(1)

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
                if len(klines["XAUUSD"]) >= 30:
                    df = pd.DataFrame(klines["XAUUSD"])
                    df = calculate_indicators(df)
                    await check_signal("XAUUSD", df)
            await asyncio.sleep(1)
        except Exception as e:
            logger.error(f"Gold fetch error: {e}")
            await asyncio.sleep(1)

def on_btc_message(ws, message):
    global main_loop
    try:
        data = json.loads(message)
        if "k" in data and data["k"]["x"]:
            k = data["k"]
            price = float(k["c"]) + EXNESS_OFFSET.get("BTCUSD", 0)
            klines["BTCUSD"].append({
                "open": float(k["o"]) + EXNESS_OFFSET.get("BTCUSD", 0), 
                "high": float(k["h"]) + EXNESS_OFFSET.get("BTCUSD", 0),
                "low": float(k["l"]) + EXNESS_OFFSET.get("BTCUSD", 0), 
                "close": price, "volume": float(k["v"]), "timestamp": time.time()
            })
            if len(klines["BTCUSD"]) > 100: klines["BTCUSD"].pop(0)
            if len(klines["BTCUSD"]) >= 30:
                df = pd.DataFrame(klines["BTCUSD"])
                df = calculate_indicators(df)
                if main_loop:
                    main_loop.call_soon_threadsafe(lambda: asyncio.create_task(check_signal("BTCUSD", df)))
    except Exception as e:
        logger.error(f"BTC message error: {e}")

def run_btc_ws():
    while bot_running:
        try:
            ws_url = "wss://fstream.binance.com/ws/btcusdt@kline_1m"
            ws = websocket.WebSocketApp(ws_url, on_message=on_btc_message)
            ws.run_forever()
        except Exception as e:
            logger.error(f"BTC WebSocket error: {e}")
            time.sleep(5)

# ---------------- COMMANDS ----------------
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_html("✅ <b>ROYAL ULTIMATE SNIPER V5 ONLINE</b>\n\n/price | /signal | /status | /active")

async def signal_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_html("<b>Wait. I will give you a good entry shortly.</b>")

async def price_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    try:
        xau = await fetch_price("XAUUSD")
        btc = await fetch_price("BTCUSD")
        xau_str = f"${xau:.2f}" if xau is not None else "Unavailable"
        btc_str = f"${btc:.0f}" if btc is not None else "Unavailable"
        msg = f"<b>💰 PRICES (EXNESS SYNC)</b>\n\nXAUUSD: {xau_str}\nBTCUSD: {btc_str}"
        await update.message.reply_html(msg)
    except Exception as e:
        logger.error(f"Error in price_command: {e}")
        await update.message.reply_html("❌ Error fetching prices.")

async def status_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "<b>🤖 ULTIMATE SNIPER STATUS: ACTIVE</b>\n\n"
    for symbol in ["XAUUSD", "BTCUSD"]:
        msg += f"📊 {symbol}: {len(klines[symbol])} candles\n"
    await update.message.reply_html(msg)

async def active_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    msg = "<b>📋 ACTIVE SIGNALS</b>\n\n"
    has_active = False
    for symbol, signal_data in active_signals.items():
        if signal_data:
            has_active = True
            price_format = ".2f" if symbol == "XAUUSD" else ".0f"
            e_str = f"{signal_data['entry']:{price_format}}" if signal_data['entry'] is not None else "N/A"
            msg += f"<b>{symbol}</b>: {signal_data['direction']} @ {e_str}\nLayers: {signal_data['layers']}\n"
    if not has_active: msg += "No active signals."
    await update.message.reply_html(msg)

# ---------------- ERROR HANDLER ----------------
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(msg="Exception while handling an update:", exc_info=context.error)
    if isinstance(update, Update) and update.effective_message:
        await update.effective_message.reply_text("⚠️ An internal error occurred. The bot is still running.")

# ---------------- MAIN ----------------
async def main():
    global application, main_loop
    main_loop = asyncio.get_running_loop()
    
    # 💎 ENHANCED CONFLICT FIX: Delete webhook and clear old updates multiple times
    for _ in range(3):
        try:
            requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/deleteWebhook", timeout=5)
            requests.get(f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/getUpdates?offset=-1&limit=1", timeout=5)
            time.sleep(1)
        except: pass

    application = ApplicationBuilder().token(TELEGRAM_TOKEN).build()
    application.add_error_handler(error_handler)
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("signal", signal_command))
    application.add_handler(CommandHandler("price", price_command))
    application.add_handler(CommandHandler("status", status_command))
    application.add_handler(CommandHandler("active", active_command))
    
    await application.initialize()
    await application.start()
    await application.updater.start_polling(drop_pending_updates=True)
    
    print("✅ Ultimate Sniper Bot V5 Started")
    await send_telegram("🚀 <b>ROYAL ULTIMATE SNIPER V5 ONLINE</b>\n<i>Conflict-Proof mode activated.</i>")
    
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
