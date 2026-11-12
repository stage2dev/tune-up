"""Aba Conexão, preparo em um clique: blocos de cada estado (nada preparado, cada passo andando, precisa do dono com o
comando, falhou, Evolution pronta com o serviço parado) sem caminho, chave ou saída crua; "Preparar tudo" solta o
preparo uma vez só e um segundo clique com ele vivo não solta outro; "Ligar o serviço" pede só o último passo; ação
desconhecida recusada; só a raiz da página vale."""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import socket  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from servico import pasta, preparo  # noqa: E402
from testes.test_servico import carregar_modulo  # noqa: E402

CHAVE = "chave-evolution-0123456789abcdef"
CRU = "Error response from daemon: pull access denied /var/lib/x"
NOMES = [n for n, _, _ in preparo.PASSOS]


class Processo:
    def __init__(self):
        self.codigo = None

    def poll(self):
        return self.codigo


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.projeto = os.path.join(self.tmp, "projeto")
        os.makedirs(self.projeto)
        self.base = os.path.join(self.tmp, "dados")
        self.pasta = pasta.pasta_de_dados(self.projeto, self.base)
        self.mod = carregar_modulo()
        self.ctx = {"raiz": self.projeto, "config": {"porta": 8790}}
        self.soltos = []
        self.processos = []

        def soltar(argv, log):
            self.soltos.append((argv, log))
            self.processos.append(Processo())
            return self.processos[-1]
        self.mod.preparar.soltar = soltar
        self.mod.preparar._lancados.clear()

    def estado(self, final, passos, pid=None, portas=None):
        registro = {"id": "x", "pid": pid or os.getpid(), "estado": final, "log": os.path.join(self.pasta,
                    "preparo.log"), "portas": portas or {}, "passos": passos}
        with open(os.path.join(self.pasta, "preparo.json"), "w", encoding="utf-8") as f:
            json.dump(registro, f)

    def passos(self, atual, estado_atual, **extra):
        lista = []
        for i, nome in enumerate(NOMES):
            e = "feito" if i < atual else (estado_atual if i == atual else "pendente")
            p = {"nome": nome, "titulo": nome, "estado": e, "mensagem": "ok" if e == "feito" else None,
                 "comando": None, "detalhe": "progresso %s %s" % (CHAVE, CRU)}
            if i == atual:
                p.update(extra)
            lista.append(p)
        return lista

    def montar(self):
        return self.mod.montar(self.ctx, base=self.base)

    def conexao(self, r=None):
        return (r or self.montar())["abas"][0]["blocos"]

    def limpo(self, blocos, comando=None):
        texto = json.dumps(blocos, ensure_ascii=False)
        if comando:
            texto = texto.replace(json.dumps(comando, ensure_ascii=False)[1:-1], "")
        for proibido in (self.pasta, self.base, self.tmp, "preparo.log", "preparo.json", CHAVE, CRU, "token",
                         "progresso"):
            self.assertNotIn(proibido, texto)
        return texto


class TesteBlocos(Base):
    def test_nada_preparado_um_cartao_preparar_tudo(self):
        r = self.montar()
        blocos = self.conexao(r)
        self.assertEqual([(b["tipo"], b["acao"], b["botao"]) for b in blocos],
                         [("formulario", "preparar_tudo", "Preparar tudo")])
        self.assertEqual(blocos[0]["titulo"], "Preparar o WhatsApp neste computador")
        texto = self.limpo(blocos)
        self.assertEqual(texto.count("Docker"), 1)
        for trecho in ("minutos", "Windows", "Fazer à mão"):
            self.assertIn(trecho, texto)
        self.assertEqual(r["atualizar_em"], 15)

    def test_rodando_em_cada_passo_lista_com_o_atual_fazendo(self):
        for i in range(len(NOMES)):
            self.estado("rodando", self.passos(i, "rodando"))
            r = self.montar()
            blocos = self.conexao(r)
            self.assertEqual([b["tipo"] for b in blocos], ["lista"])
            selos = [it["selo"]["texto"] for it in blocos[0]["itens"]]
            self.assertEqual(selos, ["feito"] * i + ["fazendo..."] + ["falta"] * (len(NOMES) - i - 1))
            self.assertEqual(r["atualizar_em"], 3)
            self.limpo(blocos)

    def test_precisa_do_dono_mensagem_comando_e_ja_fiz(self):
        comando = "brew install colima docker docker-compose"
        self.estado("precisa_do_dono", self.passos(0, "precisa_do_dono", comando=comando,
                                                   mensagem="Falta o Docker. Cole este comando num terminal."))
        blocos = self.conexao()
        self.assertEqual(len(blocos), 1)
        b = blocos[0]
        self.assertEqual((b["acao"], b["botao"]), ("preparar_tudo", "Já fiz, continuar"))
        self.assertEqual([c["valor"] for c in b["campos"]], [comando])
        self.assertIn("Cole este comando", b["descricao"])
        self.limpo(blocos, comando)

    def test_falhou_motivo_e_tentar_de_novo(self):
        self.estado("falhou", self.passos(3, "falhou", mensagem="Não consegui baixar. Confira a internet."))
        b = self.conexao()[0]
        self.assertEqual((b["acao"], b["botao"], b["campos"]), ("preparar_tudo", "Tentar de novo", []))
        self.assertIn("Confira a internet", b["descricao"])
        self.limpo([b])

    def test_mensagem_com_a_pasta_de_dados_sai_mascarada(self):
        self.estado("falhou", self.passos(2, "falhou", mensagem="Não gravei em %s/evolution." % self.pasta))
        self.limpo(self.conexao())

    def test_processo_morto_vira_tentar_de_novo(self):
        self.estado("rodando", self.passos(1, "rodando"), pid=2 ** 30)
        b = self.conexao()[0]
        self.assertEqual(b["botao"], "Tentar de novo")

    def test_estado_corrompido_vira_preparar_tudo(self):
        with open(os.path.join(self.pasta, "preparo.json"), "w", encoding="utf-8") as f:
            f.write("{nao e json")
        self.assertEqual([b["botao"] for b in self.conexao()], ["Preparar tudo"])

    def test_evolution_pronta_e_servico_parado_mostra_ligar(self):
        os.makedirs(os.path.join(self.pasta, "evolution"))
        for n in ("compose.yml", ".env"):
            open(os.path.join(self.pasta, "evolution", n), "w").close()
        escuta = socket.socket()
        self.addCleanup(escuta.close)
        escuta.bind(("127.0.0.1", 0))
        escuta.listen(1)
        porta = escuta.getsockname()[1]
        self.estado("feito", self.passos(5, "feito"), portas={"evolution": porta})
        blocos = self.conexao()
        self.assertEqual([(b["acao"], b["botao"]) for b in blocos], [("ligar_servico", "Ligar o serviço")])
        self.limpo(blocos)
        escuta.close()   # a Evolution caiu: volta o "Preparar tudo"
        self.assertEqual([b["acao"] for b in self.conexao()], ["preparar_tudo"])


class TesteAgir(Base):
    def agir(self, acao, dados=None):
        return self.mod.agir(self.ctx, acao, dados or {}, base=self.base)

    def test_preparar_tudo_solta_uma_vez_e_o_segundo_clique_nao(self):
        r = self.agir("preparar_tudo", {"projeto": "/outro/projeto", "comando": "rm -rf /"})
        self.assertTrue(r["ok"])
        self.assertEqual(len(self.soltos), 1)
        argv, log = self.soltos[0]
        self.assertIsInstance(argv, list)
        self.assertEqual(argv[:4], [sys.executable, "-B", self.mod.preparar.PREPARO, "iniciar"])
        self.assertEqual(argv[argv.index("--projeto") + 1], self.projeto)   # a raiz da página, nunca a dos dados
        self.assertEqual(argv[argv.index("--painel") + 1], "http://127.0.0.1:8790")
        self.assertNotIn("--so-servico", argv)
        self.assertNotIn("rm -rf /", json.dumps(argv))
        self.assertEqual(log, os.path.join(self.pasta, "preparo.log"))
        self.assertTrue(self.agir("preparar_tudo")["ok"])   # processo solto ainda vivo
        self.assertEqual(len(self.soltos), 1)
        self.assertEqual(self.montar()["atualizar_em"], 3)
        self.processos[0].codigo = 0
        self.estado("rodando", self.passos(2, "rodando"))   # o preparo destacado está andando
        self.agir("preparar_tudo")
        self.agir("ligar_servico")
        self.assertEqual(len(self.soltos), 1)
        self.estado("falhou", self.passos(2, "falhou", mensagem="parou"))
        self.agir("preparar_tudo")   # parou: o clique seguinte retoma
        self.assertEqual(len(self.soltos), 2)

    def test_ligar_servico_pede_so_o_ultimo_passo(self):
        self.assertTrue(self.agir("ligar_servico")["ok"])
        argv = self.soltos[0][0]
        self.assertEqual(argv[3], "iniciar")
        self.assertEqual(argv[-1], "--so-servico")
        self.assertEqual(preparo.argumentos(argv[3:]).so_servico, True)

    def test_acao_desconhecida_e_sem_raiz_recusadas(self):
        for acao in ("preparar", "apagar_tudo", "rodar"):
            self.assertEqual(self.agir(acao), {"ok": False, "mensagem": "Ação desconhecida."})
        self.assertFalse(self.mod.agir({}, "preparar_tudo", {}, base=self.base)["ok"])
        self.assertEqual(self.soltos, [])
        for acao in self.mod.preparar.ACOES:
            self.assertIn(acao, self.mod.INFO["acoes"])

    def test_regras_de_negar_continuam(self):
        negar = self.mod.INFO["negar"]
        for regra in ("Bash(*tune-up-vendas*)", "Bash(*/api/modulos/*/acao*)", "Bash(*127.0.0.1:8791*)",
                      "Read(~/Library/Application Support/tune-up-vendas/**)"):
            self.assertIn(regra, negar)


if __name__ == "__main__":
    unittest.main()
