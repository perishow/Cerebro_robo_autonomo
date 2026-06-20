import json
import mimetypes
import time
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


ROOT_PROJETO = Path(__file__).resolve().parents[1]
FRONTEND_DIR = ROOT_PROJETO / "front-end"
GRAFO_JSON_PADRAO = FRONTEND_DIR / "grafo_atual.json"
GRAFO_VAZIO = {"direcionado": False, "nos": [], "arestas": []}


def salvar_snapshot_grafo(grafo, caminho=GRAFO_JSON_PADRAO):
    caminho = Path(caminho)
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(grafo.to_dict(), ensure_ascii=False), encoding="utf-8")


class ServidorVisualizacaoGrafo:
    def __init__(self, grafo=None, host="127.0.0.1", porta=8765, caminho_json=None):
        self.grafo = grafo
        self.host = host
        self.porta = porta
        self.caminho_json = Path(caminho_json or GRAFO_JSON_PADRAO)
        self._servidor = None
        self._thread = None
        self._root_frontend = FRONTEND_DIR

    def obter_grafo_dict(self):
        if self.grafo is not None:
            return self.grafo.to_dict()

        if not self.caminho_json.exists():
            return GRAFO_VAZIO

        try:
            return json.loads(self.caminho_json.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return GRAFO_VAZIO

    def iniciar(self):
        if self._servidor:
            return

        visualizador = self

        class Handler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/api/grafo":
                    self._responder_json(visualizador.obter_grafo_dict())
                    return

                caminho = self.path.split("?", 1)[0]
                if caminho in ("", "/"):
                    caminho = "/index.html"

                arquivo = (visualizador._root_frontend / caminho.lstrip("/")).resolve()
                if not self._arquivo_permitido(arquivo):
                    self.send_error(404)
                    return

                conteudo = arquivo.read_bytes()
                content_type = mimetypes.guess_type(str(arquivo))[0] or "application/octet-stream"
                self.send_response(200)
                self.send_header("Content-Type", content_type)
                self.send_header("Content-Length", str(len(conteudo)))
                self.end_headers()
                self.wfile.write(conteudo)

            def log_message(self, formato, *args):
                return

            def _arquivo_permitido(self, arquivo):
                try:
                    arquivo.relative_to(visualizador._root_frontend)
                except ValueError:
                    return False
                return arquivo.is_file()

            def _responder_json(self, dados):
                conteudo = json.dumps(dados, ensure_ascii=False).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Cache-Control", "no-store")
                self.send_header("Content-Length", str(len(conteudo)))
                self.end_headers()
                self.wfile.write(conteudo)

        self._servidor = ThreadingHTTPServer((self.host, self.porta), Handler)
        self._thread = threading.Thread(target=self._servidor.serve_forever, daemon=True)
        self._thread.start()
        print(f"[Visualizador] Servidor rodando em http://{self.host}:{self.porta}")
        print("[Visualizador] Acesse esse endereço para ver o grafo em tempo real.")

    def parar(self):
        if not self._servidor:
            return

        self._servidor.shutdown()
        self._servidor.server_close()
        self._servidor = None
        self._thread = None


def main():
    servidor = ServidorVisualizacaoGrafo()
    servidor.iniciar()
    print(f"[Visualizador] Lendo grafo de {GRAFO_JSON_PADRAO}")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[Visualizador] Encerrando servidor...")
    finally:
        servidor.parar()


if __name__ == "__main__":
    main()
