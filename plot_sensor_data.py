import pandas as pd
import matplotlib.pyplot as plt
import os

# Ruta al archivo CSV
CSV_FILE = "D:/Backend-MQTT/sensor_data.csv"

# Nombres de las columnas
COLUMNS = [
    "timestamp", "voltage", "current", "speed", "acceleration", 
    "temperature", "altitud", "predicted_current", "predicted_speed"
]

def plot_sensor_data():
    # Verificar si el archivo existe
    if not os.path.exists(CSV_FILE):
        print(f"Error: No se encontró el archivo {CSV_FILE}")
        return
    
    # Leer el CSV, especificando los nombres de las columnas
    try:
        df = pd.read_csv(CSV_FILE, header=None, names=COLUMNS)
        # Convertir timestamp a formato datetime
        df['timestamp'] = pd.to_datetime(df['timestamp'])
    except Exception as e:
        print(f"Error al leer el CSV: {e}")
        return
    
    # Verificar si el DataFrame tiene datos
    if df.empty:
        print("Error: El CSV está vacío")
        return
    
    # Crear una figura con subplots (uno por cada columna, excepto timestamp)
    plot_columns = COLUMNS[1:]  # Excluir timestamp
    fig, axes = plt.subplots(len(plot_columns), 1, figsize=(12, 4 * len(plot_columns)), sharex=True)
    
    # Asegurarse de que axes sea una lista incluso si hay una sola columna
    if len(plot_columns) == 1:
        axes = [axes]
    
    # Graficar cada columna
    for i, column in enumerate(plot_columns):
        if column in df.columns:
            axes[i].plot(df['timestamp'], df[column], label=column, color='blue', marker='o', markersize=4)
            axes[i].set_title(column.capitalize(), fontsize=12)
            axes[i].set_ylabel(column, fontsize=10)
            axes[i].legend()
            axes[i].grid(True)
        else:
            print(f"Advertencia: La columna {column} no está en el CSV")
    
    # Configurar el eje x (común)
    axes[-1].set_xlabel("Timestamp", fontsize=12)
    plt.gca().xaxis.set_major_formatter(plt.matplotlib.dates.DateFormatter('%Y-%m-%d %H:%M:%S'))
    plt.xticks(rotation=45)
    
    # Ajustar el diseño para evitar solapamiento
    plt.tight_layout()
    
    # Mostrar el gráfico
    plt.show()

if __name__ == "__main__":
    plot_sensor_data()