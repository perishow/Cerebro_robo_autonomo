from grafo_teste import Grafo
from controlador_teste import ControladorRobo

# 1. Montamos o ambiente (Mapa)
mapa = Grafo(direcionado=False)

# Adicionando um cenário um pouco maior para testar a DFS
mapa.adicionar_conexao("A", "B", status="livre")
mapa.adicionar_conexao("A", "C", status="livre")
mapa.adicionar_conexao("B", "D", status="com entulho")  # Caminho bloqueado!
mapa.adicionar_conexao("B", "E", status="livre")
mapa.adicionar_conexao("C", "F", status="livre")

print("--- MAPA INICIAL ---")
mapa.mostrar_grafo()

# 2. Ligamos o robô no nó "A"
robo = ControladorRobo(mapa, no_inicial="A")

# 3. Rodamos um loop de controle (como rodaria no microcontrolador do robô)
# Vamos rodar até a função retornar None (exploração finalizada)
while True:
    proximo_no = robo.decidir_proximo_passo()
    if proximo_no is None:
        break
