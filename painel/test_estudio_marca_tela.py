"""Aba Marca do estúdio refeita (item 10.3): logo, fotos, cores, letras, o negócio, prévia e um botão só.

O módulo real (plugin tune-up-studio) é carregado pelo módulo-ponte de test_estudio_marca. Logo e fotos passam
pela rota de envio de verdade (envio.receber) e pela rota de mídia (midia.abrir). Nada chama o claude.
"""
import sys

sys.dont_write_bytecode = True

import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import struct  # noqa: E402
import time  # noqa: E402
import unittest  # noqa: E402
import zlib  # noqa: E402

import envio  # noqa: E402
import midia  # noqa: E402
import modulos  # noqa: E402
import test_estudio_marca as tem  # noqa: E402
from test_modulos import escrever  # noqa: E402


def png_de(*cores):
    """PNG RGB 2 x N, uma linha por cor (#rrggbb): cada envio com cores diferentes tem bytes diferentes."""
    linhas = b"".join(b"\x00" + bytes.fromhex(c[1:]) * 2 for c in cores)

    def ch(t, c):
        return struct.pack(">I", len(c)) + t + c + struct.pack(">I", zlib.crc32(t + c))
    return (b"\x89PNG\r\n\x1a\n" + ch(b"IHDR", struct.pack(">IIBBBBB", 2, len(cores), 8, 2, 0, 0, 0))
            + ch(b"IDAT", zlib.compress(linhas)) + ch(b"IEND", b""))


MARCA = tem.MARCA


class TesteMarcaTela(tem.TesteMarca):
    def aba(self, nome="marca"):
        abas = modulos.montar(self.cfg, "estudio", usar_cache=False)[1]["abas"]
        return next(a for a in abas if a["id"] == nome)["blocos"]

    def bloco(self, id_):
        return next((b for b in self.aba() if b.get("id") == id_), None)

    def enviar(self, destino, corpo):
        return envio.receber(self.cfg, "estudio", destino, {"Content-Length": str(len(corpo))}, io.BytesIO(corpo))

    def logo(self, corpo):
        os.makedirs(os.path.join(self.pasta, "assets"), exist_ok=True)
        with open(os.path.join(self.pasta, "assets", "logo.png"), "wb") as f:
            f.write(corpo)

    def obj(self):
        with open(self.marca, encoding="utf-8") as f:
            return json.load(f)

    def test_monta_sem_logo_na_ordem_e_sem_sha_na_tela(self):
        blocos = self.aba()
        ids = [b.get("id") or b["tipo"] for b in blocos]
        self.assertEqual(ids, ["texto", "marca-logo", "marca-sem-logo", "marca-fotos", "marca-cores", "marca-letras",
                               "marca-nome", "marca-descricao", "marca-tom", "previa", "marca-confirmar",
                               "marca-procurar", "tabela"])
        logo = self.bloco("marca-logo")
        self.assertNotIn("atual", logo)
        self.assertIn("Não achamos logo", logo["descricao"])
        self.assertNotIn("botao", self.bloco("marca-cores"))  # sem logo PNG/SVG: sem Pegar as cores da logo
        self.assertEqual([i["rotulo"] for i in self.bloco("marca-cores")["itens"]],
                         ["Cor principal", "Cor de destaque", "Fundo", "Fundo secundário", "Texto"])
        self.assertEqual([o["rotulo"] for o in self.bloco("marca-letras")["opcoes"]], ["Clássica", "Moderna", "Forte"])
        self.assertEqual(self.bloco("marca-confirmar")["botao"], "Está certo, usar esta marca")
        sem_fixos = json.dumps([{k: v for k, v in b.items() if k != "dados_fixos"} for b in blocos], ensure_ascii=False)
        self.assertNotIn(self.sha(), sem_fixos)  # o sha256 só vai escondido no botão
        self.assertNotIn("sha", sem_fixos.lower())
        self.assertEqual(self.bloco("marca-confirmar")["dados_fixos"]["sha256"], self.sha())
        tabela = blocos[-1]
        self.assertEqual((tabela["titulo"], tabela["recolhido"]), ("De onde veio cada dado", True))
        self.assertIn("a.css:1", json.dumps(tabela))

    def test_monta_com_logo_achada_no_projeto(self):
        escrever(self.marca, json.dumps(dict(MARCA, logo_copia="assets/logo.png")))
        self.logo(png_de("#112233"))
        logo = self.bloco("marca-logo")
        self.assertEqual((logo["atual"], logo["botao"]), ("estudio/marca/assets/logo.png", "Enviar outra logo"))
        self.assertIn("Achamos esta logo", logo["descricao"])
        self.assertEqual(self.bloco("marca-cores")["botao"]["acao"], "marca.cores_da_logo")
        self.assertEqual(next(b for b in self.aba() if b["tipo"] == "previa")["logo"], "estudio/marca/assets/logo.png")
        aberto = midia.abrir(self.cfg, "estudio", logo["atual"], None)  # a tela consegue mostrar
        self.assertEqual((aberto.codigo, aberto.tipo), (200, "image/png"))
        aberto.fechar()

    def test_enviar_logo_grava_ao_lado_da_marca_trava_e_derruba_aprovacao(self):
        self.aprovar()
        cod, r = self.enviar("logo", png_de("#C8702A", "#5A3220"))
        self.assertEqual((cod, r["avisos"]), (201, []), r)
        self.assertTrue(r["c"].startswith("estudio/marca/assets/"))
        self.assertTrue(os.path.isfile(os.path.join(self.pasta, "assets", r["caminho"].split("/")[-1])))
        logo = self.obj()["campos"]["logo"]
        self.assertEqual((logo["fonte"], logo["travado"]), ("dono", True))
        self.assertEqual(self.obj()["logo_copia"], "assets/logo.png")
        self.assertEqual(self.recusa().codigo, 409)  # logo nova: a aprovação caiu
        self.assertIs(modulos.dono.ler(self.cfg, "estudio")["marca"]["aprovado"], False)  # e foi gravada como caída
        self.assertIn("Esta é a logo que você enviou", self.bloco("marca-logo")["descricao"])
        cod, r2 = self.enviar("logo", png_de("#000000"))  # outra logo: a anterior sai de assets/
        envios = [n for n in os.listdir(os.path.join(self.pasta, "assets")) if envio_nome(n)]
        self.assertEqual((cod, len(envios)), (201, 1))
        # tela e prévia mostram o arquivo enviado (nome muda com o conteúdo), não logo.png: o navegador não reaproveita a velha
        self.assertEqual(self.bloco("marca-logo")["atual"], r2["c"])
        self.assertEqual(next(b for b in self.aba() if b["tipo"] == "previa")["logo"], r2["c"])
        sem = self.bloco("marca-sem-logo")
        self.assertTrue(sem["confirmar"].startswith("Tirar a logo?"))  # apagar a logo pede um sim
        self.assertIs(sem["discreto"], True)

    def test_fotos_em_grade_principal_e_remover(self):
        for cor in ("#FF0000", "#00FF00", "#0000FF"):
            self.assertEqual(self.enviar("fotos", png_de(cor))[0], 201)
            time.sleep(0.01)  # ordem por data de chegada
        fotos = self.obj()["fotos"]
        self.assertEqual([f["principal"] for f in fotos], [True, False, False])
        grade = self.bloco("marca-fotos")
        self.assertEqual([i["rotulo"] for i in grade["itens"]], ["Foto principal", "Foto 2", "Foto 3"])
        primeira = grade["itens"][0]["arquivo"]
        self.aprovar()
        cod, d = self.agir("marca.remover_foto", {"destino": "fotos", "arquivo": primeira})
        self.assertEqual((cod, d["resultado"]["feito"]), (200, True), d)
        self.assertEqual(self.recusa().codigo, 409)
        self.assertFalse(os.path.exists(os.path.join(self.pasta, "fotos", primeira.split("/")[-1])))
        self.assertEqual(self.obj()["fotos"][0], {"arquivo": "fotos/" + grade["itens"][1]["arquivo"].split("/")[-1],
                                                  "principal": True})
        for ruim in ({"destino": "fotos", "arquivo": "estudio/marca/../marca.json"},
                     {"destino": "logo", "arquivo": primeira}, {"destino": "fotos", "arquivo": "x/" + primeira}):
            self.assertIs(self.agir("marca.remover_foto", ruim)[1]["resultado"]["feito"], False, ruim)
        self.assertTrue(os.path.isfile(self.marca))

    def test_limite_de_8_fotos(self):
        for i in range(8):
            self.assertEqual(self.enviar("fotos", png_de("#%06X" % (i + 1)))[0], 201)
        self.assertEqual(self.enviar("fotos", png_de("#ABCDEF"))[0], 409)
        self.assertEqual(len(self.obj()["fotos"]), 8)

    def test_editar_cor_derruba_aprovacao_e_o_passo_3_pede_de_novo(self):
        sha = self.bloco("marca-confirmar")["dados_fixos"]["sha256"]
        cod, d = self.agir("marca.aprovar", {"confirmar": True, "sha256": sha})
        self.assertEqual((cod, d["resultado"]["feito"]), (200, True))
        self.assertIsNone(self.bloco("marca-confirmar"))
        self.assertIn("Marca confirmada", json.dumps(self.aba(), ensure_ascii=False))
        d = self.agir("marca.editar", {"campo": "cores.primary", "valor": "#abcdef"})[1]["resultado"]
        self.assertIn("Está certo, usar esta marca", d["mensagem"])
        self.assertEqual(self.recusa().codigo, 409)
        self.assertIsNotNone(self.bloco("marca-confirmar"))
        self.assertEqual(self.bloco("marca-cores")["itens"][0]["valor"], "#abcdef")
        with open(os.path.join(os.path.dirname(os.path.dirname(tem.REAL)), os.pardir, os.pardir, ".claude-plugin",
                               "plugin.json"), encoding="utf-8") as f:
            versao = json.load(f)["version"]
        escrever(os.path.join(self.cfg["dados_dir"], "ambiente.json"), json.dumps({"pronto": True, "estudio": versao}))
        novo = json.dumps(self.aba("novo"), ensure_ascii=False)
        self.assertIn("confirme de novo", novo)

    def test_aprovar_com_o_botao_da_tela_funciona(self):
        fixos = self.bloco("marca-confirmar")["dados_fixos"]
        cod, d = self.agir("marca.aprovar", fixos)
        self.assertEqual((cod, d["resultado"]["feito"]), (200, True), d)
        self.assertIs(self.aprovado(), True)

    def test_cada_mudanca_derruba_a_aprovacao(self):
        escrever(self.marca, json.dumps(dict(MARCA, logo_copia="assets/logo.png")))
        self.logo(png_de("#C8702A", "#C8702A", "#FFFFFF"))
        for acao, dados in (("marca.letras", {"campo": "letras", "valor": "classica"}),
                            ("marca.tom", {"campo": "tom", "valor": "direto", "ligado": True}),
                            ("marca.editar", {"campo": "nome", "valor": "Forno Novo"}),
                            ("marca.editar", {"campo": "descricao", "valor": "Pão de fermentação natural"}),
                            ("marca.cores_da_logo", {}),
                            ("marca.sem_logo", {"confirmar": True})):
            self.aprovar()
            cod, d = self.agir(acao, dados)
            self.assertEqual((cod, d["resultado"]["feito"]), (200, True), (acao, d))
            self.assertEqual(self.recusa().codigo, 409, acao)
        o = self.obj()
        self.assertEqual((o["campos"]["fontes.heading"]["fonte"], o["tom"]["valor"]), ("dono", ["direto"]))
        self.assertEqual(o["campos"]["cores.primary"], {"valor": "#C8702A", "fonte": "dono", "confianca": "alta",
                                                        "travado": True})
        self.assertEqual((o["campos"]["logo"]["valor"], o["logo_copia"]), (None, None))
        self.assertFalse(os.path.exists(os.path.join(self.pasta, "assets", "logo.png")))

    def test_letras_guardam_o_par_do_projeto(self):
        m = json.loads(json.dumps(MARCA))
        m["campos"]["fontes.heading"] = {"valor": "Lora", "fonte": "a.css:3", "confianca": "alta", "travado": False}
        escrever(self.marca, json.dumps(m))
        self.assertEqual(self.bloco("marca-letras")["valor"], "")
        self.assertEqual(self.bloco("marca-letras")["opcoes"][-1]["fontes"], {"titulo": "Lora", "texto": "Lora"})
        self.agir("marca.letras", {"campo": "letras", "valor": "forte"})
        self.assertEqual(self.bloco("marca-letras")["valor"], "forte")
        self.agir("marca.letras", {"campo": "letras", "valor": "projeto"})  # o par achado continua na lista
        self.assertEqual((self.bloco("marca-letras")["valor"], self.obj()["campos"]["fontes.heading"]["valor"]),
                         ("projeto", "Lora"))
        self.assertIs(self.agir("marca.letras", {"campo": "letras", "valor": "x"})[1]["resultado"]["feito"], False)

    def test_tom_liga_e_desliga(self):
        self.agir("marca.tom", {"campo": "tom", "valor": "formal", "ligado": True})
        self.agir("marca.tom", {"campo": "tom", "valor": "acolhedor", "ligado": True})
        self.agir("marca.tom", {"campo": "tom", "valor": "formal", "ligado": False})
        self.assertEqual(self.obj()["tom"]["valor"], ["acolhedor"])
        self.assertEqual([o["ligado"] for o in self.bloco("marca-tom")["opcoes"]], [True, False, False, False, False])
        self.assertEqual(self.agir("marca.tom", {"campo": "tom", "valor": "formal", "ligado": "sim"})[0], 400)

    def test_cores_da_logo_jpeg_nao_tem_botao_e_recusa(self):
        escrever(self.marca, json.dumps(dict(MARCA, logo_copia="assets/logo.jpg")))
        escrever(os.path.join(self.pasta, "assets", "logo.jpg"), "JPEG")
        self.assertNotIn("botao", self.bloco("marca-cores"))
        d = self.agir("marca.cores_da_logo", {})[1]["resultado"]
        self.assertIs(d["feito"], False)
        self.assertIn("PNG ou SVG", d["mensagem"])

    def test_procurar_de_novo_guarda_fotos_e_tom(self):
        self.enviar("fotos", png_de("#123456"))
        self.agir("marca.tom", {"campo": "tom", "valor": "direto", "ligado": True})
        cod, d = self.agir("marca.redescobrir", {"confirmar": True})
        self.assertEqual((cod, d["resultado"]["feito"]), (200, True), d)
        o = self.obj()
        self.assertEqual((len(o["fotos"]), o["tom"]["valor"]), (1, ["direto"]))

    @unittest.skipIf(not hasattr(os, "symlink") or os.name == "nt", "atalho")
    def test_pasta_de_fotos_atalho_para_fora_e_recusada(self):
        fora = os.path.join(self.tmp, "fora")
        os.makedirs(fora)
        os.symlink(fora, os.path.join(self.pasta, "fotos"))
        self.assertEqual(self.enviar("fotos", png_de("#123456"))[0], 409)
        self.assertEqual(os.listdir(fora), [])
        with open(os.path.join(fora, "0123456789abcdef.png"), "wb") as f:
            f.write(png_de("#123456"))
        r = midia.abrir(self.cfg, "estudio", "estudio/marca/fotos/0123456789abcdef.png", None)
        self.assertEqual(r[0], 404)  # a mídia também não segue o atalho

    def test_base_desconhecida_na_declaracao_e_500(self):
        class Mod:
            INFO = {"envios": {"x": {"pasta": "a", "base": "raiz", "tipos": ["png"], "max_bytes": 9, "max_arquivos": 1}}}
        with self.assertRaises(envio.Recusa) as e:
            envio.declaracao(Mod, "x")
        self.assertEqual(e.exception.codigo, 500)

    def test_gancho_do_envio_nao_sai_pela_rota_de_acao(self):
        cod, _ = self.agir("envio.recebido", {"destino": "logo", "caminho": "estudio/marca/assets/0123456789abcdef.png"})
        self.assertEqual(cod, 400)
        self.assertNotIn("dono", json.dumps(self.obj()["campos"].get("logo") or {}))


for _n in [n for n in vars(tem.TesteMarca) if n.startswith("test_")]:
    setattr(TesteMarcaTela, _n, None)  # herdados: já rodam em test_estudio_marca


def envio_nome(n):
    return len(n) == 20 and n.endswith(".png") and all(c in "0123456789abcdef" for c in n[:16])


if __name__ == "__main__":
    unittest.main()
