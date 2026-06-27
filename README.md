# Smart Grid Builder 

**Live Application:** [https://smart-grid-builder.onrender.com](https://smart-grid-builder.onrender.com)

## About the Project

**Smart Grid Builder** is a full-stack, AI-powered web application that simulates and optimizes modern microgrid energy distribution. By seamlessly integrating renewable energy sources (solar and wind) alongside battery storage and grid consumption, the system intelligently manages power flow to minimize costs and maximize renewable utilization.

The platform utilizes a Machine Learning model (Scikit-Learn `MLPRegressor`) to predict 24-hour power loads. It goes a step further by implementing **Time-of-Use (ToU) Pricing Optimization**, ensuring that batteries charge during cheap off-peak hours and discharge during expensive peak hours. 

## Key Features

* **AI Load Forecasting:** Deep learning model predicts future power demands over a 24-hour cycle.
* **Time-of-Use Cost Optimization:** Smart heuristic algorithms dynamically shift battery discharging to peak-price hours, visualizing thousands of dollars in potential savings.
* **Real-Time Weather Integration:** Fetches live cloud cover and wind speed from the OpenWeatherMap API to dynamically calculate realistic solar and wind energy generation.
* **Custom CSV Data Processing:** Upload your own historical energy demand CSV files. The application parses the data in real-time and runs custom simulations against your specific load profiles.
* **Persistent History:** Backed by an SQLite database, every simulation is recorded and available for review in the History dashboard.

## Tech Stack

* **Backend:** Python, Flask, Pandas, SQLite
* **Machine Learning:** Scikit-Learn (`MLPRegressor`, `LinearRegression`), NumPy
* **Frontend:** Vanilla JavaScript, HTML5, CSS3, Chart.js
* **Deployment:** Docker, Gunicorn, Render

## How to Run Locally

### 1. Clone the repository
```bash
git clone https://github.com/your-username/smart-grid-builder.git
cd smart-grid-builder
```

### 2. Install dependencies
Ensure you are using Python 3.10+ (Python 3.12 recommended).
```bash
pip install -r requirements.txt
```

### 3. Run the application
Start the Flask server:
```bash
python app.py
```
Open your browser and navigate to `http://localhost:5000`


## Using the CSV Upload Feature

You can upload your own custom load profiles to simulate how the grid would handle your specific power demands. 

Your CSV file must contain a column named `load` or `demand` with numerical kW values representing 24 hours of data.

**Example CSV Format (`my_data.csv`):**
```csv
Time,Load
00:00,45.2
01:00,42.1
02:00,40.5
03:00,38.9
... (up to 24 rows)
```
Upload this file using the **Custom Data Prediction** section on the dashboard, and the AI will recalculate the simulation based on your curve!
