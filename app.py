from flask import Flask, render_template, request, redirect
import threading
import time
import json
import pytz
from datetime import datetime
from collections import defaultdict
from websocket import create_connection
import requests
import os

app = Flask(__name__)

NIGERIA_TZ = pytz.timezone("Africa/Lagos")
COINS_FILE = "coins.json"

# === Load coin list or set default ===
if os.path.exists(COINS_FILE):
    with open(COINS_FILE, "r") as f:
        COINS = json.load(f)
else:
    COINS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
    with open(COINS_FILE, "w") as f:
        json.dump(COINS, f)

buy_volume = 0
sell_volume = 0
add_counter = 0
tick_counter = 0
tick_cache = {}
tick_arrow = "→"

delta_data = defaultdict(lambda: {"buy": 0, "sell": 0, "prev_close": 0})


def get_price(symbol):
    try:
        r = requests.get(f"https://api.binance.com/api/v3/ticker/price?symbol={symbol}").json()
        return float(r["price"])
    except:
        return 0

def get_prev_close(symbol):
    try:
        r = requests.get(f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1d&limit=2").json()
        return float(r[-2][4])
    except:
        return 0

def load_prev_closes():
    for coin in COINS:
        delta_data[coin]["prev_close"] = get_prev_close(coin)

def reset_volumes():
    global buy_volume, sell_volume, add_counter, tick_counter, tick_arrow
    buy_volume = 0
    sell_volume = 0
    add_counter = 0
    tick_counter = 0
    tick_arrow = "→"
    load_prev_closes()

def delta_worker():
    global buy_volume, sell_volume, add_counter, tick_counter, tick_arrow

    while True:
        try:
            now = datetime.now(NIGERIA_TZ)
            if now.hour == 0 and now.minute == 0 and now.second < 5:
                reset_volumes()

            streams = "/".join([f"{coin.lower()}@trade" for coin in COINS])
            ws = create_connection(f"wss://stream.binance.com:9443/stream?streams={streams}")
            tick_cache.update({coin: get_price(coin) for coin in COINS})

            while True:
                data = json.loads(ws.recv())
                trade = data["data"]
                symbol = trade["s"]
                qty = float(trade["q"])
                price = float(trade["p"])
                is_buyer_maker = trade["m"]

                if is_buyer_maker:
                    sell_volume += qty
                    delta_data[symbol]["sell"] += qty
                else:
                    buy_volume += qty
                    delta_data[symbol]["buy"] += qty

                # ADD logic
                if price > delta_data[symbol]["prev_close"]:
                    add_counter += 1
                else:
                    add_counter -= 1

                # TICK logic
                if price > tick_cache[symbol]:
                    tick_counter += 1
                elif price < tick_cache[symbol]:
                    tick_counter -= 1
                tick_cache[symbol] = price

                # TICK Arrow update every 15 minutes
                if int(time.time()) % (15 * 60) == 0:
                    if tick_counter > 0:
                        tick_arrow = "↑"
                    elif tick_counter < 0:
                        tick_arrow = "↓"
                    else:
                        tick_arrow = "→"

        except Exception as e:
            time.sleep(5)  # reconnect delay
            continue

@app.route("/", methods=["GET", "POST"])
def index():
    global COINS
    if request.method == "POST":
        new_list = request.form.get("coin_list", "")
        coins = [c.strip().upper() for c in new_list.split(",") if c.strip()]
        if coins:
            COINS[:] = coins
            with open(COINS_FILE, "w") as f:
                json.dump(COINS, f)
            reset_volumes()
        return redirect("/")

    delta_ratio = f"{round(buy_volume / sell_volume, 2) if sell_volume else buy_volume:.2f}:1"
    delta_color = "green" if get_price(COINS[0]) > delta_data[COINS[0]]["prev_close"] else "red"

    return render_template("index.html",
        delta_ratio=("+" if delta_color == "green" else "-") + delta_ratio,
        delta_color=delta_color,
        add_counter=add_counter,
        tick_counter=tick_counter,
        tick_arrow=tick_arrow,
        coin_list=", ".join(COINS),
        now=datetime.now(NIGERIA_TZ).strftime('%Y-%m-%d %H:%M:%S')
    )

# Start background thread
threading.Thread(target=delta_worker, daemon=True).start()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
