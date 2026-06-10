from coppeliasim_zmqremoteapi_client import RemoteAPIClient
import time # Adicionado para dar um "respiro" no loop
import math

def bueiro_routine(obj_handler):
    limite_radianos = math.radians(90)
    passo_angular = 0.05
    try:
        print("Rotina de Bueiro em andamento, vai segurando papoi")
        ori = sim.getObjectOrientation(obj_handler)
        contador = 0
        while contador < limite_radianos:
            ori[2] += passo_angular
            contador += passo_angular
            sim.setObjectOrientation(cuboid_handle, sim.handle_world, ori)
        time.sleep(1)

        contador = 0
        while contador < limite_radianos:
            ori[2] -= passo_angular
            contador += passo_angular
            sim.setObjectOrientation(cuboid_handle, sim.handle_world, ori)
        time.sleep(1)
        contador = 0
        while contador < limite_radianos:
            ori[2] -= passo_angular
            contador += passo_angular
            sim.setObjectOrientation(cuboid_handle, sim.handle_world, ori)
        time.sleep(1)
    except KeyboardInterrupt:
        pass

client = RemoteAPIClient()
sim = client.require('sim')

prox_superior_path = "/Cuboid[0]/proximidade_superior"

try:
    prox_superior_handle = sim.getObject(prox_superior_path)
except Exception:
    print(f"Erro ao encontrar o objeto {prox_superior_path}")

sim.startSimulation()
cuboid_handle = sim.getObject('/Cuboid')

# tempo para o motor de física aquecer
time.sleep(0.5)

print("Cerebro rodando, o robô vai fazer coisas fodas")

passo_linear = 0.05

try:
    while True:
        # Coleta de dados segura (evita o crash caso o sensor retorne menos variáveis)
        sensor_data = sim.readProximitySensor(prox_superior_handle)
        result = sensor_data[0] # 1 se detectou, 0 se não detectou
        
        # Pega a posição atual
        pos = sim.getObjectPosition(cuboid_handle, sim.handle_world)
        
        if result > 0:
            pos[1] += passo_linear
            
            # --- A LINHA MÁGICA QUE FALTAVA ---
            # Envia a nova posição de volta para o CoppeliaSim
            sim.setObjectPosition(cuboid_handle, sim.handle_world, pos)
            
            print("andei kkkk")
        else:
            bueiro_routine(cuboid_handle)
        client.step() # Mantém a sincronia com o simulador
        time.sleep(0.05) # Pausa de 50ms para não floodar e travar o terminal

except KeyboardInterrupt:
    pass
finally:
    sim.stopSimulation()


