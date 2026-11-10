"""Testes do leitor com trechos sintéticos (sem dado real). Rode: python3 -m unittest -v"""
import sys

sys.dont_write_bytecode = True

import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402

import leitor  # noqa: E402
import painel  # noqa: E402

NOMES = dict(leitor.NOMES_PADRAO)

GOAL = """# Fase 900 - Teste

## Partes (um contexto por Parte)

| Parte | Itens | Pré-requisito | Comando |
|---|---|---|---|
| A | A.0-A.3 | nenhum | `/goal Fase 900 Parte A` |
| B | B.1 | A | `/goal Fase 900 Parte B` |
| B-extra | B.9 | B | `/goal Fase 900 Parte B-extra` |
| G1 | G1.0 | nenhum | `/goal Fase 900 Parte G1` |
"""

PROGRESS = """# Fase 900 - PROGRESS

## OPEN QUESTIONS

- Q1: qual remetente usar?
- Q2 (respondida): cor do botão.

## Estado

- Ordem: `/goal Fase 900 Parte B - Stop when: "Parte B fechada" in progress OR you wrote PRECISO DE VOCÊ: OR 40 turns.`
- Regra: ao fechar, escreva "Parte X fechada" aqui.

## Parte A (em andamento)

- **A.1** - executor. Revisão: failures `CRÍTICO 0, ALTO 0`; security `ALTO 1` (teto fura).
- **A.1 volta 2** - executor novo. Revisão: security `ALTO 0`.
- **A.2** - revisão: falhas ALTO 2→1→0 em 3 voltas.
- **A.3 v1** - silent-failure REPROVADO: HIGH 1 playbook sem conferir aceite.

### Parte A fechada (01/01/2030) — PR #12

## Parte G1

- **G1.0** - executor. Revisão: `CRÍTICO 0, ALTO 0`.

PRECISO DE VOCÊ: aplicar a migration da Parte G1 antes do merge.
"""


class TestTabelaDePartes(unittest.TestCase):
    def test_le_tabela_do_goal(self):
        partes = leitor.partes_do_goal(GOAL)
        self.assertEqual([p["id"] for p in partes], ["A", "B", "B-extra", "G1"])
        self.assertEqual(partes[0]["itens_plano"], "A.0-A.3")
        self.assertEqual(partes[1]["prerequisito"], "A")

    def test_sem_tabela_volta_lista_vazia(self):
        self.assertEqual(leitor.partes_do_goal("# Fase\n\nsem tabela"), [])
        self.assertEqual(leitor.partes_do_goal(None), [])

    def test_recusa_linha_que_nao_e_id(self):
        texto = "| Parte | Branch |\n|---|---|\n| Backend + migrations | x |\n| Tela | y |\n| A1b | z |\n"
        self.assertEqual([p["id"] for p in leitor.partes_do_goal(texto)], ["A1b"])

    def test_plano_b_pelos_titulos(self):
        texto = "# F\n### Parte A — base\n### Parte A-mfa — MFA\n"
        self.assertEqual([p["id"] for p in leitor.partes_de_titulos(texto)], ["A", "A-mfa"])


class TestProgress(unittest.TestCase):
    def setUp(self):
        self.ids = ["A", "B", "B-extra", "G1"]
        self.res = leitor.analisar_progress(PROGRESS, self.ids, NOMES)

    def test_marcador_de_parte_fechada(self):
        self.assertEqual(sorted(self.res["fechadas"]), ["A"])
        self.assertIn("Parte A fechada", self.res["fechadas"]["A"]["trecho"])

    def test_marcador_entre_aspas_ou_codigo_nao_conta(self):
        self.assertNotIn("B", self.res["fechadas"])
        self.assertNotIn("X", self.res["ids_vistos"])

    def test_preciso_de_voce_real_e_da_parte(self):
        self.assertEqual([(x["parte"]) for x in self.res["precisa"]], ["G1"])

    def test_preciso_de_voce_em_regra_de_goal_e_ignorado(self):
        texto = "- Stop when: done OR you wrote PRECISO DE VOCÊ: OR 40 turns.\n"
        self.assertEqual(leitor.analisar_progress(texto, ["A"], NOMES)["precisa"], [])

    def test_marcador_como_titulo_pega_o_corpo(self):
        texto = "## Parte A\n\n### PRECISO DE VOCÊ:\n\n1. Aplicar a migration.\n2. Ligar a chave.\n"
        r = leitor.analisar_progress(texto, ["A"], NOMES)
        self.assertEqual(len(r["precisa"]), 1)
        self.assertIn("Aplicar a migration", r["precisa"][0]["texto"])

    def test_marcador_sem_parte_superado_por_fechamento_posterior(self):
        texto = "PRECISO DE VOCÊ: rodar o SQL.\n\n## Parte A fechada (hoje)\n"
        self.assertEqual(leitor.analisar_progress(texto, ["A"], NOMES)["precisa"], [])

    def test_perguntas_abertas_sem_as_respondidas(self):
        self.assertEqual([q["texto"] for q in self.res["perguntas"]], ["Q1: qual remetente usar?"])

    def test_achados_por_volta(self):
        a1 = self.res["itens"]["A.1"]
        voltas = {k: v["alto"] for k, v in a1["voltas"].items()}
        self.assertEqual(voltas, {0: 1, 2: 0})
        a2 = self.res["itens"]["A.2"]
        self.assertEqual([(v["volta"], v["alto"]) for _k, v in sorted(a2["voltas"].items())],
                         [(1, 2), (2, 1), (3, 0)])

    def test_rotulo_de_achado_nao_vira_contagem(self):
        self.assertEqual(self.res["itens"]["A.3"]["voltas"], {})

    def test_item_vai_para_a_parte_certa(self):
        self.assertEqual(self.res["itens"]["G1.0"]["parte"], "G1")
        self.assertEqual(leitor.parte_do_item("D2b", ["D"]), "D")
        self.assertEqual(leitor.parte_do_item("G1.0", ["G", "G1"]), "G1")

    def test_bullet_fechada_em_maiusculas(self):
        r = leitor.analisar_progress("- **B — FECHADA 02/01; PR #7 MERGEADA.** texto\n", ["B"], NOMES)
        self.assertIn("B", r["fechadas"])
        self.assertEqual(r["prs_citadas"]["B"], [7])

    def test_parte_fechada_como_condicao_nao_conta(self):
        # Mesma forma de uma linha real: a Parte é pré-condição, não foi fechada.
        for frase in ("- Apagar conta real só com a Parte B-extra fechada; o script segue valendo até lá.\n",
                      "- Apagar conta só com a Parte B fechada.\n",
                      "Ligar a flag depois da Parte B fechada.\n",
                      "Esperar até a Parte B fechada.\n",
                      "Rodar quando Parte B fechada.\n"):
            r = leitor.analisar_progress(frase, ["B", "B-extra"], NOMES)
            self.assertEqual(r["fechadas"], {}, frase)

    def test_parte_fechada_em_formas_validas(self):
        casos = {"## Parte B fechada (01/01/2030)\n": "B",
                 "- **Parte B fechada (01/01).** texto\n": "B",
                 "04/11 — Parte B fechada\n": "B",
                 "2. Parte B fechada em 14/10.\n": "B",
                 "- 26/10/2030: **Parte B fechada (26/10/2030)**\n": "B",
                 "- Plano revisado, 0 ALTO em aberto. Parte B fechada em 09/11.\n": "B",
                 "Parte J — 1ª leva: Parte B fechada na 1ª leva\n": "B",
                 "- migrations aplicadas; Parte B-extra fechada em 30/10\n": "B-extra"}
        for frase, pid in casos.items():
            r = leitor.analisar_progress(frase, ["B", "B-extra"], NOMES)
            self.assertEqual(list(r["fechadas"]), [pid], frase)

    def test_achados_em_tabela_por_item(self):
        texto = ("## Parte A\n\n| Item | Executor | CRÍTICO/ALTO por volta | Resultado |\n|---|---|---|---|\n"
                 "| A1a | executor (13) | ALTO 1→0 (falhas: corrigido) | ok |\n"
                 "| A2 tela | executor (7) | 0 | ok |\n"
                 "| J1a-1 estado | executor (15) | ALTO 2→1→0 | ok |\n")
        r = leitor.analisar_progress(texto, ["A", "J"], NOMES)
        self.assertEqual([(v["volta"], v["alto"]) for _k, v in sorted(r["itens"]["A1a"]["voltas"].items())],
                         [(1, 1), (2, 0)])
        self.assertEqual(r["itens"]["A2"]["voltas"], {})
        self.assertEqual(r["itens"]["J1a-1"]["parte"], "A")  # seção manda
        self.assertEqual(len(r["itens"]["J1a-1"]["voltas"]), 3)

    def test_tabela_sem_coluna_de_alto_e_ignorada(self):
        texto = "| Item | Resultado |\n|---|---|\n| A1 | ALTO 1 citado à toa |\n"
        self.assertEqual(leitor.analisar_progress(texto, ["A"], NOMES)["itens"], {})

    def test_achados_em_sub_bullet_sem_negrito(self):
        texto = ("## Parte D\n- Por item:\n"
                 "  - D2a — executor · ~30 · falhas ALTO 1→0 (timeout) · segurança 0.\n"
                 "  - D2b — executor · falhas ALTO 2→1→0 em 3 voltas.\n")
        r = leitor.analisar_progress(texto, ["D"], NOMES)
        self.assertEqual(len(r["itens"]["D2a"]["voltas"]), 2)
        self.assertEqual(r["itens"]["D2b"]["voltas"][1]["alto"], 2)

    def test_numero_antes_e_paragrafo_de_revisao(self):
        texto = ("## Parte F fechada\n\n**Revisão:** F2: falhas 2 ALTO (cache caído) → fechados na volta 2. "
                 "F1a: banco 0 ALTO; falhas 1 ALTO (beat) → fechado.\n\n## Parte C fechada\n\n"
                 "**Revisão:** C4 e C5 sem CRÍTICO/ALTO introduzido. C1a: ALTO preço vazando entre planos; fechado.\n")
        r = leitor.analisar_progress(texto, ["C", "F"], NOMES)
        self.assertEqual(r["itens"]["F2"]["voltas"], {0: {"volta": None, "critico": 0, "alto": 2}})
        self.assertEqual(r["itens"]["F1a"]["voltas"][0]["alto"], 1)
        self.assertEqual(r["itens"]["C1a"]["voltas"][0]["alto"], 1)
        self.assertEqual(r["itens"]["C1a"]["parte"], "C")
        self.assertNotIn("C4", r["itens"])

    def test_texto_vazio_nao_quebra(self):
        r = leitor.analisar_progress(None, [], NOMES)
        self.assertEqual(r["fechadas"], {})


class TestDepois(unittest.TestCase):
    def test_conta_caixas_abertas(self):
        self.assertEqual(leitor.contar_depois("- [ ] um\n- [x] dois\n  - [ ] tres\n"), (2, "caixas"))

    def test_sem_caixas_vira_null(self):
        self.assertEqual(leitor.contar_depois("- achado sem caixa\n| a | b |\n"), (None, "sem_caixas"))
        self.assertEqual(leitor.contar_depois(None), (None, "sem_arquivo"))


class TestCasamentos(unittest.TestCase):
    def test_branch_para_parte(self):
        ids = ["A", "A-mfa", "J", "G1", "G"]
        self.assertEqual(leitor.parte_da_branch("feat/fase-900-parte-a", "900", ids), "A")
        self.assertEqual(leitor.parte_da_branch("feat/fase-900-a-mfa", "900", ids), "A-mfa")
        self.assertEqual(leitor.parte_da_branch("feat/fase-900-j2", "900", ids), "J")
        self.assertEqual(leitor.parte_da_branch("feat/fase-900-parte-g1", "900", ids), "G1")
        self.assertIsNone(leitor.parte_da_branch("feat/fase-901-parte-a", "900", ids))

    def test_sessao_para_parte(self):
        self.assertEqual(leitor.parte_da_sessao("Fase 900 Parte G1", "900", ["G", "G1"]), "G1")
        self.assertIsNone(leitor.parte_da_sessao("Grupo de onboarding", "900", ["A"]))


class TestFaseNoDisco(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.mkdtemp()
        pasta = os.path.join(self.tmp, "phases", "900-teste")
        os.makedirs(pasta)
        os.makedirs(os.path.join(self.tmp, "phases", "899-antiga"))
        for nome, texto in (("GOAL.md", GOAL), ("PROGRESS.md", PROGRESS), ("DEPOIS.md", "- [ ] a\n- [ ] b\n")):
            with open(os.path.join(pasta, nome), "w", encoding="utf-8") as f:
                f.write(texto)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def test_estado_completo(self):
        prs = [{"numero": 31, "titulo": "x", "estado": "OPEN", "branch": "feat/fase-900-parte-b",
                "url": "https://github.com/o/r/pull/31", "atualizada": "2030-01-01"}]
        sessoes = [{"nome": "Fase 900 Parte B-extra", "estado": "running", "ativa": True, "rodando": True}]
        avisos = []
        f = leitor.ler_fase(os.path.join(self.tmp, "phases", "900-teste"), NOMES, prs, sessoes, avisos)
        st = {p["id"]: p["status"] for p in f["partes"]}
        self.assertEqual(st, {"A": "fechada", "B": "rodando", "B-extra": "rodando", "G1": "precisa_de_voce"})
        por_id = {p["id"]: p for p in f["partes"]}
        self.assertIn("PR #31", por_id["B"]["origem"])
        self.assertIn("sessão", por_id["B-extra"]["origem"])
        self.assertEqual(por_id["A"]["pr"]["numero"], 12)
        self.assertEqual(por_id["G1"]["comando_copiar"], 'claude --bg "/tune-up:part 900 G1"')
        self.assertEqual(f["depois_abertos"], 2)
        self.assertFalse(f["completa"])

    def test_aviso_quando_ha_alto_sem_item(self):
        texto = PROGRESS + "\n- Revisão por item: 1.5 executor, ALTO 1→0 em 2 voltas.\n"
        texto = texto.replace("`ALTO 1`", "`ALTO 0`").replace("ALTO 2→1→0", "ALTO 0")
        with open(os.path.join(self.tmp, "phases", "900-teste", "PROGRESS.md"), "w", encoding="utf-8") as f:
            f.write(texto)
        avisos = []
        leitor.ler_fase(os.path.join(self.tmp, "phases", "900-teste"), NOMES, [], [], avisos)
        self.assertTrue(any("nenhum item saiu com achado" in a for a in avisos), avisos)

    def test_sem_aviso_quando_item_tem_achado(self):
        avisos = []
        leitor.ler_fase(os.path.join(self.tmp, "phases", "900-teste"), NOMES, [], [], avisos)
        self.assertFalse(any("nenhum item saiu com achado" in a for a in avisos), avisos)

    def test_montar_estado_sem_comandos_externos(self):
        e = leitor.montar_estado(plans_cli=self.tmp, rodar_externos=False)
        self.assertEqual(e["resumo"]["fases_total"], 2)
        self.assertEqual(e["resumo"]["fases_acompanhadas"], 1)
        self.assertEqual(e["resumo"]["partes_total"], 4)
        self.assertEqual(e["resumo"]["partes_fechadas"], 1)
        self.assertEqual(e["fases"][0]["numero"], "900")  # mais nova primeiro
        self.assertTrue(any("sem PROGRESS.md" in a for a in e["avisos"]))

    def test_pasta_inexistente_vira_aviso(self):
        e = leitor.montar_estado(plans_cli=os.path.join(self.tmp, "nao-existe"), rodar_externos=False)
        self.assertEqual(e["fases"], [])
        self.assertTrue(any("não consegui listar" in a for a in e["avisos"]))


class TestPainel(unittest.TestCase):
    def test_host(self):
        self.assertTrue(painel.host_permitido("127.0.0.1:8787"))
        self.assertTrue(painel.host_permitido("localhost"))
        self.assertFalse(painel.host_permitido("evil.example:8787"))
        self.assertFalse(painel.host_permitido("127.0.0.1.evil.example"))
        self.assertFalse(painel.host_permitido(None))

    def test_cache_respeita_validade(self):
        agora = [0.0]
        c = leitor.Cache(relogio=lambda: agora[0])
        chamadas = []
        f = lambda: chamadas.append(1) or len(chamadas)  # noqa: E731
        self.assertEqual(c.pegar("k", 10, f), 1)
        agora[0] = 5
        self.assertEqual(c.pegar("k", 10, f), 1)
        agora[0] = 11
        self.assertEqual(c.pegar("k", 10, f), 2)


if __name__ == "__main__":
    unittest.main()
