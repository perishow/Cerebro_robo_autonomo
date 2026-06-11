class ControladorRobo:
    def __init__(self, mapa_grafo, no_inicial):
        """
        Inicializa o robô em um ponto de partida no grafo.
        """
        self.mapa = mapa_grafo
        self.no_atual = no_inicial
        self.pilha_caminho = []  # O histórico para o robô saber como voltar

        # Marca o nó inicial como visitado
        self.mapa.atualizar_status_no(self.no_atual, "visitado")

    def decidir_proximo_passo(self):
        """
        Avalia o ambiente e retorna para onde o robô deve ir agora.
        """
        print(f"\n[Robô] Estou no nó: {self.no_atual}")

        # Pega todas as conexões saindo do nó atual
        vizinhos = self.mapa.grafo[self.no_atual]

        # 1. Tenta encontrar um caminho inédito e livre
        for vizinho, dados_via in vizinhos.items():
            status_via = dados_via["status"]
            status_no = self.mapa.nos[vizinho]["status"]

            if status_via == "livre" and status_no == "não visitado":
                print(f"-> Caminho livre encontrado para {vizinho}!")

                # Guarda onde estamos antes de ir, para podermos voltar se necessário
                self.pilha_caminho.append(self.no_atual)

                # Move o robô e atualiza o mapa
                self.no_atual = vizinho
                self.mapa.atualizar_status_no(vizinho, "visitado")

                return vizinho  # Retorna o comando para o hardware se mover

        # 2. Se chegou aqui, é um beco sem saída. Precisa recuar.
        print(
            "-> Beco sem saída ou todas as vias ao redor já foram visitadas/bloqueadas."
        )

        if self.pilha_caminho:
            no_anterior = self.pilha_caminho.pop()
            print(f"-> Executando Backtracking (marcha à ré) para: {no_anterior}")
            self.no_atual = no_anterior
            return no_anterior

        # 3. Se a pilha está vazia, o robô explorou tudo que era possível
        print("-> Exploração concluída! Não há mais para onde ir.")
        return None
