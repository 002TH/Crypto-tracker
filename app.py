from flask import Flask, render_template_string
import requests
import threading
import time
from datetime import datetime, timedelta
import pytz

app = Flask(__name__)

# === SETTINGS ===
COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
NIGERIA_TZ = pytz.timezone("Africa/Lagos")

buy_volume = 0
sell_volume = 0
add_counter = 0
tick_counter = 0
tick_cache = {coin: 0 for coin in COINS}
last_tick_arrow = "→"
last_15m_check = datetime.utcnow()

def get_price(symbol):
    r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}").json()
    return float(r["price"])

def get_prev_close(symbol):
    r = requests.get(f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1d&limit=2").json()
    return float(r[-2][4])

def get_recent_trades(symbol):
    r = requests.get(f"https://api.binance.com/api/v3/trades?symbol={symbol}&limit=1000").json()
    return r

def reset_volumes():
    global buy_volume, sell_volume
    buy_volume = 0
    sell_volume = 0

def background_worker():
    global buy_volume, sell_volume, add_counter, tick_counter, last_tick_arrow, last_15m_check

    while True:
        now = datetime.now(NIGERIA_TZ)

        if now.hour == 0 and now.minute == 0 and now.second < 5:
            reset_volumes()

        add_counter = 0
        tick_counter = 0

        for coin in COINS:
            try:
                # Price data
                price = get_price(coin)
                prev_close = get_prev_close(coin)

                # --- ADD: price vs previous close
                if price > prev_close:
                    add_counter += 1
                elif price < prev_close:
                    add_counter -= 1

                # --- TICK: compare to last cached price
                if price > tick_cache[coin]:
                    tick_counter += 1
                elif price < tick_cache[coin]:
                    tick_counter -= 1
                tick_cache[coin] = price

                # --- Cumulative Delta
                trades = get_recent_trades(coin)
                for trade in trades:
                    qty = float(trade["qty"])
                    if trade["isBuyerMaker"]:
                        sell_volume += qty
                    else:
                        buy_volume += qty

            except Exception as e:
                print(f"Error processing {coin}: {e}")
                continue

        # TICK arrow direction
        if datetime.utcnow() - last_15m_check >= timedelta(minutes=15):
            last_15m_check = datetime.utcnow()
            if tick_counter > 0:
                last_tick_arrow = "↑"
            elif tick_counter < 0:
                last_tick_arrow = "↓"
            else:
                last_tick_arrow = "→"

        time.sleep(3)

# === Background thread ===
threading.Thread(target=background_worker, daemon=True).start()

# === Flask route ===
@app.route("/")
def index():
    # Calculate Delta Ratio
    if sell_volume > 0:
        ratio = round(buy_volume / sell_volume, 2)
        delta_ratio = f"+{ratio}:1" if ratio > 1 else f"-{round(sell_volume / buy_volume, 2)}:1"
    else:
        delta_ratio = "+∞"

    # Determine Delta Color: compare current price to yesterday’s close of BTC
    try:
        current_price = get_price("BTCUSDT")
        yclose = get_prev_close("BTCUSDT")
        delta_color = "green" if current_price > yclose else "red"
    except:
        delta_color = "white"

    return render_template_string("""
    <html>
    <head>
        <title>Crypto Breadth Tracker</title>
        <meta http-equiv="refresh" content="5" />
        <style>
            body { font-family: monospace; background-color: black; color: white; text-align: center; padding-top: 50px; }
            .green { color: lime; }
            .red { color: red; }
        </style>
    </head>
    <body>
        <h1>Crypto Breadth Tracker (Nigerian Time)</h1>
        <h2>Delta Ratio: <span class="{{ delta_color }}">{{ delta_ratio }}</span></h2>
        <h2>ADD: <span class="{{ add_color }}">{{ add_counter }}</span></h2>
        <h2>TICK: <span class="{{ tick_color }}">{{ tick_counter }} {{ tick_arrow }}</span></h2>
        <p>{{ now }}</p>
    </body>
    </html>
    """,
    delta_ratio=delta_ratio,
    delta_color=delta_color,
    add_counter=add_counter,
    add_color="green" if add_counter > 0 else "red",
    tick_counter=tick_counter,
    tick_arrow=last_tick_arrow,
    tick_color="green" if tick_counter > 0 else "red",
    now=datetime.now(NIGERIA_TZ).strftime('%Y-%m-%d %H:%M:%S'))

# === Render-compatible server run ===
import os
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)