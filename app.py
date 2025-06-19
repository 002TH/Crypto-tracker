from flask import Flask, render_template, request, jsonify
import threading, json, time
from datetime import datetime
import pytz
from websocket import create_connection
import requests

app = Flask(__name__)
NIGERIA_TZ = pytz.timezone("Africa/Lagos")
COINS = ["SOLUSDT", "BTCUSDT", "ETHUSDT"]

# === STATE ===
coin_data = {
    symbol: {
        "buy_volume": 0.0,
        "sell_volume": 0.0,
        "price": 0.0,
        "prev_close": 0.0,
        "last_tick": 0.0
    } for symbol in COINS
}

tick_arrow = "→"
tick_counter = 0
add_counter = 0

# === HELPER FUNCTIONS ===
def get_prev_close(symbol):
    try:
        r = requests.get(f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval=1d&limit=2").json()
        return float(r[-2][4])
    except:
        return 0.0

def reset_daily_data():
    global tick_arrow, tick_counter, add_counter
    tick_arrow = "→"
    tick_counter = 0
    add_counter = 0
    for coin in coin_data:
        coin_data[coin]["buy_volume"] = 0
        coin_data[coin]["sell_volume"] = 0
        coin_data[coin]["prev_close"] = get_prev_close(coin)

# === BACKGROUND THREAD ===
def ws_worker():
    global tick_arrow, tick_counter, add_counter
    stream_url = f"wss://stream.binance.com:9443/stream?streams={'/'.join([s.lower() + '@trade' for s in COINS])}"
    ws = create_connection(stream_url)
    last_reset_day = datetime.now(NIGERIA_TZ).day

    while True:
        now = datetime.now(NIGERIA_TZ)
        if now.day != last_reset_day:
            reset_daily_data()
            last_reset_day = now.day

        try:
            msg = json.loads(ws.recv())
            data = msg['data']
            symbol = data['s']
            qty = float(data['q'])
            price = float(data['p'])
            is_buyer_maker = data['m']

            if is_buyer_maker:
                coin_data[symbol]["sell_volume"] += qty
            else:
                coin_data[symbol]["buy_volume"] += qty

            coin_data[symbol]["price"] = price

            # ADD Logic
            if price > coin_data[symbol]["prev_close"]:
                add_counter += 1
            else:
                add_counter -= 1

            # TICK Logic
            if coin_data[symbol]["last_tick"] != 0:
                if price > coin_data[symbol]["last_tick"]:
                    tick_counter += 1
                elif price < coin_data[symbol]["last_tick"]:
                    tick_counter -= 1
            coin_data[symbol]["last_tick"] = price

            # Tick arrow logic every 15 mins
            if now.minute % 15 == 0 and now.second < 3:
                if tick_counter > 0:
                    tick_arrow = "↑"
                elif tick_counter < 0:
                    tick_arrow = "↓"
                else:
                    tick_arrow = "→"

        except Exception as e:
            print("WebSocket error:", e)
            time.sleep(5)
            try:
                ws = create_connection(stream_url)
            except:
                continue

# === API ROUTES ===
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/data")
def get_data():
    total_buy = sum(coin_data[c]["buy_volume"] for c in COINS)
    total_sell = sum(coin_data[c]["sell_volume"] for c in COINS)
    delta_ratio = (total_buy / total_sell) if total_sell else total_buy
    ratio_str = f"+{round(delta_ratio, 2)}:1" if total_buy > total_sell else f"-{round(delta_ratio, 2)}:1"

    reference_coin = COINS[0]
    ref_price = coin_data[reference_coin]["price"]
    ref_close = coin_data[reference_coin]["prev_close"]
    delta_color = "green" if ref_price > ref_close else "red"

    return jsonify({
        "delta_ratio": ratio_str,
        "delta_color": delta_color,
        "add": add_counter,
        "tick": tick_counter,
        "tick_arrow": tick_arrow,
        "time": datetime.now(NIGERIA_TZ).strftime("%Y-%m-%d %H:%M:%S")
    })

# === START THREAD ===
threading.Thread(target=ws_worker, daemon=True).start()

if __name__ == "__main__":
    import os
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)