import MetaTrader5 as mt5
import pandas as pd
import yfinance as yf
import requests
import time
from datetime import datetime

# ================= CONFIG =================
TOKEN = "8601674578:AAHycLEx-6M_r_JHFuS96oKuLTBJqefwKnk"
CHAT_ID = "992623579"

SYMBOL = "XAUUSD"
RISK_PERCENT = 1

last_trade_time = 0

# ================= TELEGRAM =================
def send(msg):
    url = f"https://api.telegram.org/bot{TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg})

# ================= MT5 =================
mt5.initialize()

def lot_size(balance, sl_points):
    risk = balance * (RISK_PERCENT / 100)
    lot = risk / sl_points
    return round(lot, 2)

def open_trade(order_type, sl, tp):
    symbol_info = mt5.symbol_info(SYMBOL)
    price = mt5.symbol_info_tick(SYMBOL).ask if order_type == "buy" else mt5.symbol_info_tick(SYMBOL).bid

    balance = mt5.account_info().balance
    lot = lot_size(balance, abs(price - sl))

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": SYMBOL,
        "volume": lot,
        "type": mt5.ORDER_TYPE_BUY if order_type == "buy" else mt5.ORDER_TYPE_SELL,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 20,
        "magic": 123456,
        "comment": "AI BOT",
    }

    mt5.order_send(request)

    send(f"🚀 TRADE OPENED ({order_type.upper()})\nLot: {lot}")

# ================= DATA =================
def get_data(interval):
    return yf.download("XAUUSD=X", period="1d", interval=interval)

# ================= AI SCORE =================
def ai_score(df):
    score = 0
    last = df.iloc[-1]

    if last['EMA20'] > last['EMA50']:
        score += 2
    if last['Close'] > last['EMA20']:
        score += 1
    if last['RSI'] > 50:
        score += 1

    return score

# ================= INDICATORS =================
def indicators(df):
    df['EMA20'] = df['Close'].ewm(span=20).mean()
    df['EMA50'] = df['Close'].ewm(span=50).mean()

    delta = df['Close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)

    rs = gain.rolling(14).mean() / loss.rolling(14).mean()
    df['RSI'] = 100 - (100 / (1 + rs))

    df['ATR'] = (df['High'] - df['Low']).rolling(14).mean()

    return df

# ================= SIGNAL =================
def check(df):
    global last_trade_time

    now = time.time()

    if now - last_trade_time < 300:
        return

    score = ai_score(df)
    last = df.iloc[-1]

    if score >= 3:
        entry = last['Close']
        sl = entry - last['ATR']
        tp = entry + (last['ATR'] * 2)

        open_trade("buy", sl, tp)
        last_trade_time = now

    if score <= -3:
        entry = last['Close']
        sl = entry + last['ATR']
        tp = entry - (last['ATR'] * 2)

        open_trade("sell", sl, tp)
        last_trade_time = now

# ================= BREAKEVEN =================
def manage_trades():
    positions = mt5.positions_get(symbol=SYMBOL)

    for pos in positions:
        price = mt5.symbol_info_tick(SYMBOL).bid

        if pos.type == 0:  # buy
            if price - pos.price_open > 1:
                mt5.order_send({
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": pos.ticket,
                    "sl": pos.price_open,
                    "tp": pos.tp,
                })

        if pos.type == 1:  # sell
            if pos.price_open - price > 1:
                mt5.order_send({
                    "action": mt5.TRADE_ACTION_SLTP,
                    "position": pos.ticket,
                    "sl": pos.price_open,
                    "tp": pos.tp,
                })

# ================= LOOP =================
while True:
    try:
        df = get_data("1m")
        df = indicators(df)

        check(df)
        manage_trades()

        time.sleep(60)

    except Exception as e:
        print(e)
        time.sleep(10)
