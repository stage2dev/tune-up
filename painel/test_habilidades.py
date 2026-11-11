"""Testes da lista de skills do chat: descoberta, grupos, escolha e o bloco no pedido.

Home e projeto são pastas temporárias; nada chama o claude de verdade.
"""
import sys

sys.dont_write_bytecode = True

import http.client  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import threading  # noqa: E402
import unittest  # noqa: E402

import config  # noqa: E402
import habilidades  # noqa: E402
import lancador  # noqa: E402
import painel  # noqa: E402
import transcricao  # noqa: E402
from test_chat import NIVEL, CLIChat  # noqa: E402
from test_lancador import cfg_teste  # noqa: E402


def escrever(caminho, texto):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8", newline="\n") as f:
        f.write(texto)


def skill(pasta, nome, descricao="faz coisas", cabeca=None):
    escrever(os.path.join(pasta, nome, "SKILL.md"),
             cabeca if cabeca is not None else "---\nname: %s\ndescription: %s\n---\n# corpo\n" % (nome, descricao))


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, self.tmp)
        self.home = os.path.join(self.tmp, "home")
        self.proj = os.path.join(self.tmp, "proj")
        os.makedirs(os.path.join(self.proj, "acoes"))
        with open(os.path.join(self.proj, "acoes", "chat.json"), "w", encoding="utf-8") as f:
            json.dump({"acoes": [NIVEL, {"id": "dev.x", "grupo": "dev", "titulo": "Dev", "risco": "leitura",
                                         "prompt": "/fazer"}]}, f)
        habilidades._cache.clear()
        self.addCleanup(habilidades._cache.clear)
        plugins = {}
        for nome, mkt in (("vendedor", "loja"), ("desligado", "loja"), ("tune-up", "loja"), ("tune-up-extra", "loja")):
            inst = os.path.join(self.tmp, "inst", nome)
            plugins["%s@%s" % (nome, mkt)] = [{"installPath": inst, "lastUpdated": "2026-01-01"}]
        escrever(os.path.join(self.home, ".claude", "plugins", "installed_plugins.json"),
                 json.dumps({"version": 2, "plugins": plugins}))
        escrever(os.path.join(self.home, ".claude", "settings.json"),
                 json.dumps({"enabledPlugins": {"desligado@loja": False, "vendedor@loja": True}}))
        inst = os.path.join(self.tmp, "inst")
        skill(os.path.join(inst, "vendedor", "skills"), "prospectar", "Acha leads e monta o funil de vendas")
        skill(os.path.join(inst, "desligado", "skills"), "video-curto", "Edita um vídeo curto")
        skill(os.path.join(inst, "tune-up", "skills"), "part", "Roda uma Parte")
        skill(os.path.join(inst, "tune-up-extra", "skills"), "pitfalls", "Armadilhas do projeto")
        skill(os.path.join(self.home, ".claude", "skills"), "minha", "Revisão de segurança do código")
        skill(os.path.join(self.proj, ".claude", "skills"), "do-projeto", "Migration no Postgres")
        self.extra = os.path.join(self.tmp, "extra")
        skill(self.extra, "anuncio", "Escreve o anúncio")

    def cfg(self, **extra):
        base = dict(home=self.home, raiz=self.proj, repo=None,
                    habilidades_pastas=[{"titulo": "Pasta extra", "pasta": self.extra}])
        base.update(extra)
        return cfg_teste(self.proj, **base)

    def por_nome(self, cfg=None):
        return {h["nome"]: h for h in habilidades.descobrir(cfg or self.cfg())["habilidades"]}


class TesteDescoberta(Base):
    def test_quatro_fontes(self):
        hs = self.por_nome()
        self.assertEqual(sorted(hs), ["anuncio", "desligado:video-curto", "do-projeto", "minha",
                                      "tune-up-extra:pitfalls", "tune-up:part", "vendedor:prospectar"])
        v = hs["vendedor:prospectar"]
        self.assertEqual((v["titulo"], v["origem"], v["listada"], v["fixa"], v["grupo"]),
                         ("prospectar", "vendedor", True, False, "vendas"))
        self.assertRegex(v["id"], r"^[0-9a-f]{12}$")
        self.assertEqual((hs["minha"]["origem"], hs["minha"]["listada"]), ("Suas skills", True))
        self.assertEqual((hs["do-projeto"]["origem"], hs["do-projeto"]["listada"]), ("Projeto", True))
        self.assertEqual((hs["anuncio"]["origem"], hs["anuncio"]["listada"]), ("Pasta extra", False))
        self.assertEqual(self.por_nome()["vendedor:prospectar"]["id"], v["id"])  # estável

    def test_plugin_desligado_e_fixas(self):
        hs = self.por_nome()
        self.assertFalse(hs["desligado:video-curto"]["listada"])
        for n in ("tune-up:part", "tune-up-extra:pitfalls"):
            self.assertEqual((hs[n]["fixa"], hs[n]["grupo"]), (True, "tuneup"))
        # settings do projeto vence o do usuário
        escrever(os.path.join(self.proj, ".claude", "settings.local.json"),
                 json.dumps({"enabledPlugins": {"desligado@loja": True}}))
        self.assertTrue(self.por_nome()["desligado:video-curto"]["listada"])

    def test_grupos_e_resposta_publica(self):
        dado = habilidades.descobrir(self.cfg())
        ids = [g["id"] for g in dado["grupos"]]
        self.assertEqual(ids, ["tuneup", "marketing", "vendas", "revisao", "banco", "midia"])
        self.assertEqual(dado["grupos"][0]["titulo"], "Tune-up (sempre ligado)")
        publico = habilidades.para_tela(dado)
        self.assertNotIn(self.tmp, json.dumps(publico))
        self.assertEqual(sorted(publico["habilidades"][0]), sorted(habilidades.PUBLICOS))

    def test_frontmatter_torto_e_nome_invalido(self):
        pasta = os.path.join(self.home, ".claude", "skills")
        skill(pasta, "sem-fim", cabeca="---\nname: outro\ndescription: nunca fecha\n")
        skill(pasta, "dobrado", cabeca="---\nname: dobrado\ndescription: >\n  linha um\n  linha dois\nx: 1\n---\n")
        skill(pasta, "aspas", cabeca="---\nname: \"aspas\"\ndescription: 'com aspas'\n---\n")
        skill(pasta, "ruim", cabeca="---\nname: -comeca-com-traco\n---\n")
        skill(pasta, "espaco", cabeca="---\nname: tem espaço\n---\n")
        skill(pasta, "vazio", cabeca="")
        os.makedirs(os.path.join(pasta, "sem-arquivo"))
        hs = self.por_nome()
        self.assertEqual(hs["sem-fim"]["descricao"], "")  # bloco sem fim: vale o nome da pasta
        self.assertEqual(hs["dobrado"]["descricao"], "linha um linha dois")
        self.assertEqual(hs["aspas"]["descricao"], "com aspas")
        self.assertIn("vazio", hs)
        for fora in ("-comeca-com-traco", "tem espaço", "ruim", "espaco", "sem-arquivo", "outro"):
            self.assertNotIn(fora, hs)
        self.assertEqual(habilidades.frontmatter("---\ndescription: |\n  a\n  b\n---\n"), {"description": "a\nb"})

    def test_descricao_cortada_e_mascarada(self):
        skill(os.path.join(self.home, ".claude", "skills"), "longa", "token sk-abcdefghijklmnopqrstu " + "x" * 400)
        d = self.por_nome()["longa"]["descricao"]
        self.assertLessEqual(len(d), 300)
        self.assertNotIn("abcdefghijklmnop", d)

    @unittest.skipUnless(hasattr(os, "mkfifo"), "sem FIFO neste sistema")
    def test_fifo_nao_trava(self):
        pasta = os.path.join(self.home, ".claude", "skills", "fifo")
        os.makedirs(pasta)
        os.mkfifo(os.path.join(pasta, "SKILL.md"))
        self.assertNotIn("fifo", self.por_nome())

    def test_repetido_fica_o_listado_e_teto(self):
        skill(self.extra, "minha", "cópia de fora da lista")
        skill(os.path.join(self.proj, ".claude", "skills"), "minha", "segunda listada")
        self.assertEqual(self.por_nome()["minha"]["origem"], "Suas skills")
        cfg = self.cfg(habilidades_pastas=[])
        skill(os.path.join(self.proj, ".claude", "skills"), "anuncio", "listada")
        self.assertEqual(self.por_nome(self.cfg(habilidades_pastas=[{"titulo": "X", "pasta": self.extra}]))
                         ["anuncio"]["origem"], "Projeto")
        velho, habilidades.TETO = habilidades.TETO, 3
        try:
            dado = habilidades.descobrir(cfg)
        finally:
            habilidades.TETO = velho
        self.assertEqual(len(dado["habilidades"]), 3)
        self.assertTrue(any("3" in a for a in dado["avisos"]))

    def test_regras_do_pacote(self):
        pacote = os.path.join(self.proj, "pacote")
        escrever(os.path.join(pacote, "habilidades.json"), json.dumps({
            "regras": [{"grupo": "design", "regex": "funil"}, {"grupo": "inexistente", "regex": "x"},
                       {"grupo": "codigo", "regex": "("}],
            "plugins": {"desligado": "codigo", "outro": "nada"}}))
        cfg = self.cfg(pacote_dir=pacote, pacote_ok=True)
        dado = habilidades.descobrir(cfg)
        hs = {h["nome"]: h for h in dado["habilidades"]}
        self.assertEqual(hs["vendedor:prospectar"]["grupo"], "design")
        self.assertEqual(hs["desligado:video-curto"]["grupo"], "codigo")
        self.assertEqual(len([a for a in dado["avisos"] if "pacote" in a]), 3)
        escrever(os.path.join(pacote, "habilidades.json"), "{ruim")
        dado = habilidades.descobrir(cfg)
        self.assertTrue(dado["habilidades"] and any("ilegível" in a for a in dado["avisos"]))

    @unittest.skipUnless(hasattr(os, "mkfifo"), "sem FIFO neste sistema")
    def test_json_sem_bloquear_e_avisos(self):
        avisos = []
        self.assertEqual(habilidades._ler_json(os.path.join(self.tmp, "nao-ha.json"), avisos, "x"), {})
        os.mkfifo(os.path.join(self.tmp, "fifo.json"))
        escrever(os.path.join(self.tmp, "grande.json"), '{"a": "%s"}' % ("x" * 300 * 1024))
        self.assertEqual(habilidades._ler_json(os.path.join(self.tmp, "fifo.json"), avisos, "fifo"), {})
        self.assertEqual(habilidades._ler_json(os.path.join(self.tmp, "grande.json"), avisos, "grande"), {})
        self.assertEqual(len(avisos), 2)
        os.remove(os.path.join(self.home, ".claude", "settings.json"))
        os.mkfifo(os.path.join(self.home, ".claude", "settings.json"))  # existe e não abre
        dado = habilidades.descobrir(self.cfg())
        hs = {h["nome"]: h for h in dado["habilidades"]}
        self.assertFalse(hs["vendedor:prospectar"]["listada"])
        self.assertTrue(hs["tune-up:part"]["listada"] and hs["minha"]["listada"])
        self.assertTrue(any("settings" in a for a in dado["avisos"]))
        escrever(os.path.join(self.home, ".claude", "plugins", "installed_plugins.json"), "{ruim")
        dado = habilidades.descobrir(self.cfg())
        self.assertNotIn("vendedor:prospectar", {h["nome"] for h in dado["habilidades"]})
        self.assertIn("não consegui ler a lista de plugins; as skills de plugin ficaram de fora", dado["avisos"])

    def test_listada_so_do_que_a_sessao_carrega(self):
        repo = os.path.join(self.tmp, "repo")
        skill(os.path.join(repo, ".claude", "skills"), "do-repo")
        escrever(os.path.join(repo, ".claude", "settings.json"), json.dumps({"enabledPlugins": {"desligado@loja": True}}))
        hs = self.por_nome(self.cfg(repo=repo))
        self.assertEqual((hs["do-repo"]["origem"], hs["do-repo"]["listada"]), ("Projeto", False))
        self.assertFalse(hs["desligado:video-curto"]["listada"])  # settings do repo não vale
        atalho = os.path.join(self.tmp, "atalho-proj")
        os.symlink(self.proj, atalho)
        self.assertTrue(self.por_nome(self.cfg(repo=atalho))["do-projeto"]["listada"])

    def test_nome_da_pasta_e_atalhos(self):
        pasta = os.path.join(self.home, ".claude", "skills")
        skill(pasta, "tem espaço", cabeca="---\nname: bonito\n---\n")
        skill(os.path.join(self.tmp, "fora"), "segredo")
        os.makedirs(os.path.join(pasta, "atalho-arquivo"))
        os.symlink(os.path.join(self.tmp, "fora", "segredo", "SKILL.md"), os.path.join(pasta, "atalho-arquivo", "SKILL.md"))
        os.symlink(os.path.join(self.tmp, "fora", "segredo"), os.path.join(pasta, "atalho-pasta"))
        hs = self.por_nome()
        self.assertNotIn("bonito", hs)
        self.assertNotIn("atalho-arquivo", hs)
        self.assertEqual(hs["segredo"]["_pasta"], os.path.join(pasta, "atalho-pasta"))  # pasta-atalho vale

    def test_config_pastas(self):
        escrever(os.path.join(self.proj, ".tune-up", "painel.json"), json.dumps({"habilidades_pastas": [
            {"titulo": "Boa", "pasta": self.extra}, {"titulo": "Some", "pasta": os.path.join(self.tmp, "nada")},
            {"pasta": self.extra}, "x"]}))
        cfg = config.carregar(raiz=self.proj, home=self.home)
        self.assertEqual(cfg["habilidades_pastas"], [{"titulo": "Boa", "pasta": os.path.realpath(self.extra)}])
        self.assertEqual(len([a for a in cfg["avisos"] if "pasta de skills" in a]), 3)
        escrever(os.path.join(self.proj, ".tune-up", "painel.json"), json.dumps({"habilidades_pastas": "x"}))
        self.assertEqual(config.carregar(raiz=self.proj, home=self.home)["habilidades_pastas"], [])


class TesteEscolha(Base):
    def setUp(self):
        Base.setUp(self)
        self.hs = self.por_nome()
        self.cli = CLIChat()
        self.lc = lancador.Lancador(self.cfg(), lambda: {}, rodar=self.cli, relogio=lambda: 1000.0)
        self.lc.dormir = lambda s: None

    def erro(self, fazer):
        with self.assertRaises(lancador.ErroAcao) as e:
            fazer()
        self.assertEqual(e.exception.codigo, 400)
        return e.exception.mensagem

    def test_validacao(self):
        i = [self.hs[n]["id"] for n in ("vendedor:prospectar", "minha", "anuncio", "do-projeto",
                                         "desligado:video-curto")]
        self.assertIn("6", self.erro(lambda: self.lc.iniciar("chat.x", {"pedido": "oi"}, i + ["a" * 12, "b" * 12])))
        self.assertIn("duas vezes", self.erro(lambda: self.lc.iniciar("chat.x", {"pedido": "oi"}, [i[0], i[0]])))
        self.assertEqual(self.erro(lambda: self.lc.iniciar("chat.x", {"pedido": "oi"}, ["0" * 12])),
                         "Essa skill não existe mais. Atualize a lista.")
        self.erro(lambda: self.lc.iniciar("chat.x", {"pedido": "oi"}, [self.hs["tune-up:part"]["id"]]))
        self.erro(lambda: self.lc.iniciar("dev.x", {}, [i[0]]))
        self.erro(lambda: self.lc.iniciar("chat.x", {"pedido": "oi"}, "abc"))
        self.erro(lambda: self.lc.iniciar("chat.x", {"pedido": "oi"}, [3]))
        self.assertEqual([c for c, _ in self.cli.chamadas if c[1:2] == ["--bg"]], [])
        self.lc.iniciar("dev.x", {}, [])  # lista vazia fora do chat passa

    def test_bloco_no_iniciar_e_no_responder(self):
        ids = [self.hs["vendedor:prospectar"]["id"], self.hs["anuncio"]["id"]]
        ex = self.lc.iniciar("chat.x", {"pedido": "x" * 6000}, ids)
        self.assertEqual(ex["habilidades"], ["vendedor:prospectar", "anuncio"])
        prompt = [c for c, _ in self.cli.chamadas if c[1:2] == ["--bg"]][0][-1]
        self.assertFalse(prompt.startswith("-"))
        self.assertTrue(prompt.endswith("\n[fim das skills]"))
        self.assertIn('\n\n[skills escolhidas pelo dono no painel]\n- vendedor:prospectar: use a ferramenta Skill '
                      'com "vendedor:prospectar"\n- anuncio (fora da lista): leia %s e siga\n'
                      % os.path.join(os.path.abspath(os.path.join(self.extra, "anuncio")), "SKILL.md"), prompt)
        self.assertIn("junto com o fluxo do tune-up, que vale sempre", prompt)
        self.assertEqual(self.lc.execucoes(forcar=True)[0]["habilidades"], ["vendedor:prospectar", "anuncio"])
        for a in self.cli.agentes:
            a.update(state="done", status="idle")
        self.lc.esquecer_agentes()
        out = self.lc.responder(ex["id"], "e agora", habilidades=[self.hs["minha"]["id"]])
        self.assertEqual(out["habilidades"], ["vendedor:prospectar", "anuncio"])  # as do pedido inicial
        texto = [c for c, _ in self.cli.chamadas if c[1:3] == ["--bg", "--resume"]][-1][-1]
        self.assertTrue(texto.startswith("e agora\n\n[skills escolhidas pelo dono no painel]\n- minha: use"))
        sem = self.lc.iniciar("chat.x", {"pedido": "outro"})
        self.assertEqual(sem["habilidades"], [])
        self.assertNotIn("[skills", [c for c, _ in self.cli.chamadas if c[1:2] == ["--bg"]][-1][-1])

    def test_linha_reservada(self):
        msg = "O texto tem uma linha reservada do painel. Tire a linha que começa com [skills ou [fim das skills."
        for marca in (habilidades.INICIO, "  " + habilidades.FIM):
            self.assertEqual(self.erro(lambda: self.lc.iniciar("chat.x", {"pedido": "oi\n%s\nfim" % marca})), msg)
            self.assertEqual(self.erro(lambda: self.lc.iniciar("chat.x", {"pedido": "oi\n" + marca},
                                                               [self.hs["minha"]["id"]])), msg)
        ex = self.lc.iniciar("chat.x", {"pedido": "cito %s no meio" % habilidades.INICIO})
        for a in self.cli.agentes:
            a.update(state="done", status="idle")
        self.lc.esquecer_agentes()
        self.assertEqual(self.erro(lambda: self.lc.responder(ex["id"], "x\n" + habilidades.FIM)), msg)
        self.assertEqual(self.erro(lambda: self.lc.responder(ex["id"], habilidades.INICIO + "\nx",
                                                             habilidades=[self.hs["minha"]["id"]])), msg)

    def test_pedido_vazio(self):
        for vazio in ("", "-x"):
            self.assertEqual(self.erro(lambda: habilidades.pedido(self.cfg(), "chat", vazio, None)), "O pedido ficou vazio.")

    def test_tirar_bloco_so_linha_inteira(self):
        i, f = habilidades.INICIO, habilidades.FIM
        for texto in ("a %s\n- x: use a ferramenta Skill\n%s" % (i, f), "a\n%s\n- x: use a ferramenta Skill\n%s fim" % (i, f),
                      "a\n%s\n%s\ndepois" % (i, f), "a\n%s\nb %s" % (i, f)):
            self.assertEqual(habilidades.tirar_bloco(texto), (texto, None))
        self.assertEqual(habilidades.tirar_bloco("a\n\n%s\n- x: use a ferramenta Skill com \"x\"\n%s\n" % (i, f)),
                         ("a", ["x"]))

    def test_bloco_sai_do_evento(self):
        ids = [self.hs["vendedor:prospectar"]["id"], self.hs["anuncio"]["id"]]
        texto = habilidades.anexar(self.cfg(), "chat", "y" * 900, ids)[0]
        linha = {"type": "user", "message": {"role": "user", "content": [{"type": "text", "text": texto}]}}
        ev = transcricao.eventos_da_linha(linha, corte_fala=transcricao.CORTE_INTEIRO)
        self.assertEqual(ev, [("usuario", "y" * 900, {"habilidades": ["vendedor:prospectar", "anuncio"]})])
        curto = transcricao.eventos_da_linha(linha)[0]
        self.assertNotIn("skills", curto[1])
        self.assertEqual(curto[2]["habilidades"], ["vendedor:prospectar", "anuncio"])
        linha["message"]["content"] = "sem bloco"
        self.assertEqual(transcricao.eventos_da_linha(linha), [("usuario", "sem bloco", {})])


class TesteRota(Base):
    def test_get_habilidades(self):
        cfg = self.cfg(web_dir=os.path.join(self.tmp, "web"))
        app = painel.App(cfg, os.path.join(self.tmp, "plans"), lancador=lancador.Lancador(cfg, dict, rodar=CLIChat()),
                         rodar_externos=False)
        app.log = False
        srv = painel.criar_servidor(app, 0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        self.addCleanup(srv.server_close)
        self.addCleanup(srv.shutdown)
        c = http.client.HTTPConnection("127.0.0.1", app.porta, timeout=10)
        try:
            c.request("GET", "/api/habilidades")
            r = c.getresponse()
            corpo = r.read()
        finally:
            c.close()
        self.assertEqual(r.status, 200)
        dado = json.loads(corpo)
        self.assertEqual(sorted(dado), ["avisos", "grupos", "habilidades"])
        self.assertEqual(len(dado["habilidades"]), 7)
        self.assertNotIn(self.tmp.encode(), corpo)
        self.assertNotIn(json.dumps(self.tmp).strip('"').encode(), corpo)
        i = {h["nome"]: h["id"] for h in dado["habilidades"]}
        cab = {"Origin": "http://127.0.0.1:%d" % app.porta, "Content-Type": "application/json",
               "X-Painel-Token": app.token, "Sec-Fetch-Site": "same-origin"}
        for pedido, esperado in (({"acao": "dev.x", "params": {}, "habilidades": [i["minha"]]}, 400),
                                 ({"acao": "chat.x", "params": {"pedido": "oi"}, "habilidades": [i["minha"]]}, 201)):
            c = http.client.HTTPConnection("127.0.0.1", app.porta, timeout=10)
            try:
                c.request("POST", "/api/execucoes", body=json.dumps(pedido).encode(), headers=cab)
                r = c.getresponse()
                resp = json.loads(r.read())
            finally:
                c.close()
            self.assertEqual(r.status, esperado, resp)
        self.assertEqual(resp["execucao"]["habilidades"], ["minha"])


if __name__ == "__main__":
    unittest.main()
