from coppeliasim_zmqremoteapi_client import RemoteAPIClient
import time
import math

client = RemoteAPIClient()
sim = client.require("sim")

gyro_path = "/script/GyroSensor"
prox_path = "/script/sensorProximidade"

try:
    gyro_handle = sim.getObject(gyro_path)
except Exception:
    print(f"Erro ao encontrar o objeto {gyro_path}")

try:
    prox_handle = sim.getObject(prox_path)
except Exception:
    print(f"Erro ao encontrar o objeto {prox_path}")

sim.startSimulation()
print("Simulação iniciada, lendo dados do giroscópio e proximidade")

try:
    contador = 0
    tempo_pausa = 0.5

    while contador <= 2:
        lin_vel, ang_vel = sim.getObjectVelocity(gyro_handle)
        wx_deg = math.degrees(ang_vel[0])
        wy_deg = math.degrees(ang_vel[1])
        wz_deg = math.degrees(ang_vel[2])

        result, distance, _, _, _ = sim.readProximitySensor(prox_handle)

        print(f"Gyro:\n   x_deg: {wx_deg}\n   y_deg: {wy_deg}\n   z_deg: {wz_deg}")
        print(f"Prox:\n   result: {result}\n   distance: {distance}")

        print("---" * 10)
        contador += tempo_pausa
        time.sleep(tempo_pausa)
except KeyboardInterrupt:
    print("\nInterrompido pelo usuário")

finally:
    sim.stopSimulation()
    print("Simulação encerrada.")
