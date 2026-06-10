from coppeliasim_zmqremoteapi_client import RemoteAPIClient
import keyboard 

client = RemoteAPIClient()
sim = client.require('sim')

sim.startSimulation()
cuboid_handle = sim.getObject('/Cuboid')

print("Use 'W', 'A', 'S', 'D' para mover o objeto no plano horizontal.")
print("Use 'Q' e 'E' para rotacionar (girar no eixo Z).")
print("Pressione 'ESC' para sair.")

try:
    while True:
        # Pega a posição (X, Y, Z) e a orientação (alfa, beta, gama) atuais
        pos = sim.getObjectPosition(cuboid_handle, sim.handle_world)
        ori = sim.getObjectOrientation(cuboid_handle, sim.handle_world)
        
        passo_linear = 0.05  # Velocidade do movimento (metros)
        passo_angular = 0.05 # Velocidade da rotação (radianos, aprox. 2.8 graus)
        
        moveu = False
        rotacionou = False 

        # --- CONTROLE DE TRANSLAÇÃO (X e Y) ---
        if keyboard.is_pressed('w'):
            pos[1] += passo_linear
            moveu = True
        if keyboard.is_pressed('s'):
            pos[1] -= passo_linear
            moveu = True
        if keyboard.is_pressed('a'):
            pos[0] -= passo_linear
            moveu = True
        if keyboard.is_pressed('d'):
            pos[0] += passo_linear
            moveu = True
            
        # --- CONTROLE DE ROTAÇÃO (Giro no eixo Z) ---
        # O índice 2 da lista 'ori' corresponde à rotação ao redor do eixo Z (gama)
        if keyboard.is_pressed('q'):
            ori[2] += passo_angular # Gira no sentido anti-horário
            rotacionou = True
        if keyboard.is_pressed('e'):
            ori[2] -= passo_angular # Gira no sentido horário
            rotacionou = True
            
        if keyboard.is_pressed('esc'):
            break 

        # --- APLICA AS MUDANÇAS NO SIMULADOR ---
        if moveu:
            sim.setObjectPosition(cuboid_handle, sim.handle_world, pos)
        if rotacionou:
            sim.setObjectOrientation(cuboid_handle, sim.handle_world, ori)

        client.step() 

except KeyboardInterrupt:
    pass

finally:
    sim.stopSimulation()
