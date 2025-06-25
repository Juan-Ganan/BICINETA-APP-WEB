from flask import Flask, request, jsonify, render_template, redirect, url_for, session
import paho.mqtt.client as mqtt
import ssl
import json
from collections import defaultdict
from datetime import datetime
import numpy as np
import pandas as pd
import os
import threading
import time

# === CONFIGURACIÓN GENERAL ===
app = Flask(__name__)
app.secret_key = 'super_secret_key'  # Necesario para sesiones
USERS = {'admin': 'password123'}
CSV_FILE = "sensor_data.csv"
ESTADO_FILE = "estado.json"

# === CONFIGURACIÓN MQTT ===
MQTT_BROKER = "02c9970343eb456bac87e5836a2905c3.s1.eu.hivemq.cloud"
MQTT_PORT = 8883
MQTT_USERNAME = "GCA_DAQ"
MQTT_PASSWORD = "#Control2005"
MQTT_TOPICS = [
    "voltage", "current", "speed", "acceleration",
    "temperature", "altitud", "latitude", "longitude"
]
MQTT_TOPIC_PUB = "control/commands"

# === VARIABLES DE ESTADO ===
sensor_data = defaultdict(lambda: [])
digital_twin_data = defaultdict(lambda: [])
MAX_POINTS = 50
latest_values = {topic: {"value": None, "timestamp": None} for topic in MQTT_TOPICS}
latest_predictions = {"predicted_current": None, "predicted_speed": None}
current1 = speed1 = voltage1 = acceleration1 = map1 = 0
global_data_collection_enabled = False

# === MATRIZ DEL GEMELO DIGITAL ===
theta = np.array([
    [-0.95,  0.00],
    [-1.84, -0.56],
    [ 0.10, -0.00],
    [ 0.49, -0.23],
    [14.28,  0.42],
    [-2.94, -0.07],
    [-0.50,  0.08],
    [ 5.42, -0.70],
    [ 3.93,  0.10],
    [ 0.48, -0.08]
])

# === FUNCIONES DE PERSISTENCIA DE ESTADO ===
def cargar_estado_desde_json():
    global global_data_collection_enabled
    if os.path.exists(ESTADO_FILE):
        with open(ESTADO_FILE, 'r') as f:
            estado = json.load(f)
            global_data_collection_enabled = estado.get("enabled", False)
    else:
        global_data_collection_enabled = False

def guardar_estado_en_json(enabled):
    with open(ESTADO_FILE, 'w') as f:
        json.dump({"enabled": enabled}, f)

# === FUNCIONES DEL GEMELO DIGITAL ===
def compute_digital_twin():
    global current1, speed1, voltage1, acceleration1, map1
    Y = np.array([[speed1, current1, speed1, current1]])
    U = np.array([[acceleration1, voltage1, map1, acceleration1, voltage1, map1]])
    H = np.hstack((-Y, U))
    Yest = H @ theta
    return Yest

# === FUNCIONES DE ALMACENAMIENTO DE DATOS ===
def save_to_csv():
    if not global_data_collection_enabled:
        return

    data_row = {
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "voltage": latest_values["voltage"]["value"],
        "current": latest_values["current"]["value"],
        "speed": latest_values["speed"]["value"],
        "acceleration": latest_values["acceleration"]["value"],
        "temperature": latest_values["temperature"]["value"],
        "altitud": latest_values["altitud"]["value"],
        "latitude": latest_values["latitude"]["value"],
        "longitude": latest_values["longitude"]["value"],
        "predicted_current": latest_predictions["predicted_current"],
        "predicted_speed": latest_predictions["predicted_speed"]
    }

    df = pd.DataFrame([data_row])
    if not os.path.exists(CSV_FILE):
        df.to_csv(CSV_FILE, index=False)
    else:
        df.to_csv(CSV_FILE, mode='a', header=False, index=False)
    print(f"Datos guardados en {CSV_FILE}: {data_row}")

def periodic_csv_writer():
    while True:
        if any(latest_values[topic]["value"] is not None for topic in MQTT_TOPICS):
            save_to_csv()
        time.sleep(10)

# === MQTT ===
def on_connect(client, userdata, flags, rc):
    print(f"Código de conexión: {rc}")
    if rc == 0:
        print("Conectado al broker MQTT")
        for topic in MQTT_TOPICS:
            client.subscribe(topic)
            print(f"Suscrito a {topic}")
    else:
        print(f"Fallo en la conexión, código: {rc}")

def on_message(client, userdata, msg):
    global current1, speed1, voltage1, acceleration1, map1
    try:
        value = float(msg.payload.decode())
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        sensor_data[msg.topic].append({"time": timestamp, "value": value})
        if len(sensor_data[msg.topic]) > MAX_POINTS:
            sensor_data[msg.topic].pop(0)

        latest_values[msg.topic]["value"] = value
        latest_values[msg.topic]["timestamp"] = timestamp

        if msg.topic == "current":
            current1 = value
        elif msg.topic == "speed":
            speed1 = value
        elif msg.topic == "voltage":
            voltage1 = value
        elif msg.topic == "acceleration":
            acceleration1 = value
        elif msg.topic == "altitud":
            map1 = value

        print(f"{msg.topic} -> {value}")

        if all([latest_values[topic]["value"] is not None for topic in ["voltage", "acceleration", "altitud"]]):
            Yest = compute_digital_twin()
            latest_predictions["predicted_current"] = Yest[0, 1]
            latest_predictions["predicted_speed"] = Yest[0, 0]
            digital_twin_data["predicted_current"].append({"time": timestamp, "value": Yest[0, 1]})
            digital_twin_data["predicted_speed"].append({"time": timestamp, "value": Yest[0, 0]})
            if len(digital_twin_data["predicted_current"]) > MAX_POINTS:
                digital_twin_data["predicted_current"].pop(0)
            if len(digital_twin_data["predicted_speed"]) > MAX_POINTS:
                digital_twin_data["predicted_speed"].pop(0)
            print(f"Predicciones: current={Yest[0, 1]}, speed={Yest[0, 0]}")
        else:
            print("Faltan datos para la predicción")

        save_to_csv()
    except ValueError:
        print(f"Valor no numérico recibido en {msg.topic}: {msg.payload.decode()}")

# === INICIALIZACIÓN MQTT Y HILO ===
cargar_estado_desde_json()

client = mqtt.Client()
client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)
client.tls_set(tls_version=ssl.PROTOCOL_TLS)
client.on_connect = on_connect
client.on_message = on_message

try:
    client.connect(MQTT_BROKER, MQTT_PORT, 60)
    client.loop_start()
except Exception as e:
    print(f"Error al conectar al broker: {e}")

threading.Thread(target=periodic_csv_writer, daemon=True).start()

# === RUTAS FLASK ===
@app.route('/', methods=['GET', 'POST'])
def login():
    global global_data_collection_enabled
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        if username in USERS and USERS[username] == password:
            session['logged_in'] = True
            session['data_collection_enabled'] = global_data_collection_enabled
            return redirect(url_for('menu'))
        else:
            return render_template('login.html', error="Credenciales inválidas")
    return render_template('login.html')

@app.route('/toggle_data_collection', methods=['POST'])
def toggle_data_collection():
    global global_data_collection_enabled
    if not session.get('logged_in'):
        return jsonify({"error": "No autenticado"}), 401
    enabled = session.get('data_collection_enabled', global_data_collection_enabled)
    new_status = not enabled
    session['data_collection_enabled'] = new_status
    global_data_collection_enabled = new_status
    guardar_estado_en_json(new_status)
    return jsonify({"enabled": new_status})

@app.route('/get_data_collection_status', methods=['GET'])
def get_data_collection_status():
    if not session.get('logged_in'):
        return jsonify({"error": "No autenticado"}), 401
    return jsonify({"enabled": session.get('data_collection_enabled', False)})

@app.route('/menu')
def menu():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('menu.html')

@app.route('/general_info')
def general_info():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('general_info.html')

@app.route('/acceleration')
def acceleration():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('acceleration.html')

@app.route('/voltage')
def voltage():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('voltage.html')

@app.route('/current')
def current():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('current.html')

@app.route('/temperature')
def temperature():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('temperature.html')

@app.route('/speed')
def speed():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('speed.html')

@app.route('/location')
def location():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('location.html')

@app.route('/digital_twin')
def digital_twin():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('digital_twin.html')

@app.route('/settings')
def settings():
    if not session.get('logged_in'):
        return redirect(url_for('login'))
    return render_template('settings.html')

@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    session.pop('data_collection_enabled', None)
    return redirect(url_for('login'))

@app.route('/publish', methods=['POST'])
def publish_message():
    if not session.get('logged_in'):
        return jsonify({"error": "No autenticado"}), 401
    data = request.get_json()
    topic = data.get('topic', MQTT_TOPIC_PUB)
    message = data.get('message')
    if not message:
        return jsonify({"error": "Mensaje vacío"}), 400
    result = client.publish(topic, message)
    if result.rc == mqtt.MQTT_ERR_SUCCESS:
        return jsonify({"status": "Mensaje publicado", "topic": topic, "message": message})
    else:
        return jsonify({"error": "Fallo al publicar mensaje"}), 500

@app.route('/data', methods=['GET'])
def get_data():
    if not session.get('logged_in'):
        return jsonify({"error": "No autenticado"}), 401
    return jsonify(dict(sensor_data))

@app.route('/digital_twin_data', methods=['GET'])
def get_digital_twin_data():
    if not session.get('logged_in'):
        return jsonify({"error": "No autenticado"}), 401
    return jsonify(dict(digital_twin_data))

# === MAIN ===
if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5000)
