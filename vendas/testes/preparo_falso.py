"""Sistema falso para os testes do preparo: nenhum processo, Docker, rede ou sono de verdade. Simula um mundo com
docker/compose/colima/brew/winget e uma Evolution e um serviço que respondem (ou não) em 127.0.0.1."""
import json
import os

from servico.preparo_sistema import Sistema


class ProcessoFalso:
    def __init__(self, codigo=None):
        self.codigo = codigo

    def poll(self):
        return self.codigo


class SistemaFalso(Sistema):
    def __init__(self, plataforma="darwin", tem=("docker", "colima"), compose_plugin=True, ligado=True,
                 evolution_no_ar=False, marca=None):
        super().__init__(plataforma=plataforma, caminho="", ambiente={"ProgramFiles": "C:\\PF"})
        self.tem = set(tem)
        self.compose_plugin = compose_plugin
        self.ligado = ligado
        self.evolution_no_ar = evolution_no_ar
        self.evolution_sobe = True        # depois do `up -d` ela passa a responder
        self.marca = marca
        self.servico_no_ar = False
        self.servico_sai = False
        self.chamadas = []
        self.soltos = []
        self.agora = 0.0
        self.dormido = 0.0
        self.ocupadas = set()
        self.arquivos = set()
        self.os_release = None
        self.respostas = {}               # (programa, 1º argumento) -> (código, saída)
        self.colima_liga = True
        self.brew_instala = True
        self.estranho = None              # código HTTP de outro programa que ocupa a porta da Evolution
        self.chave_aceita = None          # None = a Evolution aceita qualquer apikey não vazia
        self.pedidos = []                 # (url, cabeçalhos) de cada GET

    # sistema
    def achar(self, nome):
        return "/falso/bin/" + nome if nome in self.tem else None

    def rodar(self, args, tempo, pasta=None):
        args = list(args)
        self.chamadas.append(args)
        programa = os.path.basename(args[0])
        chave = (programa, args[1] if len(args) > 1 else None)
        if chave in self.respostas:
            return self.respostas[chave]
        if programa == "docker" and args[1:3] == ["compose", "version"]:
            return (0, "Docker Compose version v2") if self.compose_plugin else (1, "unknown command")
        if programa == "docker" and args[1] == "info":
            return (0, "Server Version: 27") if self.ligado else (1, "Cannot connect to the Docker daemon")
        if programa == "colima" and args[1] == "start":
            self.ligado = self.colima_liga
            return (0, "done") if self.colima_liga else (1, "colima falhou")
        if programa == "brew" and args[1] == "install":
            if self.brew_instala:
                self.tem.update({"docker", "docker-compose", "colima"})
                return 0, "instalado"
            return 1, "Error: brew falhou"
        if programa == "winget":
            self.tem.update({"docker"})
            return 0, "Successfully installed"
        if "up" in args and "-d" in args:
            self.evolution_no_ar = self.evolution_sobe
            return 0, "Container api Started"
        if "pull" in args:
            return 0, "Pulled"
        if programa == "open":
            self.ligado = True
            return 0, ""
        return 0, ""

    def soltar(self, args, caminho_log, pasta=None):
        self.soltos.append(list(args))
        if any(a.endswith("servico.py") for a in args):
            if self.servico_sai:
                with open(caminho_log, "a", encoding="utf-8") as f:
                    f.write("vendas: não subi: porta ocupada\n")
                return ProcessoFalso(4)
            self.servico_no_ar = True
        if any(a.endswith("Docker Desktop.exe") for a in args):
            self.ligado = True
        return ProcessoFalso()

    def relogio(self):
        return self.agora

    def dormir(self, segundos):
        self.agora += segundos
        self.dormido += segundos

    def http(self, url, tempo=5, cabecalhos=None):
        self.pedidos.append((url, dict(cabecalhos or {})))
        if url.endswith("/saude"):
            if self.servico_no_ar:
                return 200, json.dumps({"ok": True, "marca": self.marca}).encode("utf-8")
            return None, b""
        if self.estranho is not None:
            return self.estranho, b"Not Found"
        if not self.evolution_no_ar:
            return None, b""
        chave = (cabecalhos or {}).get("apikey")
        if not url.endswith("/instance/fetchInstances") or not chave:
            return 401, b"{}"
        return (200, b"[]") if self.chave_aceita in (None, chave) else (401, b"{}")

    def porta_livre(self, porta):
        return porta not in self.ocupadas

    def porta_qualquer(self):
        return 18080 + len(self.ocupadas)

    def existe(self, caminho):
        return caminho in self.arquivos

    def ler_texto(self, caminho):
        return self.os_release if caminho == "/etc/os-release" else None

    # ajudas dos testes
    def programas(self):
        return [os.path.basename(c[0]) for c in self.chamadas]

    def instaladores(self):
        return [c for c in self.chamadas if os.path.basename(c[0]) in ("brew", "winget", "apt-get", "sudo")]
