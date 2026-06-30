from coppeliasim_zmqremoteapi_client import RemoteAPIClient
import os
import time
import math
import traceback
import struct

from motor_grafo.grafo_modulo import Grafo
from motor_grafo.servidor_visualizacao import (
    ServidorVisualizacaoGrafo,
    salvar_snapshot_grafo,
    FOTOS_DIR,
)

def capturar_foto(sim, camera_handle, nome_duto):
    """Captura imagem do Vision Sensor e salva como PNG na pasta fotos/."""
    try:
        img, [w, h] = sim.getVisionSensorImg(camera_handle)
        # img é bytes RGB row-major; precisa inverter verticalmente (OpenGL origin)
        row_size = w * 3
        rows = [img[i * row_size:(i + 1) * row_size] for i in range(h)]
        rows.reverse()
        pixels = b"".join(rows)

        # Escreve PNG mínimo sem dependências externas
        import zlib, struct

        def png_chunk(chunk_type, data):
            c = chunk_type + data
            return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

        raw_rows = b"".join(b"\x00" + pixels[i * row_size:(i + 1) * row_size] for i in range(h))
        compressed = zlib.compress(raw_rows, 9)

        png = (
            b"\x89PNG\r\n\x1a\n"
            + png_chunk(b"IHDR", struct.pack(">IIBBBBB", w, h, 8, 2, 0, 0, 0))
            + png_chunk(b"IDAT", compressed)
            + png_chunk(b"IEND", b"")
        )

        nome_arquivo = f"{nome_duto.replace('/', '_')}.png"
        caminho = FOTOS_DIR / nome_arquivo
        FOTOS_DIR.mkdir(parents=True, exist_ok=True)
        caminho.write_bytes(png)
        print(f"[Câmera] Foto salva: {caminho}")
        return nome_arquivo
    except Exception as e:
        print(f"[Câmera] Falha ao capturar foto: {e}")
        return None


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
            status_no = self.mapa.nos.get(vizinho, {}).get("status", "não visitado")

            if status_via == "livre" and status_no == "não visitado":
                print(f"  -> Decisão: Caminho inédito encontrado para {vizinho}!")
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

                    # CORREÇÃO: O append maldito foi removido daqui!
                    self.no_atual = duto_intermediario
                    return duto_intermediario

            # Fallback
            self.no_atual = no_destino
            return no_destino

        # 3. Fim da linha (Retornou ao início)
        print("  -> Decisão: Exploração concluída! Retornamos ao ponto inicial.")
        return None


def sim_sleep(sim, client, duration_in_seconds):
    start_time = sim.getSimulationTime()
    while sim.getSimulationTime() - start_time < duration_in_seconds:
        client.step()


def calcular_distancia(pos1, pos2):
    return math.sqrt((pos1[0] - pos2[0]) ** 2 + (pos1[1] - pos2[1]) ** 2)

def normalizar_angulo(angulo):
    """Mantém o ângulo entre -pi e +pi para evitar acumular giros."""
    return math.atan2(math.sin(angulo), math.cos(angulo))


def ler_proximidade(sim, sensor_handle):
    """
    Retorna uma leitura normalizada do sensor de proximidade.

    result > 0 indica detecção válida.
    distance é útil para depuração e para futuros refinamentos.
    """
    result, distance, _, _, _ = sim.readProximitySensor(sensor_handle)
    return result, distance


def no_eh_duto(no_id):
    return "Duto" in str(no_id)

def frontal_muito_proximo(result_frontal, distancia_frontal, limite_distancia):
    """
    Considera bloqueio apenas quando o frontal detecta algo e a distância é curta.
    """
    return result_frontal > 0 and distancia_frontal is not None and distancia_frontal <= limite_distancia

def avalia_duto(frontal_handler, grafo, sim, no_atual, id_destino, angulo_atual):
    sensor_data = sim.readProximitySensor(frontal_handler)
    result_frontal = sensor_data[0]

    if result_frontal > 0:
        print(f"  -> Parede detectada em {id_destino}. Caminho ignorado.")
    elif result_frontal == 0:
        novo_no = f"{no_atual}_Duto_{id_destino}"
        grafo.adicionar_conexao(origem=no_atual, destino=novo_no, status="livre")

        grafo.grafo[no_atual][novo_no]["angulo"] = angulo_atual
        if not grafo.direcionado:
            grafo.grafo[novo_no][no_atual]["angulo"] = angulo_atual + math.pi

        print(f"  -> Duto livre! Conexão criada: {no_atual} <---> {novo_no}")


def bueiro_routine(
    obj_handler,
    passo_linear,
    sim,
    client,
    frontal_handler,
    grafo,
    controlador,
    bueiro_ja_conhecido,
):
    limite_radianos = math.radians(90)
    passo_angular = 0.05
    no_atual = controlador.no_atual

    try:
        # REMOVIDA a lógica de centralização daqui. O robô já entra na função perfeitamente no centro!
        print(f"\n--- Rotina de Bueiro Iniciada em: {no_atual} ---")
        ori = sim.getObjectOrientation(obj_handler, sim.handle_world)
        angulo_base = ori[2]

        angulo_esq = angulo_base + limite_radianos
        angulo_frente = angulo_base
        angulo_dir = angulo_base - limite_radianos

        # Só mapeia se for inexplorado
        if not bueiro_ja_conhecido:
            # Esquerda (+90)
            contador = 0
            while contador < limite_radianos:
                ori[2] += passo_angular
                contador += passo_angular
                sim.setObjectOrientation(obj_handler, sim.handle_world, ori)
                client.step()
            ori[2] = angulo_esq
            sim.setObjectOrientation(obj_handler, sim.handle_world, ori)
            client.step()
            sim_sleep(sim, client, 0.5)
            avalia_duto(frontal_handler, grafo, sim, no_atual, "Esq", angulo_esq)

            # Frente (Volta aos 0)
            contador = 0
            while contador < limite_radianos:
                ori[2] -= passo_angular
                contador += passo_angular
                sim.setObjectOrientation(obj_handler, sim.handle_world, ori)
                client.step()
            ori[2] = angulo_frente
            sim.setObjectOrientation(obj_handler, sim.handle_world, ori)
            client.step()
            sim_sleep(sim, client, 0.5)
            avalia_duto(frontal_handler, grafo, sim, no_atual, "Frente", angulo_frente)

            # Direita (-90)
            contador = 0
            while contador < limite_radianos:
                ori[2] -= passo_angular
                contador += passo_angular
                sim.setObjectOrientation(obj_handler, sim.handle_world, ori)
                client.step()
            ori[2] = angulo_dir
            sim.setObjectOrientation(obj_handler, sim.handle_world, ori)
            client.step()
            sim_sleep(sim, client, 0.5)
            avalia_duto(frontal_handler, grafo, sim, no_atual, "Dir", angulo_dir)
        else:
            print(
                f"[{no_atual}] Local já conhecido! Poupando sensores e resgatando do grafo."
            )

        # ========================================================
        # DECISÃO DE MOVIMENTO
        # ========================================================
        proximo_destino = controlador.decidir_proximo_passo()

        if proximo_destino:
            angulo_alvo = grafo.grafo[no_atual][proximo_destino].get("angulo", 0)

            print(
                f"[{no_atual}] Virando fisicamente para {
                    proximo_destino
                } (Ângulo alvo: {angulo_alvo:.2f} rad)..."
            )
            ori = sim.getObjectOrientation(obj_handler, sim.handle_world)
            ori[2] = angulo_alvo
            sim.setObjectOrientation(obj_handler, sim.handle_world, ori)
            client.step()
            sim_sleep(sim, client, 0.5)

            # Dá os passos iniciais para ENTRAR no duto
            for _ in range(20):
                pos = sim.getObjectPosition(obj_handler, sim.handle_world)
                pos[0] -= passo_linear * math.sin(ori[2])
                pos[1] += passo_linear * math.cos(ori[2])
                sim.setObjectPosition(obj_handler, sim.handle_world, pos)
                client.step()
                sim_sleep(sim, client, 0.2)

            return True
        else:
            print(
                "\n[Sucesso] Labirinto totalmente explorado! Robô retornou ao ponto final."
            )
            return False

    except KeyboardInterrupt:
        raise KeyboardInterrupt

def duto_bloqueado_routine(
    obj_handler,
    passo_linear,
    sim,
    client,
    superior_handler,
    grafo,
    controlador,
    camera_handle=None,
    passos_centralizacao=9,
    limite_passos_retorno=500,
):
    """
    Trata bloqueio dentro de um duto.

    Condição esperada: sensor superior detectando duto e sensor frontal detectando obstáculo
    muito perto.
    A rotina marca o duto/aresta como bloqueado, gira 180 graus, volta até o bueiro
    anterior e devolve o controle para a rotina de bueiro continuar a busca.
    """
    duto_bloqueado = controlador.no_atual

    if controlador.pilha_caminho:
        bueiro_anterior = controlador.pilha_caminho.pop()
    else:
        bueiro_anterior = None

    print(f"\n[Bloqueio] Frontal muito perto: duto bloqueado detectado em {duto_bloqueado}.")

    # Tira foto antes de girar
    if camera_handle is not None:
        nome_foto = capturar_foto(sim, camera_handle, duto_bloqueado)
        if nome_foto and duto_bloqueado in grafo.nos:
            grafo.nos[duto_bloqueado]["foto"] = nome_foto

    # Marca o duto e a conexão de ida como bloqueados no grafo.
    if duto_bloqueado in grafo.grafo:
        try:
            grafo.atualizar_status_no(duto_bloqueado, "bloqueado")
        except Exception:
            # A aresta bloqueada já impede nova tentativa, mesmo que o grafo não use status em nós.
            pass

    if bueiro_anterior:
        if bueiro_anterior in grafo.grafo and duto_bloqueado in grafo.grafo[bueiro_anterior]:
            grafo.grafo[bueiro_anterior][duto_bloqueado]["status"] = "bloqueado"

        if duto_bloqueado in grafo.grafo and bueiro_anterior in grafo.grafo[duto_bloqueado]:
            grafo.grafo[duto_bloqueado][bueiro_anterior]["status"] = "bloqueado"

        print(f"[Bloqueio] Conexão {bueiro_anterior} <--> {duto_bloqueado} marcada como bloqueada.")
    else:
        print("[Bloqueio] Não encontrei bueiro anterior na pilha. Não dá para recuar com segurança.")
        return None

    # Giro físico de 180 graus.
    ori = sim.getObjectOrientation(obj_handler, sim.handle_world)
    ori[2] = normalizar_angulo(ori[2] + math.pi)
    sim.setObjectOrientation(obj_handler, sim.handle_world, ori)
    client.step()
    sim_sleep(sim, client, 0.5)
    print("[Bloqueio] Robô girou 180° e vai retornar ao bueiro anterior.")

    # Anda de volta pelo duto até o sensor superior deixar de detectar o teto do duto.
    passos = 0
    while passos < limite_passos_retorno:
        result_superior = sim.readProximitySensor(superior_handler)[0]
        if result_superior == 0:
            break

        pos = sim.getObjectPosition(obj_handler, sim.handle_world)
        pos[0] -= passo_linear * math.sin(ori[2])
        pos[1] += passo_linear * math.cos(ori[2])
        sim.setObjectPosition(obj_handler, sim.handle_world, pos)
        client.step()
        sim_sleep(sim, client, 0.2)
        passos += 1

    if passos >= limite_passos_retorno:
        print("[Bloqueio] Limite de retorno atingido antes de reencontrar o bueiro anterior.")
        return None

    # Entrou no bueiro anterior; anda mais um pouco para centralizar.
    for _ in range(passos_centralizacao):
        pos = sim.getObjectPosition(obj_handler, sim.handle_world)
        pos[0] -= passo_linear * math.sin(ori[2])
        pos[1] += passo_linear * math.cos(ori[2])
        sim.setObjectPosition(obj_handler, sim.handle_world, pos)
        client.step()
        sim_sleep(sim, client, 0.2)

    controlador.no_atual = bueiro_anterior
    grafo.atualizar_status_no(bueiro_anterior, "visitado")

    print(f"[Bloqueio] Retorno concluído. Robô voltou para {bueiro_anterior} e continuará a busca.")
    return bueiro_anterior

# SETUP INICIAL ===========================================
client = RemoteAPIClient()
client.setStepping(True)
sim = client.require("sim")

passo_linear = 0.1
# REMOVIDA A CAMINHADA CEGA - COMEÇA DIRETAMENTE COMO BUEIRO
estado = "Bueiro"
is_primeiro_bueiro = True
bueiro_ja_conhecido = False

grafo = Grafo()
bloqueio_frontal_consecutivo = 0
# Ajuste este valor para mudar a distância máxima que caracteriza bloqueio no duto.
LIMIAR_BLOQUEIO_FRONTAL = 2

prox_superior_path = "/Cuboid/proximidade_superior"
prox_frontal_path = "/Cuboid/proximidade_frontal"

camera_handle = None
try:
    prox_superior_handle = sim.getObject(prox_superior_path)
    prox_frontal_handle = sim.getObject(prox_frontal_path)
except Exception as e:
    print(f"Erro ao encontrar sensor: {e}")

try:
    camera_handle = sim.getObject("/Cuboid/camera_frontal")
    print("[Câmera] Vision sensor encontrado.")
except Exception as e:
    print(f"[Câmera] Vision sensor não encontrado, fotos desativadas: {e}")

coordenadas_bueiros = {}
contador_bueiros = 1
bueiro_inicial = f"Bueiro_{contador_bueiros}"

grafo.adicionar_no(bueiro_inicial)
controlador = ControladorRobo(grafo, bueiro_inicial)
salvar_snapshot_grafo(grafo)

visualizador = None
if os.environ.get("VISUALIZADOR_SEPARADO") != "1":
    visualizador = ServidorVisualizacaoGrafo(grafo)
    visualizador.iniciar()

sim.startSimulation()
cuboid_handle = sim.getObject("/Cuboid")

coordenadas_bueiros[bueiro_inicial] = sim.getObjectPosition(
    cuboid_handle, sim.handle_world
)

while sim.getSimulationTime() < 1:
    client.step()

print("Cérebro rodando! Robô iniciou o mapeamento.")

# LOOP PRINCIPAL ==============================================
try:
    executando = True
    ultimo_snapshot = 0

    while executando:
        result_superior, _ = ler_proximidade(sim, prox_superior_handle)
        result_frontal, distancia_frontal = ler_proximidade(sim, prox_frontal_handle)

        if result_superior > 0:
            estado = "Duto"

            if no_eh_duto(controlador.no_atual) and frontal_muito_proximo(
                result_frontal,
                distancia_frontal,
                LIMIAR_BLOQUEIO_FRONTAL,
            ):
                bloqueio_frontal_consecutivo += 1
            else:
                bloqueio_frontal_consecutivo = 0

            # Bloqueio real:
            # só dispara quando o frontal permanecer detectando obstáculo
            # muito perto por leituras consecutivas enquanto o robô já está em um duto.
            if bloqueio_frontal_consecutivo >= 2:
                bueiro_retorno = duto_bloqueado_routine(
                    cuboid_handle,
                    passo_linear,
                    sim,
                    client,
                    prox_superior_handle,
                    grafo,
                    controlador,
                    camera_handle=camera_handle,
                )

                if bueiro_retorno is None:
                    print("[Bloqueio] Falha ao retornar para o bueiro anterior. Encerrando por segurança.")
                    break

                bueiro_ja_conhecido = True
                estado = "Bueiro"
                bloqueio_frontal_consecutivo = 0

                salvar_snapshot_grafo(grafo)
                ultimo_snapshot = time.time()

                # Importante:
                # evita continuar esta mesma iteração com leituras antigas dos sensores.
                continue

        elif result_superior == 0:
            bloqueio_frontal_consecutivo = 0
            if estado == "Duto":
                print(
                    "\n[Ação] Fim do duto detectado! Andando até o centro geométrico do ambiente..."
                )

                ori = sim.getObjectOrientation(cuboid_handle, sim.handle_world)

                for i in range(9):
                    pos = sim.getObjectPosition(cuboid_handle, sim.handle_world)
                    pos[0] -= passo_linear * math.sin(ori[2])
                    pos[1] += passo_linear * math.cos(ori[2])
                    sim.setObjectPosition(cuboid_handle, sim.handle_world, pos)
                    client.step()
                    sim_sleep(sim, client, 0.2)

                pos_atual = sim.getObjectPosition(cuboid_handle, sim.handle_world)
                bueiro_reconhecido = None

                for nome_conhecido, coord_salva in coordenadas_bueiros.items():
                    if calcular_distancia(pos_atual, coord_salva) < 0.6:
                        bueiro_reconhecido = nome_conhecido
                        break

                duto_anterior = controlador.no_atual

                if bueiro_reconhecido:
                    bueiro_atual = bueiro_reconhecido
                    print(f"-> [Memória] Local conhecido identificado! Nós estamos no {bueiro_atual}")
                    bueiro_ja_conhecido = True
                else:
                    contador_bueiros += 1
                    bueiro_atual = f"Bueiro_{contador_bueiros}"
                    coordenadas_bueiros[bueiro_atual] = pos_atual
                    print(f"-> [Descoberta] Novo local descoberto: {bueiro_atual}")
                    bueiro_ja_conhecido = False

                if bueiro_atual not in grafo.grafo:
                    grafo.adicionar_no(bueiro_atual)

                grafo.atualizar_status_no(bueiro_atual, "visitado")

                grafo.adicionar_conexao(
                    duto_anterior,
                    bueiro_atual,
                    status="livre"
                )

                ori_atual = sim.getObjectOrientation(cuboid_handle, sim.handle_world)
                angulo_de_volta = ori_atual[2] + math.pi

                if duto_anterior not in grafo.grafo[bueiro_atual]:
                    grafo.grafo[bueiro_atual][duto_anterior] = {"status": "livre"}

                grafo.grafo[bueiro_atual][duto_anterior]["angulo"] = angulo_de_volta

                controlador.no_atual = bueiro_atual

            estado = "Bueiro"

        else:
            print("Erro Crítico no Sensor Superior!")
            break

        if estado == "Duto":
            ori = sim.getObjectOrientation(cuboid_handle, sim.handle_world)
            pos = sim.getObjectPosition(cuboid_handle, sim.handle_world)
            pos[0] -= passo_linear * math.sin(ori[2])
            pos[1] += passo_linear * math.cos(ori[2])
            sim.setObjectPosition(cuboid_handle, sim.handle_world, pos)

        elif estado == "Bueiro":
            continuar_simulacao = bueiro_routine(
                cuboid_handle,
                passo_linear,
                sim,
                client,
                prox_frontal_handle,
                grafo,
                controlador,
                bueiro_ja_conhecido,
            )

            if not continuar_simulacao:
                executando = False

        client.step()

        agora = time.time()
        if agora - ultimo_snapshot >= 0.5:
            salvar_snapshot_grafo(grafo)
            ultimo_snapshot = agora

        time.sleep(0.05)

except KeyboardInterrupt:
    print("\n[Sistema] Simulação interrompida pelo usuário (Ctrl+C).")

except Exception as e:
    print("\n[ERRO CRÍTICO] O Cérebro deu tela azul:")
    traceback.print_exc()

finally:
    print("\n[Sistema] Finalizando simulação no CoppeliaSim...")

    try:
        sim.stopSimulation()
    except Exception:
        pass

    salvar_snapshot_grafo(grafo)

    if visualizador:
        visualizador.parar()

    print("\n" + "=" * 50)
    print("       MAPA FINAL DA EXPLORAÇÃO (GRAFO RESULTANTE)       ")
    print("=" * 50)
    grafo.mostrar_grafo()
    print("=" * 50 + "\n")
