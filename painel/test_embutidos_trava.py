"""Código dos embutidos guardado como o painel/ (fix do item A1): checkout fora de ~/.claude, travas reais.

O plugin roda de um checkout (`claude --plugin-dir <repo>`): <tmp>/dev/tune-up com painel/, tune-up-studio/,
vendas/ e tune-up-mkt/. As travas saem de travas.argv_travas (o mesmo caminho do lançador) e o gancho decide com travas.decidir.
"""
import sys

sys.dont_write_bytecode = True

import json  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from unittest import mock  # noqa: E402

import catalogo  # noqa: E402
import config  # noqa: E402
import embutidos  # noqa: E402
import modulos  # noqa: E402
import trabalho  # noqa: E402
import travas  # noqa: E402
from test_estudio_hf import ACOES, STUDIO_REAL, acoes_reais, gancho  # noqa: E402
from test_travas import ACAO_CODIGO, ACAO_LEITURA  # noqa: E402

MODULO_VENDAS = ("vendas", "painel", "modulos", "vendas", "modulo.py")
MODULO_ESTUDIO = ("tune-up-studio", "painel", "modulos", "estudio", "modulo.py")
MODULO_MKT = ("tune-up-mkt", "painel", "modulos", "mkt", "modulo.py")
INFO = 'INFO = {"titulo": "X"}\ndef montar(ctx):\n    return {}\n'


def escrever(caminho, texto=""):
    os.makedirs(os.path.dirname(caminho), exist_ok=True)
    with open(caminho, "w", encoding="utf-8") as f:
        f.write(texto)


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.raiz = os.path.join(self.tmp, "dev", "tune-up")
        self.studio = os.path.join(self.raiz, "tune-up-studio")
        escrever(os.path.join(self.raiz, "painel", "painel.py"))
        escrever(os.path.join(self.raiz, *MODULO_VENDAS), INFO)
        escrever(os.path.join(self.raiz, *MODULO_ESTUDIO), INFO)
        escrever(os.path.join(self.raiz, *MODULO_MKT), INFO)
        escrever(os.path.join(self.studio, "painel", "acoes", "estudio.json"))
        shutil.copyfile(ACOES, os.path.join(self.studio, "painel", "acoes", "estudio.json"))
        escrever(os.path.join(self.studio, "scripts", "qa_imagem.py"))
        escrever(os.path.join(self.studio, "referencias", "marca.md"), "# marca\n")
        os.makedirs(os.path.join(self.studio, "node"))
        shutil.copyfile(os.path.join(STUDIO_REAL, "node", "package-lock.json"),
                        os.path.join(self.studio, "node", "package-lock.json"))
        self.hf = os.path.join(self.studio, "node", "node_modules", ".bin", "hyperframes")
        escrever(self.hf)
        self.usar_painel(os.path.join(self.raiz, "painel"))
        ws = os.path.join(self.tmp, "proj")
        pacote = os.path.join(ws, ".tune-up", "painel")
        self.cfg = {"home": os.path.join(self.tmp, "casa"), "workspace": ws, "pacote_dir": pacote,
                    "dados_dir": os.path.join(pacote, "dados"), "painel_dir": config.PAINEL, "modulos": [],
                    "bruto": {}}
        os.makedirs(self.cfg["dados_dir"])
        self.trab = os.path.join(self.cfg["dados_dir"], "trabalhos", "abc")
        modulos.esquecer()
        self.addCleanup(modulos.esquecer)

    def usar_painel(self, painel):
        p = mock.patch.object(config, "PAINEL", painel)
        p.start()
        self.addCleanup(p.stop)

    def conf_estudio(self, aid="estudio.post"):
        acao = [a for a in acoes_reais() if a["id"] == aid][0]
        est = embutidos.estudio_da_acao(self.cfg, acao)
        return gancho(trabalho.resolver_travas(acao, self.trab, est), self.cfg)


class TesteCodigoGuardado(Base):
    def alvos(self, raiz):
        return [os.path.join(raiz, *MODULO_VENDAS),
                os.path.join(raiz, "vendas", "painel", "modulos", "vendas", "json.py"),  # irmão com nome da stdlib
                os.path.join(raiz, "vendas", "servico", "servico.py"),
                os.path.join(raiz, *MODULO_ESTUDIO),
                os.path.join(raiz, "tune-up-studio", "painel", "acoes", "estudio.json"),
                os.path.join(raiz, "tune-up-studio", "scripts", "preparar_estudio.py"),
                os.path.join(raiz, "tune-up-studio", "node", "node_modules", ".bin", "hyperframes"),
                os.path.join(raiz, *MODULO_MKT),
                os.path.join(raiz, "tune-up-mkt", "painel", "modulos", "mkt", "rodar_conferencia.py"),
                os.path.join(raiz, "tune-up-mkt", "scripts", "contas.py")]

    def casos(self, raiz):
        for alvo in self.alvos(raiz):
            for f in ("Write", "Edit"):
                yield f, {"file_path": alvo, "content": "x", "old_string": "a", "new_string": "b"}
            for cmd in ("echo x >> %s", "cp /tmp/x %s", "mv /tmp/x %s", "rm %s", "sed -i s/a/b/ %s",
                        "ln -s /tmp/x %s"):
                yield "Bash", {"command": cmd % alvo}

    def confere(self, conf, raiz, rotulo):
        for ferramenta, entrada in self.casos(raiz):
            with self.subTest(acao=rotulo, ferramenta=ferramenta, entrada=entrada):
                got = travas.decidir(conf, ferramenta, entrada, self.trab)
                self.assertIsNotNone(got)
                self.assertIn(got[0], ("deny", "ask"))

    def test_sessao_nao_grava_o_codigo_dos_embutidos(self):
        for acao in (ACAO_CODIGO, ACAO_LEITURA, dict(ACAO_CODIGO, id="x.r", risco="rascunho")):
            conf = gancho(catalogo.validar_acao(acao), self.cfg)
            self.assertFalse(conf["sb"])
            self.confere(conf, self.raiz, acao["risco"])

    def test_ligado_ou_desligado_a_protecao_e_a_mesma(self):
        conf = gancho(catalogo.validar_acao(ACAO_CODIGO), self.cfg)
        embutidos.mudar(self.cfg, "vendas", {"ligado": True})
        self.assertEqual(gancho(catalogo.validar_acao(ACAO_CODIGO), self.cfg)["prot"], conf["prot"])
        for nome in embutidos.PASTAS_CODIGO:
            self.assertIn(os.path.join(self.raiz, nome), conf["prot"])

    @unittest.skipUnless(hasattr(os, "symlink") and os.name != "nt", "symlink")
    def test_raiz_por_atalho_protege_as_duas_formas(self):
        atalho = os.path.join(self.tmp, "atalho")
        os.symlink(self.raiz, atalho)
        self.usar_painel(os.path.join(atalho, "painel"))
        conf = gancho(catalogo.validar_acao(ACAO_CODIGO), dict(self.cfg, painel_dir=config.PAINEL))
        self.confere(conf, atalho, "atalho")
        self.confere(conf, self.raiz, "real")

    @unittest.skipIf(os.name == "nt", "Estúdio indisponível no Windows nativo (sem sandbox); caminho em barras POSIX")
    def test_acao_do_estudio_ainda_roda_o_binario_e_os_scripts(self):
        scripts = os.path.join(self.studio, "scripts") + os.sep
        for aid in ("estudio.post", "estudio.video"):
            conf = self.conf_estudio(aid)
            self.assertTrue(conf["sb"])
            self.assertEqual(conf["exe"], [self.hf])  # checkout: o binário mora dentro da pasta protegida
            for cmd in (self.hf + " check fonte --json --strict", self.hf + " render fonte -o saida.mp4",
                        "python3 -I %sqa_imagem.py --achados fonte" % scripts,
                        "python3 -I -B %sqa_imagem.py --source fonte --png %s/a.png" % (scripts, self.trab)):
                with self.subTest(acao=aid, cmd=cmd):
                    self.assertIsNone(travas.decidir(conf, "Bash", {"command": cmd}, self.trab))
                    sem = dict(conf, exe=[], py=None)  # sem a isenção exata: a pasta protegida nega
                    self.assertEqual(travas.decidir(sem, "Bash", {"command": cmd}, self.trab)[0], "deny")
            for cmd in (self.hf + " check fonte; cp a " + self.hf, "cp a %sqa_imagem.py" % scripts,
                        self.hf + " render fonte -o " + os.path.join(self.studio, "kit", "x.mp4")):
                with self.subTest(acao=aid, cmd=cmd):
                    self.assertEqual(travas.decidir(conf, "Bash", {"command": cmd}, self.trab)[0], "deny")

    def test_leitura_da_arvore_protegida_segue_livre(self):
        ref = os.path.join(self.studio, "referencias", "marca.md")
        confs = [self.conf_estudio()] + [gancho(catalogo.validar_acao(a), self.cfg) for a in (ACAO_LEITURA,
                                                                                             ACAO_CODIGO)]
        for conf in confs:
            for ferramenta, entrada in (("Read", {"file_path": ref}),
                                        ("Read", {"file_path": os.path.join(self.studio, "formatos.json")}),
                                        ("Glob", {"pattern": "*.md", "path": os.path.dirname(ref)}),
                                        ("Grep", {"pattern": "x", "path": os.path.join(self.studio, "kit")}),
                                        ("Bash", {"command": "cat " + ref}),
                                        ("Bash", {"command": "ls " + os.path.join(self.studio, "kit")})):
                if ferramenta == "Bash" and conf is confs[0]:
                    continue  # a ação do Estúdio nega `cat`/`ls` pela regra dela (só ffmpeg, python3, hyperframes)
                with self.subTest(conf=conf["leve"], ferramenta=ferramenta, entrada=entrada):
                    self.assertIsNone(travas.decidir(conf, ferramenta, entrada, self.trab))


@unittest.skipUnless(hasattr(os, "symlink") and os.name != "nt", "symlink")
class TesteAtalho(Base):
    def ligar(self, mid):
        self.assertEqual(embutidos.mudar(self.cfg, mid, {"ligado": True})[0], 200)

    def test_modulo_que_e_atalho_nao_carrega(self):
        self.ligar("vendas")
        self.assertEqual(modulos.caminho_do_modulo(self.cfg, "vendas"), os.path.join(self.raiz, *MODULO_VENDAS))
        arq = os.path.join(self.raiz, *MODULO_VENDAS)
        fora, dentro = os.path.join(self.tmp, "fora.py"), os.path.join(os.path.dirname(arq), "outro.py")
        escrever(fora, INFO)
        escrever(dentro, INFO)
        for alvo in (fora, dentro):
            os.remove(arq)
            os.symlink(alvo, arq)
            with self.subTest(alvo=alvo):
                self.assertIsNone(embutidos.caminho("vendas"))
                with self.assertRaises(modulos.ErroModulo) as e:
                    modulos.caminho_do_modulo(self.cfg, "vendas")
                self.assertIn("é atalho", " ".join(e.exception.avisos))

    def test_pasta_do_modulo_que_e_atalho_nao_carrega(self):
        self.ligar("estudio")
        pasta = os.path.dirname(os.path.join(self.raiz, *MODULO_ESTUDIO))
        fora = os.path.join(self.tmp, "fora-estudio")
        shutil.move(pasta, fora)
        os.symlink(fora, pasta)
        self.assertIsNone(embutidos.caminho("estudio"))
        with self.assertRaises(modulos.ErroModulo):
            modulos.caminho_do_modulo(self.cfg, "estudio")

    def test_pasta_de_acoes_que_e_atalho_nao_carrega(self):
        self.ligar("estudio")
        acoes = os.path.join(self.studio, "painel", "acoes")
        self.assertEqual(embutidos.pastas_de_acoes(self.cfg), [acoes])
        fora = os.path.join(self.tmp, "fora-acoes")
        shutil.move(acoes, fora)
        os.symlink(fora, acoes)
        self.assertEqual(embutidos.pastas_de_acoes(self.cfg), [])


class TesteNegarSemArquivo(Base):
    def test_vendas_usado_e_arquivo_apagado_mantem_as_regras(self):
        self.assertEqual(embutidos.negar(self.cfg), [])  # nunca usado: sem pasta, sem arquivo, sem regra
        embutidos.mudar(self.cfg, "vendas", {"ligado": True})
        os.makedirs(os.path.join(self.cfg["home"], "Library", "Application Support", "tune-up-vendas"))
        os.remove(os.path.join(self.cfg["dados_dir"], embutidos.ARQUIVO))
        self.assertEqual(embutidos.negar(self.cfg), list(embutidos.NEGAR_VENDAS))
        self.assertEqual(embutidos.ligados(self.cfg), [])  # a pasta só mantém as regras, não liga
        shutil.rmtree(self.cfg["dados_dir"])  # a pasta de dados do painel inteira some
        self.assertEqual(embutidos.negar(self.cfg), list(embutidos.NEGAR_VENDAS))

    def test_as_tres_pastas_de_dados_contam(self):
        for d in embutidos.PASTAS_DADOS_VENDAS:
            casa = os.path.join(self.tmp, "casa-" + str(abs(hash(d))))
            os.makedirs(os.path.join(casa, d[2:]))
            self.assertEqual(embutidos.negar(dict(self.cfg, home=casa)), list(embutidos.NEGAR_VENDAS), d)


if __name__ == "__main__":
    unittest.main()
