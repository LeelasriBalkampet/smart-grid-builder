from sklearn.linear_model import LinearRegression
from sklearn.preprocessing import StandardScaler
from sklearn.neural_network import MLPRegressor
import streamlit as st
import numpy as np
import matplotlib.pyplot as plt
import requests

API_KEY = "ccdf0efdfba224c382832d024c586c93"

def get_weather():
    city = "Hyderabad"
    url = f"https://api.openweathermap.org/data/2.5/weather?q={city}&appid={API_KEY}&units=metric"
    
    response = requests.get(url)
    data = response.json()

    if "main" not in data:
        st.warning("Weather API failed, using default values")
        return 30, 60  

    temp = data["main"]["temp"]
    humidity = data["main"]["humidity"]

    return temp, humidity

# ===== USER CONTROLS =====  
st.sidebar.markdown("""
<div style="
    background-color:#2c2f33;
    color:white;
    padding:10px;
    border-radius:8px;
    border:1px solid #444;
    text-align:center;
    font-size:18px;
    font-weight:600;
    margin-bottom:10px;
">
Smart Grid Builder
</div>
""", unsafe_allow_html=True)  
st.sidebar.header("Control Panel")
temp, humidity = get_weather()

st.sidebar.write(f"Temp: {temp} °C")
st.sidebar.write(f"Humidity: {humidity}%")

load_value = st.sidebar.slider("Load Demand (kW)", 20, 150, 80)

use_solar = st.sidebar.toggle("Enable Solar", True)
use_wind = st.sidebar.toggle("Enable Wind", True)
use_battery = st.sidebar.toggle("Enable Battery", True)
use_grid = st.sidebar.toggle("Enable Grid", True)

solar_intensity = st.sidebar.slider("Solar Intensity", 0, 100, 70)
wind_speed = st.sidebar.slider("Wind Speed", 0, 15, 5)

t = np.arange(24)

P_solar = np.zeros(24)
if use_solar:
    P_solar = solar_intensity * np.maximum(0, np.sin(np.pi*(t-6)/12))

P_wind = np.zeros(24)
if use_wind:
    P_wind = wind_speed * 4 * np.ones(24)

P_ren = P_solar + P_wind
P_load = load_value + 20*np.sin(np.pi*(t-6)/12) + 10*np.sin(np.pi*(t-18)/12)
P_load = np.maximum(P_load, 20)

# ===== ML LOAD PREDICTION USING WEATHER =====

lr_model = LinearRegression()
nn_model = Sequential()

t = np.arange(24)

# create temperature variation from real temp
temperature_series = temp + 2*np.sin(np.pi*(t-6)/12)

X_lr = np.column_stack((t, temperature_series))
y_lr = P_load

lr_model = LinearRegression()
lr_model.fit(X_lr, y_lr)

predicted_lr = lr_model.predict(X_lr)

X_nn = P_load[:-1].reshape(-1,1)
y_nn = P_load[1:].reshape(-1,1)

# Neural Network (Optimized to MLPRegressor for real-time responsiveness)
nn_model = MLPRegressor(hidden_layer_sizes=(10,), activation="relu", max_iter=200, random_state=42)
nn_model.fit(X_nn, y_nn.ravel())
predicted_nn = nn_model.predict(X_nn)

t_nn = t[1:]

# ===== BATTERY SYSTEM =====
battery_capacity = 100
battery_level = 50
battery_levels = []
battery_store = []
battery_used = []
unmet_load = []
P_from_grid = []
P_spilled = []

# ===== MAIN LOOP =====
for i in range(24):
    load = P_load[i]
    ren = P_ren[i]
    excess = max(ren - load, 0)
    shortage = max(load - ren, 0)
    charge = 0
    discharge = 0
    grid_use = 0
    unserved = 0

    # BATTERY CHARGING
    if use_battery:
        charge = min(excess, battery_capacity - battery_level)
        battery_level += charge

    # BATTERY DISCHARGING
    if use_battery:
        discharge = min(shortage, battery_level)
        battery_level -= discharge

    # GRID / POWER CUT
    if use_grid:
        grid_use = max(shortage - discharge, 0)
    else:
        unserved = max(shortage - discharge, 0)

    # WASTE
    spill = max(excess - charge, 0)

    # STORE VALUES
    battery_levels.append(battery_level)
    battery_store.append(charge)
    battery_used.append(discharge)
    P_from_grid.append(grid_use)
    P_spilled.append(spill)
    unmet_load.append(unserved)

# ===== CONVERT TO NUMPY =====
battery_levels = np.array(battery_levels)
P_from_grid = np.array(P_from_grid)
P_spilled = np.array(P_spilled)
unmet_load = np.array(unmet_load)

# ===== STATUS MESSAGE (ONLY ONCE) =====
total_unmet = np.sum(unmet_load)

if total_unmet > 0:
    st.error(f"POWER CUT! Unserved Energy = {total_unmet:.2f} kW")
else:
    st.success("All demand successfully met")

# ===== STATUS DISPLAY =====
st.markdown("## Simulation Results")
st.write(f"Load Demand: {load_value} kW")
st.write(f"Solar: {'ON' if use_solar else 'OFF'}")
st.write(f"Wind: {'ON' if use_wind else 'OFF'}")
st.write(f"Battery: {'ON' if use_battery else 'OFF'}")
st.write(f"Grid: {'ON' if use_grid else 'OFF'}")

# ===== GRAPHS =====
st.subheader("Energy Source Distribution")
fig, ax = plt.subplots(figsize=(6,3)) 
ax.plot(t, P_load, label="Load", linewidth=2)
ax.plot(t, P_solar, "--", label="Solar")
ax.plot(t, P_wind, "--", label="Wind")
ax.plot(t, battery_used, "--", label="Battery")
ax.plot(t, P_from_grid, "--", label="Grid")

ax.legend()
st.pyplot(fig)
plt.close(fig)

col1, col2 = st.columns(2)
with col1:
    st.subheader("Load vs Renewable")
    fig, ax = plt.subplots()
    ax.plot(t, P_load, label="Load")
    ax.plot(t, P_ren, label="Renewable")
    ax.legend()
    st.pyplot(fig)
    plt.close(fig)

with col2:
    st.subheader("Grid vs Wasted Renewable")
    fig, ax = plt.subplots()
    ax.plot(t, P_from_grid, label="Grid Usage", linewidth=2)
    ax.plot(t, P_spilled, label="Wasted Energy", linewidth=2)
    ax.legend()
    st.pyplot(fig)
    plt.close(fig)

# ===== BATTERY =====
if use_battery:
    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Battery Behavior")
        fig, ax = plt.subplots(figsize=(5,4))   
        ax.plot(t, battery_store, label="Stored")
        ax.plot(t, battery_used, label="Used")
        ax.legend()
        st.pyplot(fig)
        plt.close(fig)

    with col2:
        st.subheader("Battery Level")
        fig, ax = plt.subplots(figsize=(5,4))   
        ax.plot(t, battery_levels, label="Battery Level")
        ax.legend()
        st.pyplot(fig)
        plt.close(fig)

st.subheader("AI Load Forecast vs Actual")

fig, ax = plt.subplots(figsize=(6,3))

ax.plot(t, P_load, label="Actual Load")
# ax.plot(t, predicted_lr, '--', label="Linear Regression")
ax.plot(t_nn, predicted_nn, '--', label="Predicted Load")

ax.legend()
st.pyplot(fig)
plt.close(fig)