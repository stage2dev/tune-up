"""Endurecimento da revisão da Parte F: o dono reenvia o incerto de campanha ativa (e não o de campanha pausada), o
reenvio que sai marca o contato 'enviado', todo motivo que chega à tela tem texto em pt-BR, campanha_parada com a
campanha ainda ativa deixa evento e aviso, site sem esquema vira https://, tempo esgotado com batimento fresco diz
"ainda processando" e o precos.json usa a troca com nova tentativa. Nada de rede fora de 127.0.0.1."""
import sys

sys.dont_write_bytecode = True

import contextlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import re  # noqa: E402
import shutil  # noqa: E402
import socket  # noqa: E402
import tempfile  # noqa: E402
import types  # noqa: E402
import unittest  # noqa: E402
import urllib.error  # noqa: E402
from importlib import util  # noqa: E402
from unittest import mock  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from servico import campanha, candidatos, conversas, modelo, portao, precos, travas  # noqa: E402
from testes import test_campanha  # noqa: E402
from testes.test_aba_conexao import Aba  # noqa: E402


class TesteReenvioDoDono(test_campanha.Base):
    def _incerto_com_campanha_ativa(self):
        cid = self.campanha(2)   # 2 contatos: o 1º fica incerto e a campanha segue ativa
        self.c.modo_envio = "timeout"
        self.rodar(1)
        self.c.modo_envio = "ok"
        self.assertEqual(self.estados(cid), ["incerto", "pendente"])
        envio = self.con.execute("SELECT id FROM envios WHERE estado = 'incerto'").fetchone()[0]
        return cid, envio

    def _reenviar(self, envio):
        app = types.SimpleNamespace(conector=self.c)
        return conversas._decidir(app, self.con, envio, "reenviar", {})

    def test_dono_reenvia_incerto_de_campanha_ativa_e_o_contato_vira_enviado(self):
        cid, envio = self._incerto_com_campanha_ativa()
        codigo, r = self._reenviar(envio)
        self.assertEqual((codigo, r["estado"], r["motivo"]), (200, "enviado", None))
        self.assertEqual(len(self.c.entregues), 1)
        self.assertEqual(self.estados(cid), ["enviado", "pendente"])   # o progresso não conta mais como incerto

    def test_dono_nao_reenvia_incerto_de_campanha_pausada(self):
        cid, envio = self._incerto_com_campanha_ativa()
        self.assertTrue(campanha.pausar(self.con, cid))
        codigo, r = self._reenviar(envio)
        self.assertEqual((r["estado"], r["motivo"]), ("negado", "campanha_parada"))
        self.assertEqual(self.c.entregues, [])
        self.assertEqual(self.estados(cid), ["incerto", "pendente"])
        estado = self.con.execute("SELECT estado FROM envios WHERE id = ?", (envio,)).fetchone()[0]
        self.assertEqual(estado, "incerto")   # negado no reenvio não muda a linha

    def test_reenvio_de_outro_envio_do_contato_nao_sai(self):
        cid, envio = self._incerto_com_campanha_ativa()
        self.con.execute("UPDATE campanha_contatos SET envio_id = NULL WHERE campanha_id = ?", (cid,))
        r = portao.reenviar(self.con, self.c, test_campanha.INST, envio, agora=self.agora)
        self.assertEqual((r["estado"], r["motivo"]), ("negado", "contato_fora_da_campanha"))
        self.assertEqual(self.c.entregues, [])


class TesteAgendadorAvisa(test_campanha.Base):
    def test_campanha_parada_com_campanha_ativa_deixa_evento_e_aviso(self):
        cid = self.campanha(1)
        negado = {"estado": "negado", "envio_id": None, "motivo": "campanha_parada"}
        erro = io.StringIO()
        with mock.patch.object(portao, "enviar_campanha", return_value=negado), contextlib.redirect_stderr(erro):
            self.ag.passo()
        ev = self.con.execute("SELECT dados FROM eventos WHERE tipo = 'campanha_parada_mas_ativa'").fetchone()
        self.assertIsNotNone(ev)
        self.assertEqual(json.loads(ev[0])["campanha_id"], cid)
        self.assertIn("campanha_parada", erro.getvalue())
        self.assertNotIn("90000", ev[0] + erro.getvalue())

    def test_campanha_pausada_de_verdade_fica_quieta(self):
        cid = self.campanha(1)

        def pausa_no_meio(*_a, **_k):   # o dono pausa entre a escolha e a reserva: o portão nega com razão
            self.assertTrue(campanha.pausar(self.con, cid))
            return {"estado": "negado", "envio_id": None, "motivo": "campanha_parada"}
        erro = io.StringIO()
        with mock.patch.object(portao, "enviar_campanha", pausa_no_meio), contextlib.redirect_stderr(erro):
            self.ag.passo()
        self.assertIsNone(self.con.execute("SELECT 1 FROM eventos WHERE tipo = 'campanha_parada_mas_ativa'")
                          .fetchone())
        self.assertEqual(erro.getvalue(), "")


def _codigos(arquivo, padroes):
    texto = open(os.path.join(os.path.dirname(AQUI), "servico", arquivo), encoding="utf-8").read()
    return {c for p in padroes for c in re.findall(p, texto)}


class TesteMotivosEmPtBr(unittest.TestCase):
    def test_todo_motivo_que_chega_a_tela_tem_texto(self):
        base = os.path.join(os.path.dirname(AQUI), "painel", "modulos", "vendas", "abas")
        abas = {}
        for nome in ("conversas", "disparos"):
            spec = util.spec_from_file_location("aba_" + nome, os.path.join(base, nome + ".py"))
            abas[nome] = util.module_from_spec(spec)
            spec.loader.exec_module(abas[nome])
        gate = _codigos("portao.py", [r'return "([a-z_]+)"', r'return None if ok else "([a-z_]+)"',
                                      r"motivo = '([a-z_]+)'", r'_resultado\([^)]*"([a-z_]+)"\)',
                                      r'_resultado\("negado", envio_id, "([a-z_]+)"\)'])
        cerebro = _codigos("cerebro.py", [r'_parar\(con, conversa_id, r, "([a-z_]+)"', r'return None, "([a-z_]+)"',
                                          r'_parar\(con, conversa_id, r, "[a-z_]+" if [a-z ]+ else "([a-z_]+)"',
                                          r'marcar_precisa_de_voce\(con, conversa_id, "([a-z_]+)"'])
        cerebro |= _codigos("atendente.py", [r'marcar_precisa_de_voce\(con, conversa_id, "([a-z_]+)"'])
        cerebro |= _codigos("audio_ia.py", [r'marcar_precisa_de_voce\(con, conversa_id, "([a-z_]+)"'])
        cerebro |= _codigos("saida.py", [r'return None, "([a-z_]+)"', r'_barrar\(con, conversa_id, "([a-z_]+)"',
                                         r'"motivo": "(gatilho_[a-z_]+)"'])
        cerebro |= _codigos("rascunhos.py", [r'_barrar\(con, conversa_id, "([a-z_]+)"',
                                             r'"motivo": "(gatilho_[a-z_]+)"'])
        cerebro |= {"envio_negado", "envio_parcial"}   # saida.py: tipo[len("ia_"):]
        for codigo in ("campanha_parada", "resposta_cortada", "reescrita_falhou", "contato_fora_da_campanha",
                       "teto_audio_contato_dia", "audio_incerto"):
            self.assertIn(codigo, gate | cerebro, "a varredura do código perdeu %s" % codigo)
        sem_texto = sorted(c for c in gate | cerebro if c not in abas["conversas"].MOTIVOS)
        self.assertEqual(sem_texto, [], "Conversas sem texto pt-BR")
        so_de_outra_origem = {"nao_e_o_dono", "sem_numero_do_dono", "teto_teste_audio_dia", "teto_audio_dia",
                              "teto_audio_contato_dia",
                              "sem_optout", "optout_pede_confirmacao"}   # teste de áudio, IA em áudio, manual, sair
        campanhas = (gate - so_de_outra_origem) | set(modelo.DA_CAMPANHA) | _codigos(
            "modelo.py", [r'(?m)return None, "([a-z_]+)"$']) | {
            "sem_nome", "sem_origem", "pausada_pelo_dono", "sem_numero_descartavel"}
        sem_texto = sorted(c for c in campanhas if c not in abas["disparos"].MOTIVOS)
        self.assertEqual(sem_texto, [], "Disparos sem texto pt-BR")
        for prefixado in ("nao_enviado:500", "incerto:timeout", "erro_inesperado:KeyError", "sem_id_externo"):
            self.assertNotEqual(abas["disparos"].motivo_texto(prefixado), prefixado)


class TesteSiteSemEsquema(unittest.TestCase):
    def test_www_vira_https_e_o_resto_segue_recusado(self):
        ok = candidatos.validar_linha({"nome": "Loja", "site": "www.empresa.com"})
        self.assertEqual(ok["site"], "https://www.empresa.com")
        ok = candidatos.validar_linha({"nome": "Loja", "site": "empresa.com.br/contato"})
        self.assertEqual(ok["site"], "https://empresa.com.br/contato")
        self.assertEqual(candidatos.chave_do_site(ok["site"]), "empresa.com.br/contato")
        for ruim in ("javascript:alert(1)", "ftp://empresa.com", "mailto:a@empresa.com", "empresa"):
            with self.assertRaises(ValueError, msg=ruim):
                candidatos.validar_linha({"nome": "Loja", "site": ruim})
        with self.assertRaises(ValueError):   # só o site ganha esquema; a fonte segue exigindo http(s)
            candidatos.validar_linha({"nome": "Loja", "url_da_fonte": "www.empresa.com"})


class TesteTempoEsgotado(Aba):
    def _chamar_com(self, erro):
        cliente = self.mod.cliente
        original = cliente.pedir

        def pedir(metodo, url, cab, corpo=None, tempo=None):
            if url.endswith("/saude") or url.endswith("/token-de-envio"):
                return original(metodo, url, cab, corpo, tempo)
            raise erro
        with mock.patch.object(cliente, "pedir", pedir):
            with self.assertRaises(cliente.Recusa) as ctx:
                cliente.chamar(self.ctx, "POST", "/conversas/1/modo", {"modo": "humano"}, base=self.base)
        return str(ctx.exception)

    def test_tempo_esgotado_com_batimento_fresco_diz_ainda_processando(self):
        for erro in (socket.timeout("timed out"), urllib.error.URLError(socket.timeout("timed out"))):
            texto = self._chamar_com(erro)
            self.assertIn("ainda está processando", texto)
            self.assertIn("Atualize a tela", texto)

    def test_conexao_recusada_continua_sem_resposta(self):
        self.assertEqual(self._chamar_com(ConnectionRefusedError()), self.mod.cliente.SEM_RESPOSTA)


class TestePrecosNoWindows(unittest.TestCase):
    def test_gravar_preco_tenta_de_novo_no_windows(self):
        pasta = tempfile.mkdtemp()
        self.addCleanup(shutil.rmtree, pasta, True)
        chamadas, real = [], os.replace

        def falha_uma(origem, destino):
            chamadas.append(1)
            if len(chamadas) < 2:
                raise PermissionError("em uso")
            real(origem, destino)
        with mock.patch.object(os, "replace", falha_uma), mock.patch.object(travas.time, "sleep"), \
                mock.patch.object(travas.os, "name", "nt"):
            precos.gravar_preco(pasta, "modelo-x", 0.15, 0.6)
        self.assertEqual(len(chamadas), 2)
        self.assertEqual(precos.preco(precos.tabela(pasta), "modelo-x"), [0.15, 0.6])
        self.assertEqual([n for n in os.listdir(pasta) if n.endswith(".tmp")], [])


if __name__ == "__main__":
    unittest.main()
