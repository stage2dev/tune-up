"""Rotas /voz pelo serviço de verdade (token obrigatório): a chave da ElevenLabs não aparece em resposta de rota,
linha de log nem arquivo da raiz do projeto; fica num arquivo 0600 da pasta de dados. O número do teste de áudio
nunca vem do corpo do pedido. Consentimento liga a voz clonada."""
import sys

sys.dont_write_bytecode = True

import contextlib  # noqa: E402
import io  # noqa: E402
import json  # noqa: E402
import os  # noqa: E402
import stat  # noqa: E402
import unittest  # noqa: E402
from unittest import mock  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from servico import banco, rotas, voz, voz_cliente  # noqa: E402
from servico.conectores.falso import ConectorFalso  # noqa: E402
from testes.elevenlabs_falsa import ElevenLabsFalsa  # noqa: E402
from testes.test_voz import CHAVE, DONO, OUTRO, SEM_FFMPEG  # noqa: E402
from testes.test_webhook_modo import Base  # noqa: E402


class TesteRotasVoz(Base):
    def setUp(self):
        super().setUp()
        self.falsa = ElevenLabsFalsa()
        self.addCleanup(self.falsa.fechar)
        self.falsa.vozes = (200, {"voices": [{"voice_id": "VozCatalogo0001", "name": "Ana", "category": "premade"}]})
        self.app.elevenlabs_url = self.falsa.url
        self.app.conector = ConectorFalso()
        con = banco.abrir(self.pasta)
        try:
            banco.gravar_config(con, "instancia", "loja")
            banco.gravar_config(con, "numero_dono", DONO)
        finally:
            con.close()
        p = mock.patch.object(voz_cliente, "achar_ffmpeg", return_value=SEM_FFMPEG)
        p.start()
        self.addCleanup(p.stop)
        self.respostas = []

    def rota(self, metodo, caminho, corpo=None):
        codigo, bruto = self.pedir(metodo, caminho, {rotas.CAB_TOKEN: self.token}, corpo)
        self.respostas.append(bruto)
        return codigo, json.loads(bruto)

    def test_chave_nunca_sai_e_fica_0600_fora_do_projeto(self):
        log = io.StringIO()
        with contextlib.redirect_stderr(log), contextlib.redirect_stdout(log):
            codigo, r = self.rota("POST", "/voz/chave", {"chave": CHAVE})
            self.assertEqual((codigo, r["chave"]), (200, {"configurada": True, "final": CHAVE[-4:]}))
            self.assertEqual(self.rota("POST", "/voz/config", {"voz_id": "VozCatalogo0001", "clonada": False})[0], 200)
            codigo, est = self.rota("GET", "/voz")
            self.assertEqual(codigo, 200)
            self.assertTrue(est["ligada"], est["avisos"])
            self.falsa.fila.append((401, {"detail": {"status": "invalid_api_key", "message": CHAVE}}))
            codigo, r = self.rota("POST", "/voz/teste", {"id_tela": "tela-0000001"})
            self.assertEqual((codigo, r["estado"]), (502, "erro"))
            self.assertEqual(self.pedir("GET", "/voz")[0], 403, "rota sem token")
        for bruto in self.respostas + [log.getvalue()]:
            self.assertNotIn(CHAVE, bruto)
        arquivo = os.path.join(self.pasta, voz.ARQUIVO_CHAVE)
        if os.name != "nt":
            self.assertEqual(stat.S_IMODE(os.stat(arquivo).st_mode), 0o600)
        for raiz, _, nomes in os.walk(self.projeto):
            for nome in nomes:
                with open(os.path.join(raiz, nome), "rb") as f:
                    self.assertNotIn(CHAVE.encode(), f.read(), nome)
        self.assertEqual(self.app.conector.envios(), 0)

    def test_numero_do_corpo_e_ignorado_no_teste_de_audio(self):
        self.rota("POST", "/voz/chave", {"chave": CHAVE})
        self.rota("POST", "/voz/config", {"voz_id": "VozCatalogo0001"})
        codigo, r = self.rota("POST", "/voz/teste", {"id_tela": "tela-0000002", "numero": OUTRO, "texto": "Oi."})
        self.assertEqual(r.get("motivo"), None, r)   # o portão não negou: o número usado foi o do dono
        self.assertEqual(len(self.falsa.pedidos), 1)  # chegou à ElevenLabs; a conversão (ffmpeg falso) falhou
        self.assertEqual(r["estado"], "erro")

    def test_consentimento_liga_a_voz_clonada(self):
        self.rota("POST", "/voz/chave", {"chave": CHAVE})
        self.rota("POST", "/voz/config", {"voz_id": "VozClonada0001", "clonada": True})
        est = self.rota("GET", "/voz")[1]
        self.assertFalse(est["ligada"])
        self.assertEqual(est["aviso_ia"], voz.AVISO_IA)
        codigo, _ = self.rota("POST", "/voz/consentimento", {"nome": "Fulana", "data": "2026-13", "texto": "curto"})
        self.assertEqual(codigo, 400)
        codigo, r = self.rota("POST", "/voz/consentimento", {
            "nome": "Fulana de Teste", "data": "2026-01-02", "texto": "Autorizo o uso da minha voz clonada nas vendas."})
        self.assertEqual((codigo, r["consentimento"]), (200, {"nome": "Fulana de Teste", "data": "2026-01-02"}))
        self.assertTrue(self.rota("GET", "/voz")[1]["ligada"])
        self.rota("POST", "/voz/config", {"voz_id": "VozClonada0002", "clonada": True})
        self.assertFalse(self.rota("GET", "/voz")[1]["ligada"], "consentimento é da voz, não da conta")

    def test_config_invalida_recusada(self):
        self.assertEqual(self.rota("POST", "/voz/config", {"voz_id": "../x"})[0], 400)
        self.assertEqual(self.rota("POST", "/voz/config", {"voz_id": "VozCatalogo0001", "teto_caracteres_dia": -1})[0],
                         400)
        self.assertEqual(self.rota("POST", "/voz/teste", {})[0], 400)


if __name__ == "__main__":
    unittest.main()
