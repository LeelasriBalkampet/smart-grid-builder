from flask import Flask, jsonify, request
from flask_cors import CORS
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
from sklearn.neural_network import MLPRegressor
import numpy as np
import requests
import os
import json
import sqlite3
import pandas as pd
from datetime import datetime
from io import StringIO
import time

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

from flask.json.provider import DefaultJSONProvider

class NumpyJSONProvider(DefaultJSONProvider):
    def default(self, obj):
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)

app.json_provider_class = NumpyJSONProvider
app.json = NumpyJSONProvider(app)

API_KEY = "ccdf0efdfba224c382832d024c586c93"

def init_db():
    conn = sqlite3.connect("grid_history.db")
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS simulations (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
            load_value REAL,
            total_unmet REAL,
            total_cost REAL,
            total_savings REAL
        )
    ''')
    conn.commit()
    conn.close()

init_db()

weather_cache = {
    "timestamp": 0,
    "data": (30, 60, 20, 5)
}

def get_weather():
    global weather_cache
    if time.time() - weather_cache["timestamp"] < 300: # 5 minutes cache
        return weather_cache["data"]

    city = "Hyderabad"
    url = (
        f"https://api.openweathermap.org/data/2.5/weather"
        f"?q={city}&appid={API_KEY}&units=metric"
    )
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if "main" not in data:
            return weather_cache["data"]
        temp = data["main"]["temp"]
        humidity = data["main"]["humidity"]
        clouds = data.get("clouds", {}).get("all", 20)
        wind = data.get("wind", {}).get("speed", 5)
        
        weather_cache["data"] = (temp, humidity, clouds, wind)
        weather_cache["timestamp"] = time.time()
        return weather_cache["data"]
    except Exception:
        return weather_cache["data"]

@app.route("/")
def index():
    return app.send_static_file("index.html")

@app.route("/api/weather")
def weather():
    temp, humidity, clouds, wind = get_weather()
    return jsonify({"temp": temp, "humidity": humidity, "clouds": clouds, "wind": wind})

@app.route("/api/simulate", methods=["POST"])
def simulate():
    body = request.get_json()

    load_value     = float(body.get("load_value", 80))
    use_solar      = bool(body.get("use_solar", True))
    use_wind       = bool(body.get("use_wind", True))
    use_battery    = bool(body.get("use_battery", True))
    use_grid       = bool(body.get("use_grid", True))
    solar_intensity = float(body.get("solar_intensity", 70))
    wind_speed     = float(body.get("wind_speed", 5))

  
    temp, humidity, clouds, real_wind_speed = get_weather()

    t = np.arange(24)

    # Use actual weather data to modulate generation
    P_solar = np.zeros(24)
    if use_solar:
        # Fewer clouds = more solar intensity. Base intensity modified by cloud cover %.
        effective_intensity = solar_intensity * (1 - (clouds / 100.0))
        P_solar = effective_intensity * np.maximum(0, np.sin(np.pi * (t - 6) / 12))

    P_wind = np.zeros(24)
    if use_wind:
        # Use real wind speed instead of the slider (or combination)
        effective_wind = real_wind_speed if wind_speed == 5 else wind_speed
        # Assume wind varies slightly over the day
        P_wind = effective_wind * 4 * (1 + 0.2 * np.sin(np.pi * t / 12))

    P_ren  = P_solar + P_wind
    custom_load = body.get("custom_load_profile")
    if custom_load and isinstance(custom_load, list) and len(custom_load) == 24:
        P_load = np.array(custom_load)
    else:
        P_load = load_value + 20 * np.sin(np.pi * (t - 6) / 12) + 10 * np.sin(np.pi * (t - 18) / 12)
        P_load = np.maximum(P_load, 20)

    temperature_series = temp + 2 * np.sin(np.pi * (t - 6) / 12)
    X_lr = np.column_stack((t, temperature_series))
    y_lr = P_load
    lr_model = LinearRegression()
    lr_model.fit(X_lr, y_lr)
    predicted_lr = lr_model.predict(X_lr).tolist()

    X_nn = P_load[:-1].reshape(-1, 1)
    y_nn = P_load[1:].reshape(-1, 1)

    scaler_X = StandardScaler()
    scaler_y = StandardScaler()
    
    X_nn_scaled = scaler_X.fit_transform(X_nn)
    y_nn_scaled = scaler_y.fit_transform(y_nn)

    nn_model = MLPRegressor(hidden_layer_sizes=(10,), activation="relu", max_iter=200, random_state=42)
    nn_model.fit(X_nn_scaled, y_nn_scaled.ravel())
    
    predicted_nn_scaled = nn_model.predict(X_nn_scaled)
    predicted_nn = scaler_y.inverse_transform(predicted_nn_scaled.reshape(-1, 1)).flatten().tolist()

   
    battery_capacity = 100
    battery_level    = 50
    battery_levels   = []
    battery_store    = []
    battery_used     = []
    unmet_load       = []
    P_from_grid      = []
    P_spilled        = []
    
    # Time-of-Use (ToU) Pricing: Peak hours 18:00 - 21:00 cost $0.30, else $0.10
    prices = [0.30 if 18 <= h <= 21 else 0.10 for h in t]
    hourly_costs = []

    for i in range(24):
        load     = P_load[i]
        ren      = P_ren[i]
        price    = prices[i]
        
        excess   = max(ren - load, 0)
        shortage = max(load - ren, 0)
        
        charge   = 0
        discharge = 0
        grid_use  = 0
        unserved  = 0
        
        # SMART AI BEHAVIOR: Charge from grid if it's very cheap (night time 0-5) and battery is low
        if use_battery and use_grid and i < 6 and battery_level < battery_capacity * 0.8:
            grid_charge = min(battery_capacity - battery_level - excess, 20) # charge up to 20kW per hour from grid
            if grid_charge > 0:
                grid_use += grid_charge
                charge += grid_charge

        if use_battery:
            # Charge from renewables
            ren_charge = min(excess, battery_capacity - battery_level - charge)
            charge += ren_charge
            battery_level += charge

        if use_battery:
            discharge = min(shortage, battery_level)
            battery_level -= discharge

        if use_grid:
            grid_use += max(shortage - discharge, 0)
        else:
            unserved = max(shortage - discharge, 0)

        spill = max(excess - (charge if excess > 0 else 0), 0)

        hourly_costs.append(grid_use * price)
        battery_levels.append(battery_level)
        battery_store.append(charge)
        battery_used.append(discharge)
        P_from_grid.append(grid_use)
        P_spilled.append(spill)
        unmet_load.append(unserved)

    total_unmet = float(np.sum(unmet_load))

    # ── Financials & AI Insights ──
    total_grid_kwh = float(np.sum(P_from_grid))
    total_cost = float(np.sum(hourly_costs))
    
    # Calculate savings (what cost would have been without renewables/battery on flat rate vs what it is now)
    # Assume old behavior was all load from grid at flat rate $0.15
    old_cost = float(np.sum(P_load)) * 0.15
    total_savings = old_cost - total_cost

    max_pred_idx = int(np.argmax(predicted_nn))
    max_pred_val = predicted_nn[max_pred_idx]
    peak_hour = int(t[1:][max_pred_idx])
    ai_insight = f"AI predicts peak load of {max_pred_val:.1f} kW at {peak_hour:02d}:00. Using Time-of-Use pricing, AI shifted grid charging to off-peak."

    # Save to Database
    try:
        conn = sqlite3.connect("grid_history.db")
        c = conn.cursor()
        c.execute('''
            INSERT INTO simulations (load_value, total_unmet, total_cost, total_savings)
            VALUES (?, ?, ?, ?)
        ''', (load_value, total_unmet, total_cost, total_savings))
        conn.commit()
        conn.close()
    except Exception as e:
        print("DB Error:", e)

    return jsonify({
        "t":              [int(x) for x in t],
        "t_nn":           [int(x) for x in t[1:]],
        "P_load":         P_load.tolist(),
        "P_solar":        P_solar.tolist(),
        "P_wind":         P_wind.tolist(),
        "P_ren":          P_ren.tolist(),
        "battery_levels": battery_levels,
        "battery_store":  battery_store,
        "battery_used":   battery_used,
        "P_from_grid":    P_from_grid,
        "P_spilled":      P_spilled,
        "unmet_load":     unmet_load,
        "predicted_nn":   predicted_nn,
        "predicted_lr":   predicted_lr,
        "total_unmet":    total_unmet,
        "total_cost":     total_cost,
        "total_savings":  total_savings,
        "ai_insight":     ai_insight,
        "temp":           temp,
        "humidity":       humidity,
        "load_value":     load_value,
        "use_solar":      use_solar,
        "use_wind":       use_wind,
        "use_battery":    use_battery,
        "use_grid":       use_grid,
        "hourly_costs":   hourly_costs,
        "prices":         prices,
        "clouds":         clouds,
        "wind_speed":     real_wind_speed
    })

@app.route("/api/history", methods=["GET"])
def history():
    try:
        conn = sqlite3.connect("grid_history.db")
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM simulations ORDER BY timestamp DESC LIMIT 50")
        rows = c.fetchall()
        conn.close()
        
        history_list = [dict(row) for row in rows]
        return jsonify(history_list)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/api/upload-csv", methods=["POST"])
def upload_csv():
    if 'file' not in request.files:
        return jsonify({"error": "No file part"}), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({"error": "No selected file"}), 400
    
    try:
        # Read the CSV file
        stream = StringIO(file.stream.read().decode("UTF8"), newline=None)
        df = pd.read_csv(stream)
        
        # Expecting a column 'load' or similar
        col_names = [c.lower() for c in df.columns]
        load_col = None
        for c in col_names:
            if 'load' in c or 'demand' in c:
                load_col = df.columns[col_names.index(c)]
                break
        
        if load_col is None:
            return jsonify({"error": "Could not find a 'load' or 'demand' column in the CSV. Please ensure your CSV has a column named 'load'."}), 400
            
        load_data = df[load_col].fillna(0).values.tolist()
        
        # We'll return the parsed load array (first 24 items or padded to 24)
        profile_24 = load_data[:24]
        if len(profile_24) < 24:
            profile_24 = profile_24 + [profile_24[-1]] * (24 - len(profile_24))
            
        avg_load = float(np.mean(profile_24))
        max_load = float(np.max(profile_24))
        
        return jsonify({
            "message": "CSV processed successfully",
            "data_points": len(load_data),
            "average_load": avg_load,
            "max_load": max_load,
            "suggested_load_value": avg_load,
            "load_profile": profile_24
        })
    except Exception as e:
        return jsonify({"error": f"Error processing CSV: {str(e)}"}), 500

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
