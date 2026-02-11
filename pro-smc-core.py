import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import pytz
import requests
import time
from datetime import datetime, UTC

# ================= SETTINGS =================
LOGIN = 413341109
PASSWORD = "Test@123"
SERVER = "Exness-MT5Trial6"

SYMBOLS = ["XAUUSDm", "EURUSDm", "GBPUSDm"]

HTF = mt5.TIMEFRAME_H4
LTF = mt5.TIMEFRAME_M15

BOT_TOKEN = "8252878004:AAFykCNZMGQvqSlGNMiRWVLOh3LoWHFZsR4"
CHAT_ID = "5963049329"

# ============================================


# ================= MT5 =================
def connect():
    if not mt5.initialize(login=LOGIN, password=PASSWORD, server=SERVER):
        raise RuntimeError("MT5 connection failed")
    print("✅ MT5 Connected")


# ================= DATA =================
def get_rates(symbol, timeframe, n=200):
    utc = datetime.now(pytz.utc)
    rates = mt5.copy_rates_from(symbol, timeframe, utc, n)
    return pd.DataFrame(rates)


# ================= SESSION FILTER =================
def in_session():
    now = datetime.now(UTC).hour
    return (7 <= now <= 16) or (13 <= now <= 22)


# ================= SWINGS =================
def find_swings(df):
    highs, lows = [], []

    for i in range(2, len(df) - 2):
        if df.high[i] > df.high[i-1] and df.high[i] > df.high[i+1]:
            highs.append(df.high[i])

        if df.low[i] < df.low[i-1] and df.low[i] < df.low[i+1]:
            lows.append(df.low[i])

    return highs, lows


# ================= BOS =================
def detect_bos(swings_high, swings_low):
    if len(swings_high) < 2 or len(swings_low) < 2:
        return None

    if swings_high[-1] > swings_high[-2]:
        return "BUY"

    if swings_low[-1] < swings_low[-2]:
        return "SELL"

    return None


# ================= ORDER BLOCK =================
def find_order_block(df, direction):
    for i in range(len(df) - 3, 2, -1):
        candle = df.iloc[i]

        if direction == "BUY" and candle.close < candle.open:
            return candle.low, candle.high

        if direction == "SELL" and candle.close > candle.open:
            return candle.low, candle.high

    return None, None


# ================= LIQUIDITY SWEEP (M15) =================
def liquidity_sweep(df, direction):
    last = df.iloc[-1]
    prev = df.iloc[-2]

    if direction == "BUY":
        return last.low < prev.low and last.close > prev.low

    if direction == "SELL":
        return last.high > prev.high and last.close < prev.high

    return False


# ================= BACKTEST =================
def backtest(symbol, direction, entry, sl, tps):
    df = get_rates(symbol, LTF, 200)

    wins = 0
    total = 0

    for i in range(20, len(df) - 1):
        total += 1
        candle = df.iloc[i]

        if direction == "BUY":
            if candle.low <= sl:
                continue
            if candle.high >= tps[1]:
                wins += 1

        if direction == "SELL":
            if candle.high >= sl:
                continue
            if candle.low <= tps[1]:
                wins += 1

    return round((wins / total) * 100, 1) if total else 0


# ================= TELEGRAM =================
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    requests.post(url, data={"chat_id": CHAT_ID, "text": msg})


# ================= SIGNAL =================
def check_signal(symbol):

    print(symbol)
    
    if not in_session():
        return

    htf = get_rates(symbol, HTF)
    ltf = get_rates(symbol, LTF)

    swings_h, swings_l = find_swings(htf)
    direction = detect_bos(swings_h, swings_l)

    if not direction:
        return

    ob_low, ob_high = find_order_block(htf, direction)
    if ob_low is None:
        return

    if not liquidity_sweep(ltf, direction):
        return

    price = mt5.symbol_info_tick(symbol).bid

    if not (ob_low <= price <= ob_high):
        return

    # ===== SL & TP =====
    sl = ob_low if direction == "BUY" else ob_high
    risk = abs(price - sl)

    tp1 = price + risk if direction == "BUY" else price - risk
    tp2 = price + risk * 2 if direction == "BUY" else price - risk * 2
    tp3 = price + risk * 3 if direction == "BUY" else price - risk * 3

    accuracy = backtest(symbol, direction, price, sl, [tp1, tp2, tp3])

    # ===== MESSAGE =====
    msg = f"""
📊 SMC SIGNAL (M15 CONFIRM)

Symbol: {symbol}
Direction: {direction}

Entry: {round(price,3)}
SL: {round(sl,3)}

TP1: {round(tp1,3)}
TP2: {round(tp2,3)}
TP3: {round(tp3,3)}

Session: London / NY
Backtest Accuracy: {accuracy}%

Time: {datetime.now().strftime('%Y-%m-%d %H:%M')}
"""

    print(msg)
    send_telegram(msg)


# ================= MAIN LOOP =================
def run():
    connect()

    while True:
        for s in SYMBOLS:
            try:
                check_signal(s)
            except Exception as e:
                print("Error:", e)

        time.sleep(60)


if __name__ == "__main__":
    run()
