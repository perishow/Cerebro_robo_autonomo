from coppeliasim_zmqremoteapi_client import RemoteAPIClient
import time
import math
import traceback

from motor_grafo.grafo_modulo import Grafo


class ControladorRobo:
    def __init__(self, mapa_grafo, no_inicial):
        self.mapa = mapa_grafo
        self.no_atual = no_inicial
        self.pilha_caminho = []

        self.mapa.atualizar_status_no(self.no_atual, "visitado")

    def decidir_proximo_passo(self):
        print(f"\n[Cérebro] Pensando... Estou no nó: {self.no_atual}")
        vizinhos = self.mapa.grafo.get(self.no_atual, {})

        # 1. Tenta encontrar um caminho inédito e livre
        for vizinho, dados_via in vizinhos.items():
            status_via = dados_via["status"]
            # status_no = self.mapa.nos[vizinho]["status"]
            status_no = self.mapa.nos.get(vizinho, {}).get("status", "não visitado")

            if status_via == "livre" and status_no == "não visitado":
                print(
                    f"  -> Decisão: Caminho inédito encontrado para {vizinho}!")
                self.pilha_caminho.append(self.no_atual)
                self.no_atual = vizinho
                self.mapa.atualizar_status_no(vizinho, "visitado")
                return vizinho

        # 2. Beco sem saída ou tudo visitado ao redor. Precisa recuar (Backtracking)
        print("  -> Decisão: Beco sem saída ou tudo visitado ao redor.")
        if self.pilha_caminho:
            no_destino = self.pilha_caminho.pop()
            print(f"  -> Decisão: Backtracking solicitado para: {no_destino}")

            # Checa se a conexão é direta (Duto -> Bueiro)
            if no_destino in self.mapa.grafo.get(self.no_atual, {}):
                self.no_atual = no_destino
                return no_destino

            # Se não for direta (Bueiro -> Bueiro), procura o Duto que liga os dois
            for duto_intermediario in self.mapa.grafo.get(self.no_atual, {}):
                if no_destino in self.mapa.grafo.get(duto_intermediario, {}):
                    print(
                        f"  -> Caminho indireto: Usando {
                            duto_intermediario
                        } para chegar em {no_destino}"
                    )
                    # Devolve o destino final pra pilha, pois agora daremos 1 passo até o duto
                    self.pilha_caminho.append(no_destino)
                    self.no_atual = duto_intermediario
                    return duto_intermediario

            # Fallback (Garante que a variável atualiza mesmo em erro)
            self.no_atual = no_destino
            return no_destino

        # 3. Fim da linha
        print("  -> Decisão: Exploração concluída! Não há mais para onde ir.")
        return None


def sim_sleep(sim, client, duration_in_seconds):
    """Pausa a execução passando o tempo dentro do simulador"""
    start_time = sim.getSimulationTime()
    while sim.getSimulationTime() - start_time < duration_in_seconds:
        client.step()


def calcular_distancia(pos1, pos2):
    """Calcula a distância espacial Euclidiana no plano X e Y"""
    return math.sqrt((pos1[0] - pos2[0]) ** 2 + (pos1[1] - pos2[1]) ** 2)


def avalia_duto(frontal_handler, grafo, sim, no_atual, id_destino, angulo_atual):
    sensor_data = sim.readProximitySensor(frontal_handler)
    result_frontal = sensor_data[0]

    if result_frontal > 0:
        print(f"  -> Parede detectada. Caminho ignorado.")
    elif result_frontal == 0:
        novo_no = f"{no_atual}_Duto_{id_destino}"
        grafo.adicionar_conexao(
            origem=no_atual, destino=novo_no, status="livre")

        # Salva o ângulo na aresta para o robô saber para onde virar na ida
        grafo.grafo[no_atual][novo_no]["angulo"] = angulo_atual
        if not grafo.direcionado:
            # O caminho de volta saindo do duto pro bueiro é a direção oposta (+ pi)
            grafo.grafo[novo_no][no_atual]["angulo"] = angulo_atual + math.pi

        print(f"  -> Duto livre! Conexão criada: {no_atual} <---> {novo_no}")


def bueiro_routine(
    obj_handler, passo_linear, sim, client, frontal_handler, grafo, controlador
):
    limite_radianos = math.radians(90)
    passo_angular = 0.05
    no_atual = controlador.no_atual

    try:
        # Continua em frente para centralizar no meio do bueiro
        ori = sim.getObjectOrientation(obj_handler, sim.handle_world)
        for i in range(9):
            pos = sim.getObjectPosition(obj_handler, sim.handle_world)
            pos[0] -= passo_linear * math.sin(ori[2])
            pos[1] += passo_linear * math.cos(ori[2])
            sim.setObjectPosition(obj_handler, sim.handle_world, pos)
            client.step()
            sim_sleep(sim, client, 0.2)
        
        print(f"\n--- Rotina de Bueiro Iniciada em: {no_atual} ---")
        ori = sim.getObjectOrientation(obj_handler, sim.handle_world)

        # Mapeando Esquerda (+90)
        contador = 0
        while contador < limite_radianos:
            ori[2] += passo_angular
            contador += passo_angular
            sim.setObjectOrientation(obj_handler, sim.handle_world, ori)
            client.step()
        sim_sleep(sim, client, 0.5)
        avalia_duto(frontal_handler, grafo, sim, no_atual, "Esq", ori[2])

        # Mapeando Frente (Volta aos 0 relativos)
        contador = 0
        while contador < limite_radianos:
            ori[2] -= passo_angular
            contador += passo_angular
            sim.setObjectOrientation(obj_handler, sim.handle_world, ori)
            client.step()
        sim_sleep(sim, client, 0.5)
        avalia_duto(frontal_handler, grafo, sim, no_atual, "Frente", ori[2])

        # Mapeando Direita (-90)
        contador = 0
        while contador < limite_radianos:
            ori[2] -= passo_angular
            contador += passo_angular
            sim.setObjectOrientation(obj_handler, sim.handle_world, ori)
            client.step()
        sim_sleep(sim, client, 0.5)
        avalia_duto(frontal_handler, grafo, sim, no_atual, "Dir", ori[2])

        # ========================================================
        # HORA DA DECISÃO!
        # ========================================================
        proximo_destino = controlador.decidir_proximo_passo()

        if proximo_destino:
            # Busca o ângulo armazenado no grafo para o destino escolhido
            angulo_alvo = grafo.grafo[no_atual][proximo_destino].get(
                "angulo", 0)

            print(
                f"[{no_atual}] Virando o corpo fisicamente para {
                    proximo_destino
                } (Ângulo: {angulo_alvo:.2f} rad)..."
            )
            ori = sim.getObjectOrientation(obj_handler, sim.handle_world)
            ori[2] = angulo_alvo
            sim.setObjectOrientation(obj_handler, sim.handle_world, ori)
            client.step()
            sim_sleep(sim, client, 0.5)

            # Dá os passos iniciais para ENTRAR no duto escolhido
            for _ in range(20):
                pos = sim.getObjectPosition(obj_handler, sim.handle_world)
                pos[0] -= passo_linear * math.sin(ori[2])
                pos[1] += passo_linear * math.cos(ori[2])
                sim.setObjectPosition(obj_handler, sim.handle_world, pos)
                client.step()
                sim_sleep(sim, client, 0.2)
        else:
            print("Robô explorou todo o labirinto navegável. Desligando motores!")
            sim.stopSimulation()

    except KeyboardInterrupt:
        try:
            sim.stopSimulation()
        except Exception:
            pass # Ignora se a conexão ZMQ já estiver quebrada pelo Ctrl+C


# SETUP INICIAL ===========================================
client = RemoteAPIClient()
client.setStepping(True)
sim = client.require("sim")

passo_linear = 0.1
estado = "Duto"
grafo = Grafo()

prox_superior_path = "/Cuboid/proximidade_superior"
prox_frontal_path = "/Cuboid/proximidade_frontal"

try:
    prox_superior_handle = sim.getObject(prox_superior_path)
    prox_frontal_handle = sim.getObject(prox_frontal_path)
except Exception as e:
    print(f"Erro ao encontrar sensor: {e}")

# Memória de Coordenadas para curar a Amnésia Espacial
coordenadas_bueiros = {}
contador_bueiros = 1
bueiro_inicial = f"Bueiro_{contador_bueiros}"
controlador = ControladorRobo(grafo, bueiro_inicial)

grafo.adicionar_no(bueiro_inicial)
controlador = ControladorRobo(grafo, bueiro_inicial)

sim.startSimulation()
cuboid_handle = sim.getObject("/Cuboid")

# Mapeia a coordenada do bueiro de partida logo após dar play
coordenadas_bueiros[bueiro_inicial] = sim.getObjectPosition(
    cuboid_handle, sim.handle_world
)

while sim.getSimulationTime() < 1:
    client.step()
print("Cerebro rodando, o robô vai fazer coisas fodas")

# CAMINHADA INICIAL =======================================
try:
    for i in range(30):
        pos = sim.getObjectPosition(cuboid_handle, sim.handle_world)
        pos[1] += passo_linear
        sim.setObjectPosition(cuboid_handle, sim.handle_world, pos)
        sim_sleep(sim, client, 0.2)

except KeyboardInterrupt:
    sim.stopSimulation()

# LOOP PRINCIPAL ==============================================
try:
    while True:
        sensor_data = sim.readProximitySensor(prox_superior_handle)
        result_superior = sensor_data[0]

        if result_superior > 0:
            estado = "Duto"
        elif result_superior == 0:
            # Se acabou de sair de um duto para um bueiro
            if estado == "Duto":
                pos_atual = sim.getObjectPosition(
                    cuboid_handle, sim.handle_world)
                bueiro_reconhecido = None

                # Checa se este ponto físico já foi mapeado antes (tolerância de 30cm)
                for nome_conhecido, coord_salva in coordenadas_bueiros.items():
                    if calcular_distancia(pos_atual, coord_salva) < 0.3:
                        bueiro_reconhecido = nome_conhecido
                        break

                duto_anterior = controlador.no_atual  # Duto de onde o robô veio

                if bueiro_reconhecido:
                    bueiro_atual = bueiro_reconhecido
                    print(
                        f"\n-> [Memória] Local conhecido identificado! Retornando ao {
                            bueiro_atual
                        }"
                    )
                else:
                    contador_bueiros += 1
                    bueiro_atual = f"Bueiro_{contador_bueiros}"
                    coordenadas_bueiros[bueiro_atual] = pos_atual
                    print(
                        f"\n-> [Descoberta] Novo local descoberto e batizado de: {
                            bueiro_atual
                        }"
                    )

                # Conecta o duto de onde veio ao bueiro que acabou de entrar
                grafo.adicionar_conexao(
                    duto_anterior, bueiro_atual, status="livre")

                # Salva o ângulo de volta para permitir o Backtracking correto
                # O ângulo necessário para voltar pelo duto é o oposto da orientação atual (+ pi)
                ori_atual = sim.getObjectOrientation(
                    cuboid_handle, sim.handle_world)
                angulo_de_volta = ori_atual[2] + math.pi

                if bueiro_atual not in grafo.grafo:
                    grafo.adicionar_no(bueiro_atual)
                if duto_anterior not in grafo.grafo[bueiro_atual]:
                    grafo.grafo[bueiro_atual][duto_anterior] = {
                        "status": "livre"}

                grafo.grafo[bueiro_atual][duto_anterior]["angulo"] = angulo_de_volta

                # Atualiza a posição atual na mente do robô
                controlador.no_atual = bueiro_atual

            estado = "Bueiro"
        else:
            print("Erro Crítico no Sensor Superior!")
            sim.stopSimulation()
            break

        if estado == "Duto":
            ori = sim.getObjectOrientation(cuboid_handle, sim.handle_world)
            pos = sim.getObjectPosition(cuboid_handle, sim.handle_world)
            # Avança na direção em que o robô está rotacionado
            pos[0] -= passo_linear * math.sin(ori[2])
            pos[1] += passo_linear * math.cos(ori[2])
            sim.setObjectPosition(cuboid_handle, sim.handle_world, pos)

        elif estado == "Bueiro":
            bueiro_routine(
                cuboid_handle,
                passo_linear,
                sim,
                client,
                prox_frontal_handle,
                grafo,
                controlador,
            )
            print("\n--- Mapeamento Atualizado ---")
            grafo.mostrar_grafo()

        client.step()
        time.sleep(0.05)

except KeyboardInterrupt:
    print("\n[Sistema] Simulação interrompida pelo usuário (Ctrl+C).")
except Exception as e:
    print("\n[ERRO CRÍTICO] O Cérebro deu tela azul:")
    traceback.print_exc()
finally:
    try:
        sim.stopSimulation()
    except Exception:
        pass # Fecha calado se o ZMQ não deixar
