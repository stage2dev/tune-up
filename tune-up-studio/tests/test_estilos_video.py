"""The video styles (round 7): the optional "Estilo do vídeo" field of the two video actions, one file per style in
referencias/estilos-video/, the style scene of the kit (scripts/kit_estilos.py) and the QA check `estilo`.
No Chrome, no network."""
import json
import os
import re
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
STUDIO = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(STUDIO, "scripts"))
sys.path.insert(0, HERE)

import kit_estilos  # noqa: E402
import kit_video  # noqa: E402
import qa_atencao  # noqa: E402
import qa_quadros  # noqa: E402
from test_kit import Base, falhas  # noqa: E402
from test_referencias import LEITURA, PROIBIDOS, TIQUES_RE, ler  # noqa: E402

PASTA = os.path.join(STUDIO, "referencias", "estilos-video")
ACOES = os.path.join(STUDIO, "painel", "acoes", "estudio.json")
SECOES = ("## Use it when", "## Slots of scene 2", "## Storyboard, 10 s", "## 15 s", "## Where the method enters",
          "## Never")
# One filled scene per style, from the example bakery's briefing (the facts the QA finds in entrada.md).
CENA = {
    "tipografia-cinetica": {"tipografia": {"linhas": ["Massa feita", "na véspera", "pão às 6h"]}},
    "conversa-de-whatsapp": {"conversa": {"pergunta": "Tem pão cedo?", "respostas": ["Sai às 6h", "Reserve hoje"]}},
    "lista-que-se-marca-sozinha": {"lista": {"titulo": "Na véspera", "itens": ["Massa feita", "Fermenta 24 horas"]}},
    "contador-e-grafico": {"contador": {"numero": "24", "rotulo": "horas de fermentação", "apoio": "fornadas pequenas"}},
    "antes-e-depois": {"antes_depois": {"antes": "Cesta vazia", "depois": "Pão reservado"}},
    "tela-com-cursor-clicando": {"tela": {"titulo": "Reserve com um clique", "botao": "Reservar pão", "feito": "Pão reservado"}},
    "cartaz-que-se-monta": {"cartaz": {"blocos": ["Fornada", "pequena", "acaba cedo"]}},
    "passo-a-passo": {"passos": {"titulo": "Como reservar", "itens": ["Mande mensagem", "Busque às 6h"]}},
    "mito-ou-verdade": {"mito": {"frase": "Pão bom acaba cedo", "selo": "verdade", "resposta": "Fornadas pequenas"}},
    "produto-em-destaque": {},
}


def slug(rotulo):
    sem = unicodedata.normalize("NFKD", rotulo).encode("ascii", "ignore").decode("ascii")
    return "-".join(sem.lower().split())


def arquivos():
    return sorted(n[:-3] for n in os.listdir(PASTA) if n.endswith(".md"))


def texto_de(nome):
    with open(os.path.join(PASTA, nome + ".md"), encoding="utf-8") as f:
        return f.read()


class Campo(Base):
    def opcoes(self):
        with open(ACOES, encoding="utf-8") as f:
            acoes = {a["id"]: a for a in json.load(f)["acoes"]}
        return [{p["nome"]: p for p in acoes[k]["params"]}["estilo"] for k in ("estudio.video", "estudio.video-motion")]

    def test_campo_opcional_com_a_ia_escolhe_primeiro_e_8_a_12_estilos(self):
        for campo in self.opcoes():
            self.assertEqual((campo["tipo"], campo["obrigatorio"], campo["opcoes"][0]), ("escolha", False, "a IA escolhe"))
            self.assertTrue(8 <= len(campo["opcoes"]) - 1 <= 12, campo["opcoes"])

    def test_cada_opcao_tem_um_arquivo_e_um_estilo_no_kit(self):
        for campo in self.opcoes():
            nomes = [slug(o) for o in campo["opcoes"][1:]]
            self.assertEqual(sorted(nomes), arquivos())                 # one file per option, no file left over
            self.assertEqual(sorted(nomes), sorted(kit_estilos.ESTILOS))  # and the kit assembles each of them
            self.assertEqual(sorted(nomes), qa_atencao.estilos_video())
            tabela = ler("kit-video.md").split("## Styles", 1)[1].split("\n## ", 1)[0]
            for rotulo, nome in zip(campo["opcoes"][1:], nomes):   # the skill finds the file from the prompt's label
                self.assertIn("| %s | `%s` |" % (rotulo, nome), tabela)

    def test_skill_le_so_o_arquivo_do_estilo_escolhido(self):
        with open(os.path.join(STUDIO, "skills", "video", "SKILL.md"), encoding="utf-8") as f:
            skill = f.read()
        self.assertIn("referencias/estilos-video/", skill)
        self.assertIn("that one only: never open or list the other style files", skill)
        for nome in arquivos():                # no style is named in the skill: only the table of kit-video.md does
            self.assertNotIn(nome, skill)
        self.assertIn("estilo: <the style's file name", skill)

    def test_orcamento_de_linhas_lidas_pela_skill_de_video(self):
        base = sum(len(ler(n).splitlines()) for n in LEITURA["video"])
        maior = max(len(texto_de(n).splitlines()) for n in arquivos())
        self.assertLessEqual(base + maior, 460)   # the same ceiling as the other skills: one style file is read


class Arquivos(Base):
    def test_cada_arquivo_passa_nas_checagens_das_referencias(self):
        for nome in arquivos():
            texto = texto_de(nome)
            linhas = texto.splitlines()
            self.assertLess(len(linhas), 60, nome)
            self.assertTrue(linhas[0].startswith("# Video style: "), nome)
            self.assertTrue(linhas[2].startswith("Read by the video skill only when"), nome)
            self.assertIn('`"estilo": "%s"`' % nome, linhas[2], nome)
            for p in PROIBIDOS + ("webgl", "three.js", "anime.js"):
                self.assertNotIn(p, texto.lower(), "%s: %s" % (nome, p))
            self.assertNotIn("—", texto, nome)
            self.assertEqual(TIQUES_RE.findall(texto), [], nome)
            posicoes = [texto.find(s) for s in SECOES]
            self.assertEqual(posicoes, sorted(posicoes), nome)       # every section, in this order
            self.assertNotIn(-1, posicoes, nome)
            self.assertIn("NOTICE", linhas[3], nome)                 # where the idea came from
            self.assertGreaterEqual(len(re.findall(r"^- ", texto.split("## Never", 1)[1], re.M)), 3, nome)

    def test_cada_arquivo_fala_do_seu_slot_e_dos_tempos_do_kit(self):
        for nome, cena in kit_estilos.ESTILOS.items():
            texto = texto_de(nome)
            cena = cena or "rampa"
            self.assertIn("`%s`" % cena, texto, nome)
            tempos = kit_video.roteiro({"estilo": nome}, 10)[2]
            cortes = [sum(tempos[:i]) for i in range(1, len(tempos))]
            self.assertIn("Cuts at %s" % ", ".join(("%.3f" % c).rstrip("0") for c in cortes[:-1]), texto, nome)
            self.assertIn("Cuts at 1.875, 4.875, 7.875 and 10.875 s", texto, nome)

    def test_moldes_dos_estilos_entram_no_teste_de_troca(self):
        self.assertIn("entrega buque hoje", qa_atencao._moldes())    # a mold of conversa-de-whatsapp.md
        self.assertIn("congelado e sem gosto", qa_atencao._moldes())  # and of mito-ou-verdade.md


class Kit(Base):
    def reel(self, estilo, duracao=10, **trocas):
        with open(os.path.join(self.trabalho, "estrategia.md"), encoding="utf-8") as f:
            linhas = [l for l in f.read().splitlines() if not l.startswith("estilo:")]
        with open(os.path.join(self.trabalho, "estrategia.md"), "w", encoding="utf-8") as f:
            f.write("\n".join(linhas + ["estilo: %s | teste" % estilo]) + "\n")
        extra = dict(CENA[estilo], estilo=estilo, **trocas)
        if duracao == 15 and estilo == "produto-em-destaque":
            extra["lista"] = CENA["lista-que-se-marca-sozinha"]["lista"]
        return self.montar("--tipo", "video", "--peca", self.peca("video-9x16", **extra), "--duracao", str(duracao),
                           "--out", os.path.join(self.trabalho, "fonte"))

    def test_cada_estilo_monta_e_passa_na_atencao_em_10_e_15_s(self):
        for estilo in kit_estilos.ESTILOS:
            for duracao in (10, 15):
                code, out, err = self.reel(estilo, duracao)
                self.assertEqual((code, err), (0, ""), (estilo, duracao))
                self.assertIn("estilo %s," % estilo, out)
                fonte = os.path.join(self.trabalho, "fonte")
                self.assertEqual(falhas(qa_atencao.checar_video(fonte, duracao, "hyperframes")), [], (estilo, duracao))
                self.assertIn('data-estilo="%s"' % estilo, self.ler("fonte", "index.html"))

    def test_cena_de_estilo_tem_batida_a_cada_meio_segundo_e_abre_inteira(self):
        """Scene 2 of every style: 3 or more beats that start 0.4 s or more apart, the last one by 2.1 s, and no
        entry on its title (it is whole at the cut)."""
        for estilo, cena in kit_estilos.ESTILOS.items():
            if cena is None:
                continue
            self.assertEqual(self.reel(estilo)[0], 0, estilo)
            html = self.ler("fonte", "index.html")
            script = html.split("M.pronto", 1)[0].rsplit("})();", 1)[1]
            t0, tempos = 1.625, set()
            for linha in script.splitlines():
                if not re.search(r'"[sa]2_', linha):
                    continue
                m = re.match(r'\s*M\.(entra|palavras|contador)\("[^"]+", ([\d.]+)', linha)
                if m:
                    tempos.add(float(m.group(2)))                     # a delay from the cut
                m = re.match(r'\s*M\.(traco)\("[^"]+", ([\d.]+)', linha) or re.match(r'\s*M\.(onda)\(\[[^\]]+\], ([\d.]+)', linha)
                if m:
                    tempos.add(float(m.group(2)) - t0)                # an absolute time
                m = re.match(r'\s*M\.trilha\("[^"]+", "(?:transform|opacity)", \[\[([\d.]+)', linha)
                if m and float(m.group(1)) > 0:
                    tempos.add(float(m.group(1)) - t0)
            batidas = []
            for t in sorted(tempos):
                if not batidas or t - batidas[-1] >= 0.4:
                    batidas.append(t)
            self.assertGreaterEqual(len(batidas), 3, (estilo, sorted(tempos)))
            self.assertLessEqual(max(tempos), 2.1, estilo)
            self.assertGreaterEqual(max(tempos), 1.2, estilo)          # the scene does not park after its first second
            self.assertEqual(qa_quadros.check_texto_inteiro(html, [
                {"id": "s2_titulo", "tag": "p", "attrs": {}, "classes": [], "texto": ["x"]}])["details"], ["ok"], estilo)

    def test_reel_com_estilo_tem_cortes_fora_da_grade_e_gancho_mais_curto(self):
        self.assertEqual(self.reel("conversa-de-whatsapp")[0], 0)
        html = self.ler("fonte", "index.html")
        cortes = sorted({float(s) for s in re.findall(r'id="s[2-9]_titulo"[^>]*data-start="([\d.]+)"', html)})
        self.assertEqual(cortes, [1.625, 4.375, 6.875])
        for corte in cortes:
            self.assertGreaterEqual(min(corte % 0.25, 0.25 - corte % 0.25), 0.1)
        self.assertRegex(html, r'M\.trilha\("s4_cursor", "transform"')   # the end card's cursor presses the contact
        self.assertRegex(html, r'M\.entra\("s1_barra"')                  # the hook changes before its first second ends

    def test_antes_e_depois_transforma_o_heroi_na_cena_2(self):
        self.assertEqual(self.reel("antes-e-depois")[0], 0)
        some = re.search(r'M\.trilha\("h_antes\d*", "opacity", \[\[0, "1"\], \[([\d.]+)', self.ler("fonte", "index.html"))
        self.assertIsNotNone(some)
        self.assertLess(float(some.group(1)), 4.375)   # in the style scene, not in the offer scene
        self.assertEqual(self.reel("conversa-de-whatsapp")[0], 0)
        some = re.search(r'M\.trilha\("h_antes\d*", "opacity", \[\[0, "1"\], \[([\d.]+)', self.ler("fonte", "index.html"))
        self.assertGreater(float(some.group(1)), 4.375)

    def test_recusas_com_o_motivo(self):
        casos = (("estilo-novo", {}, 'estilo "estilo-novo" não existe'),
                 ("contador-e-grafico", {"contador": {"numero": "R$ 24", "rotulo": "a cesta"}}, "preço, porcentagem"),
                 ("contador-e-grafico", {"contador": {"numero": "90%", "rotulo": "de aprovação"}}, "só algarismos"),
                 ("conversa-de-whatsapp", {"conversa": {"pergunta": "Tem pão cedo?", "respostas": []}}, "precisa de 1 a 2"),
                 ("conversa-de-whatsapp", {"conversa": {"pergunta": "Tem pão quentinho bem cedo?",
                                                         "respostas": ["Sai às 6h em ponto", "Reserve hoje mesmo aqui"]}},
                  "palavras (máximo 8"),
                 ("mito-ou-verdade", {"mito": {"frase": "Pão bom acaba", "selo": "talvez", "resposta": "Sim"}}, "mito.selo"),
                 ("cartaz-que-se-monta", {"cartaz": {"blocos": ["Fornada pequena demais", "acaba"]}}, "14"))
        for estilo, trocas, motivo in casos:
            CENA.setdefault(estilo, {})
            code, _, err = self.reel(estilo, **trocas)
            self.assertEqual(code, 1, (estilo, trocas))
            self.assertIn(motivo, err, estilo)
        CENA.pop("estilo-novo")


class QaEstilo(Base):
    def test_estilo_verde_e_vermelho(self):
        pasta = self.trabalho
        self.assertTrue(qa_atencao.check_estilo(pasta, "produto-em-destaque")["ok"])   # the example names it
        self.assertFalse(qa_atencao.check_estilo(pasta, "passo-a-passo")["ok"])         # built with another one
        self.assertIn("montado com 'passo-a-passo'", qa_atencao.check_estilo(pasta, "passo-a-passo")["details"][0])
        caminho = os.path.join(pasta, "estrategia.md")
        with open(caminho, encoding="utf-8") as f:
            texto = f.read()
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(re.sub(r"(?m)^estilo:.*\n", "", texto))
        self.assertIn("sem estilo", qa_atencao.check_estilo(pasta, "")["details"][0])
        with open(caminho, "w", encoding="utf-8") as f:
            f.write(texto.replace("estilo: produto-em-destaque", "estilo: desenho animado"))
        self.assertIn("não existe", qa_atencao.check_estilo(pasta, "")["details"][0])


class Acabamento(Base):
    """Round 7 fixes of the kit that are not about a style."""

    def test_largura_de_traco_do_desenho_e_respeitada(self):
        # a class rule with stroke-width would beat every stroke-width attribute (CSS wins over presentation
        # attributes): the kit's CSS sets none and a stroke without a width gets 14 px as an attribute
        import kit_base
        self.assertNotIn("stroke-width", kit_base.HEROI_CSS)
        caminho = os.path.join(self.trabalho, "h.svg")
        with open(caminho, "w", encoding="utf-8") as f:
            f.write('<svg viewBox="0 0 1000 1000"><g id="h_corpo">%s<path class="lt" d="M0 0 L9 9"/>'
                    '<path class="la" stroke-width="30" d="M0 0 L9 9"/></g></svg>'
                    % "".join('<rect class="p" x="%d" y="400" width="40" height="500"/>' % (100 + 60 * i) for i in range(12)))
        corpo, _ = kit_base.heroi(caminho)
        self.assertIn('<path class="lt" d="M0 0 L9 9" stroke-width="14"/>', corpo)
        self.assertIn('<path class="la" stroke-width="30" d="M0 0 L9 9"/>', corpo)
        self.assertEqual(corpo.count("stroke-width"), 2)   # a fill gets none

    def test_heroi_mais_baixo_antes_enche_o_gancho(self):
        def escala(**trocas):
            code, _, err = self.montar("--tipo", "video", "--peca", self.peca("video-9x16", **trocas), "--out",
                                       os.path.join(self.trabalho, "fonte"))
            self.assertEqual((code, err), (0, ""))
            return float(re.search(r'M\.trilha\("heroi_quadro", "transform", \[\[0, "[^"]*scale\(([\d.]+)\)',
                                   self.ler("fonte", "index.html")).group(1))
        self.assertGreater(escala(heroi_topo_antes=320), escala(heroi_topo_antes=90) + 0.15)

    def test_post_chamada_longa_em_duas_linhas_e_recusa_o_que_nao_cabe(self):
        cta = {"chamada": "Reserve hoje o pão quentinho de amanhã cedo", "condicao": "pelo WhatsApp", "canal": "whatsapp"}
        code, _, err = self.montar("--tipo", "post", "--peca", self.peca("post-4x5", cta=cta), "--out",
                                   os.path.join(self.trabalho, "q1", "fonte"))
        self.assertEqual((code, err), (0, ""))
        html = self.ler("q1", "fonte", "index.html")
        self.assertRegex(html, r'<p id="cta">[^<]+<br>[^<]+<span class="cond">')   # two lines, inside the frame
        self.assertEqual(falhas(qa_atencao.checar_quadro(os.path.join(self.trabalho, "q1", "fonte"))), [])
        cta["condicao"] = "pelo WhatsApp (11) 4002-8922 de segunda a sábado até 18h"
        code, _, err = self.montar("--tipo", "post", "--peca", self.peca("post-4x5", cta=cta), "--out",
                                   os.path.join(self.trabalho, "q1", "fonte"))
        self.assertEqual(code, 1)
        self.assertIn("cta.condicao não cabe na faixa", err)

    def test_post_oferta_o_cartao_nao_cobre_o_desenho(self):
        code, out, err = self.montar("--tipo", "post", "--peca", self.peca("post-4x5", composicao="oferta"), "--out",
                                     os.path.join(self.trabalho, "q1", "fonte"))
        self.assertEqual((code, err), (0, ""))
        lado = int(re.search(r"heroi: (\d+) px", out).group(1))
        self.assertLessEqual(lado * 0.95, 1080 - 524 - 14)   # the drawing's 95% ends before the card and its shadow

    def test_toque_do_cartao_final_e_anel_sem_border_radius(self):
        code, _, err = self.montar("--tipo", "video", "--peca", self.peca("video-9x16"), "--out",
                                   os.path.join(self.trabalho, "fonte"))
        self.assertEqual((code, err), (0, ""))
        html = self.ler("fonte", "index.html")
        self.assertNotIn("border-radius", html)          # the default reel keeps its square finish (no pill)
        self.assertRegex(html, r'<svg id="s4_onda"[^>]*><circle class="l[a-z]" stroke-width="16"')
        self.assertRegex(html, r'M\.trilha\("s4_cursor", "opacity", \[\[[\d.]+, "1", "reta"\], \[[\d.]+, "0"\]\]\)')
