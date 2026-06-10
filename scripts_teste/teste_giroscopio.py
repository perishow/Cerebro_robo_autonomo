from coppeliasim_zmqremoteapi_client import RemoteAPIClient
import time
import math

client = RemoteAPIClient()
sim = client.require("sim")

gyro_path = "/GyroSensor"
try:
    gyro_handle = sim.getObject(gyro_path)
except Exception:
    print(f"Erro ao encontrar o objeto {gyro_path}. Verifique o nome na hierarquia")
    exit()

sim.startSimulation()
print("Simulação iniada, lendo dados do giroscópio")

try:
    while True:
        lin_vel, ang_vel = sim.getObjectVelocity(gyro_handle)
        wx_deg = math.degrees(ang_vel[0])
        wy_deg = math.degrees(ang_vel[1])
        wz_deg = math.degrees(ang_vel[2])

        # 5. Printar os resultados formatados com 2 casas decimais
        print(
            f"Vel. Angular (°/s) -> X: {wx_deg:+06.2f} | Y: {wy_deg:+06.2f} | Z: {
                wz_deg:+06.2f}"
        )

        # Pequena pausa para acompanhar os passos físicos da simulação
        time.sleep(0.05)
except KeyboardInterrupt:
    print("\nInterrompido pelo usuário.")

finally:
    # 6. Parar simulação e limpar tudo
    sim.stopSimulation()
    print("Simulação encerrada.")
