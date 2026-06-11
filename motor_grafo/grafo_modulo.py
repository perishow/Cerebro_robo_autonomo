class Grafo:
    def __init__(self, direcionado=False):
        """
        Inicializa o grafo com suporte a status de nós e arestas.
        """
        self.nos = {}  # Guarda as propriedades de cada nó (ex: status)
        # Guarda as conexões e as propriedades da aresta (ex: status)
        self.grafo = {}
        self.direcionado = direcionado

    def adicionar_no(self, no, status="não visitado"):
        """
        Adiciona um novo nó ao grafo com o status inicial.
        """
        if no not in self.nos:
            self.nos[no] = {"status": status}
            self.grafo[no] = {}

    def adicionar_conexao(self, origem, destino, status="livre"):
        """
        Adiciona uma conexão entre dois nós, definindo o status da via.
        """
        self.adicionar_no(origem)
        self.adicionar_no(destino)

        # Adiciona a conexão com os parâmetros da aresta
        if destino not in self.grafo[origem]:
            self.grafo[origem][destino] = {"status": status}

        # Se não for direcionado, cria a via de volta com o mesmo status
        if not self.direcionado:
            if origem not in self.grafo[destino]:
                self.grafo[destino][origem] = {"status": status}

    def atualizar_status_no(self, no, status):
        """
        Atualiza o status de um nó existente.
        """
        if no in self.nos:
            self.nos[no]["status"] = status
        else:
            print(f"Aviso: O nó '{no}' não existe.")

    def atualizar_status_conexao(self, origem, destino, status):
        """
        Atualiza o status de uma conexão existente.
        """
        if origem in self.grafo and destino in self.grafo[origem]:
            self.grafo[origem][destino]["status"] = status

            # Atualiza a volta se o grafo for não direcionado
            if not self.direcionado:
                self.grafo[destino][origem]["status"] = status
        else:
            print(f"Aviso: A conexão entre '{origem}' e '{destino}' não existe.")

    def mostrar_grafo(self):
        """
        Imprime o grafo mostrando os status dos nós e conexões.
        """
        for no in self.grafo:
            status_do_no = self.nos[no]["status"]
            # Monta a string das conexões mostrando o destino e o status da via
            conexoes = ", ".join(
                f"{destino} (via: {dados['status']})"
                for destino, dados in self.grafo[no].items()
            )
            print(f"Nó {no} [{status_do_no}] está conectado a: [{conexoes}]")

    def display(self):
        """
        Desenha o grafo no terminal, incluindo as propriedades.
        """
        print("\n--- Desenho do Grafo ---")
        visitados_display = set()

        def dfs_desenhar(no, prefixo="", eh_ultimo=True, raiz=True, status_via=""):
            conector = "" if raiz else ("└── " if eh_ultimo else "├── ")

            # Formata a representação da aresta
            info_via = f" --({status_via})--> " if not raiz else ""
            status_no = self.nos[no]["status"]

            # Formata a representação do nó
            texto_no = f"[{no} | {status_no}]"

            if no in visitados_display:
                print(f"{prefixo}{conector}{info_via}{texto_no} (ciclo)")
                return

            print(f"{prefixo}{conector}{info_via}{texto_no}")
            visitados_display.add(no)

            novo_prefixo = prefixo + ("    " if eh_ultimo or raiz else "│   ")
            vizinhos = list(self.grafo[no].keys())

            for i, vizinho in enumerate(vizinhos):
                ultimo_vizinho = i == len(vizinhos) - 1
                # Pega o status da conexão para passar adiante
                status_da_ligacao = self.grafo[no][vizinho]["status"]
                dfs_desenhar(
                    vizinho, novo_prefixo, ultimo_vizinho, False, status_da_ligacao
                )

        for no in self.grafo:
            if no not in visitados_display:
                dfs_desenhar(no)
                print()


# ==========================================
# Exemplo de Uso
# ==========================================

meu_grafo = Grafo(direcionado=False)

# Adicionando conexões e já definindo se estão livres ou com entulho
meu_grafo.adicionar_conexao("A", "B", status="livre")
meu_grafo.adicionar_conexao("A", "C", status="com entulho")
meu_grafo.adicionar_conexao("B", "D", status="livre")
meu_grafo.adicionar_conexao("C", "D", status="livre")

# Simulando uma travessia: mudando o status dos nós para visitado
meu_grafo.atualizar_status_no("A", "visitado")
meu_grafo.atualizar_status_no("B", "visitado")

# Exibindo
print("Estrutura do Grafo:")
meu_grafo.mostrar_grafo()

meu_grafo.display()
