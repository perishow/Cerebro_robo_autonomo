from coppeliasim_zmqremoteapi_client import RemoteAPIClient

client = RemoteAPIClient()
sim = client.require('sim')

sim.startSimulation()

cuboid_handle = sim.getObject('/Cuboid')

# Define uma força vetorial [Fx, Fy, Fz] e um torque [Tx, Ty, Tz]
forca_para_aplicar = [1.0, 0.0, 0.0] # 10 Newtons no eixo X
torque_nulo = [0.0, 0.0, 0.0]

# O motor de física precisa receber os comandos a cada passo de simulação
# Você pode fazer isso dentro de um loop enquanto a simulação roda
for _ in range(1):
    # Aplica força no centro de massa (posição e referencial absolutos)
    sim.addForceAndTorque(cuboid_handle, forca_para_aplicar, torque_nulo)
    client.step() # Avança um passo na simulação (útil se estiver em modo síncrono)

sim.stopSimulation()
