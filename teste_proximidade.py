from coppeliasim_zmqremoteapi_client import RemoteAPIClient
import time

# 1. Estabelecer a conexão com o CoppeliaSim
client = RemoteAPIClient()
sim = client.require("sim")

# 2. Obter o "handle" (identificador) do sensor
# Substitua '/ProximitySensor' pelo nome exato que está na hierarquia da sua cena
sensor_path = "/script/sensorProximidade"

try:
    sensor_handle = sim.getObject(sensor_path)
except Exception:
    print(f"Erro ao encontrar o objeto {sensor_path}. Verifique o nome na hierarquia")
    exit()

sim.startSimulation()
print("Simulação iniciada, lendo dados de proximidade")

try:
    while True:
        result, distance, point, obj_handle, normal = sim.readProximitySensor(
            sensor_handle
        )
        print(f"result: {result}")
        print(f"distance: {distance}")
        print(f"point: {point}")
        print(f"obj_handle: {obj_handle}")
        print(f"normal: {normal}")
        time.sleep(0.1)

except KeyboardInterrupt:
    print("\nInterrompido pelo usuário")

finally:
    sim.stopSimulation()
    print("Simulação encerrada")
