from coppeliasim_zmqremoteapi_client import RemoteAPIClient
import time

# 1. Conecta ao CoppeliaSim (certifique-se de que a simulação está aberta)
client = RemoteAPIClient()
sim = client.require('sim')

# Inicia a simulação (opcional, dependendo de como você quer rodar)
sim.startSimulation()

# 2. Obtém o handle (referência) do cuboid. 
# Importante: o nome deve corresponder exatamente ao que está na hierarquia (Scene Hierarchy) do CoppeliaSim.
cuboid_handle = sim.getObject('/Cuboid')

# 3. Obtém a posição atual do objeto em relação ao mundo (sim.handle_world = -1)
posicao_atual = sim.getObjectPosition(cuboid_handle, sim.handle_world)
print(f"Posição atual: {posicao_atual}")

# 4. Define uma nova posição [X, Y, Z]
nova_posicao = [posicao_atual[0] + 0.5, posicao_atual[1], posicao_atual[2]]

# 5. Move o objeto
sim.setObjectPosition(cuboid_handle, sim.handle_world, nova_posicao)
print(f"Objeto movido para: {nova_posicao}")

time.sleep(2) # Pausa para você ver o objeto movido antes de parar

# Para a simulação
sim.stopSimulation()
