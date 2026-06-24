from flask import Flask, jsonify, request
from flask_cors import CORS
from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
from tensorflow.keras.models import Sequential
from tensorflow.keras.layers import Dense
from tensorflow.keras.optimizers import Adam
import numpy as np
import requests
import os
import json

app = Flask(__name__, static_folder=".", static_url_path="")
CORS(app)

# ── Make Flask JSON provider handle numpy types ──
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

# ───────────────────────────────────────────────
#  Helper: fetch weather
# ───────────────────────────────────────────────
def get_weather():
    city = "Hyderabad"
    url = (
        f"https://api.openweathermap.org/data/2.5/weather"
        f"?q={city}&appid={API_KEY}&units=metric"
    )
    try:
        response = requests.get(url, timeout=5)
        data = response.json()
        if "main" not in data:
            return 30, 60
        return data["main"]["temp"], data["main"]["humidity"]
    except Exception:
        return 30, 60


# ───────────────────────────────────────────────
#  Route: serve index.html at root
# ───────────────────────────────────────────────
@app.route("/")
def index():
    return app.send_static_file("index.html")


# ───────────────────────────────────────────────
#  Route: GET /api/weather
# ───────────────────────────────────────────────
@app.route("/api/weather")
def weather():
    temp, humidity = get_weather()
    return jsonify({"temp": temp, "humidity": humidity})


# ───────────────────────────────────────────────
#  Route: POST /api/simulate
#  Body (JSON):
#    load_value, use_solar, use_wind, use_battery,
#    use_grid, solar_intensity, wind_speed
# ───────────────────────────────────────────────
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

    # ── Weather ──
    temp, humidity = get_weather()

    # ── Time ──
    t = np.arange(24)

    # ── Generation ──
    P_solar = np.zeros(24)
    if use_solar:
        P_solar = solar_intensity * np.maximum(0, np.sin(np.pi * (t - 6) / 12))

    P_wind = np.zeros(24)
    if use_wind:
        P_wind = wind_speed * 4 * np.ones(24)

    P_ren  = P_solar + P_wind
    P_load = load_value + 20 * np.sin(np.pi * (t - 6) / 12) + 10 * np.sin(np.pi * (t - 18) / 12)
    P_load = np.maximum(P_load, 20)

    # ── ML – Linear Regression ──
    temperature_series = temp + 2 * np.sin(np.pi * (t - 6) / 12)
    X_lr = np.column_stack((t, temperature_series))
    y_lr = P_load
    lr_model = LinearRegression()
    lr_model.fit(X_lr, y_lr)
    predicted_lr = lr_model.predict(X_lr).tolist()

    # ── ML – Neural Network ──
    X_nn = P_load[:-1].reshape(-1, 1)
    y_nn = P_load[1:].reshape(-1, 1)

    scaler_X = StandardScaler()
    scaler_y = StandardScaler()
    X_scaled = scaler_X.fit_transform(X_nn)
    y_scaled = scaler_y.fit_transform(y_nn)

    nn_model = Sequential([
        Dense(10, activation="relu", input_shape=(1,)),
        Dense(1),
    ])
    nn_model.compile(optimizer=Adam(0.01), loss="mse")
    nn_model.fit(X_scaled, y_scaled, epochs=100, verbose=0)

    y_pred_scaled = nn_model.predict(X_scaled)
    predicted_nn  = scaler_y.inverse_transform(y_pred_scaled).flatten().tolist()

    # ── Battery simulation ──
    battery_capacity = 100
    battery_level    = 50
    battery_levels   = []
    battery_store    = []
    battery_used     = []
    unmet_load       = []
    P_from_grid      = []
    P_spilled        = []

    for i in range(24):
        load     = P_load[i]
        ren      = P_ren[i]
        excess   = max(ren - load, 0)
        shortage = max(load - ren, 0)
        charge   = 0
        discharge = 0
        grid_use  = 0
        unserved  = 0

        if use_battery:
            charge = min(excess, battery_capacity - battery_level)
            battery_level += charge

        if use_battery:
            discharge = min(shortage, battery_level)
            battery_level -= discharge

        if use_grid:
            grid_use = max(shortage - discharge, 0)
        else:
            unserved = max(shortage - discharge, 0)

        spill = max(excess - charge, 0)

        battery_levels.append(battery_level)
        battery_store.append(charge)
        battery_used.append(discharge)
        P_from_grid.append(grid_use)
        P_spilled.append(spill)
        unmet_load.append(unserved)

    total_unmet = float(np.sum(unmet_load))

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
        "temp":           temp,
        "humidity":       humidity,
        "load_value":     load_value,
        "use_solar":      use_solar,
        "use_wind":       use_wind,
        "use_battery":    use_battery,
        "use_grid":       use_grid,
    })


# ───────────────────────────────────────────────
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
