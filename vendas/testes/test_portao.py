"""Portão: um teste por célula da tabela origem x regra (opt-out, pausa humana, janela, teto/ritmo, dedupe).
Toda negação confere a linha 'negado' com o motivo e o conector falso com 0 chamadas."""
import sys

sys.dont_write_bytecode = True

import datetime  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402
from unittest import mock  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from servico import banco, pasta, portao  # noqa: E402
from servico.conectores.falso import ConectorFalso  # noqa: E402

UTC = datetime.timezone.utc
AGORA = datetime.datetime(2026, 11, 10, 15, 0, tzinfo=UTC)   # 12:00 no fuso -03:00
FORA = datetime.datetime(2026, 11, 10, 23, 0, tzinfo=UTC)    # 20:00 no fuso -03:00
CLIENTE = "+55 11 90000-0001"
OUTRO = "+55 11 90000-0002"
DONO = "+55 11 90000-0009"
INST = "loja"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        os.makedirs(os.path.join(self.tmp, "projeto"))
        self.pasta = pasta.pasta_de_dados(os.path.join(self.tmp, "projeto"), base=os.path.join(self.tmp, "dados"))
        self.con = banco.abrir(self.pasta)
        self.addCleanup(self.con.close)
        banco.gravar_config(self.con, "fuso", "-03:00")
        banco.gravar_config(self.con, "numero_dono", DONO)
        self.c = ConectorFalso()
        self.n = 0

    def numero(self, origem):
        return DONO if origem == "teste_audio" else CLIENTE

    def mandar(self, origem, numero=None, chave="k1", agora=AGORA, confirmar=False):
        numero = numero or self.numero(origem)
        a = (self.con, self.c, INST, numero)
        if origem == "manual":
            return portao.enviar_manual(*a, "oi", chave, confirmar, agora=agora)
        if origem == "rascunho_aprovado":
            return portao.enviar_rascunho_aprovado(*a, "oi", chave, agora=agora)
        if origem == "ia":
            return portao.enviar_ia(*a, "oi", 1, chave, 1, agora=agora)
        if origem == "campanha":
            return portao.enviar_campanha(*a, "oi", chave, 0, agora=agora)
        if origem == "audio_ia":
            return portao.enviar_audio_ia(*a, "a.ogg", 1, chave, 1, agora=agora)
        if origem == "teste_audio":
            return portao.enviar_teste_audio(*a, "a.ogg", chave, agora=agora)
        return portao.enviar_confirmacao_sair(*a, "Pronto, você não recebe mais mensagens.", agora=agora)

    def encher(self, n, quando, origem="manual", numero=None):
        """n envios já feitos (estado enviado) no instante dado."""
        contato = banco.salvar_contato(self.con, numero) if numero else None
        for _ in range(n):
            self.n += 1
            banco.registrar_envio(self.con, "pre:%d" % self.n, origem, estado="enviado", contato_id=contato,
                                  quando=portao._iso(quando))

    def linha(self, envio_id):
        return self.con.execute("SELECT * FROM envios WHERE id = ?", (envio_id,)).fetchone()

    def enviado(self, r, chamadas=1):
        self.assertEqual(r["estado"], "enviado", r)
        self.assertEqual(self.c.envios(), chamadas)
        self.assertEqual(self.linha(r["envio_id"])["estado"], "enviado")
        self.assertTrue(self.linha(r["envio_id"])["id_externo"])

    def negado(self, r, motivo, chamadas=0):
        self.assertEqual((r["estado"], r["motivo"]), ("negado", motivo), r)
        self.assertEqual(self.c.envios(), chamadas)
        linha = self.linha(r["envio_id"])
        self.assertEqual((linha["estado"], linha["motivo"]), ("negado", motivo))


CELULAS = {
    "optout": {"manual": "optout_pede_confirmacao", "rascunho_aprovado": "optout", "ia": "optout",
               "campanha": "optout", "audio_ia": "optout", "teste_audio": None, "confirmacao_sair": None},
    "pausa": {"manual": None, "rascunho_aprovado": None, "ia": "pausa_humana", "campanha": "pausa_humana",
              "audio_ia": "pausa_humana", "teste_audio": None, "confirmacao_sair": None},
    "janela": {"manual": None, "rascunho_aprovado": None, "ia": None, "campanha": "fora_da_janela",
               "audio_ia": None, "teste_audio": None, "confirmacao_sair": None},
}


class TesteTabela(Base):
    def preparar(self, regra, origem):
        numero = self.numero(origem)
        if origem == "confirmacao_sair" or regra == "optout":
            banco.marcar_optout(self.con, numero)
        if regra == "pausa":
            conversa = banco.abrir_conversa(self.con, banco.salvar_contato(self.con, numero))
            self.con.execute("UPDATE conversas SET modo = 'humano' WHERE id = ?", (conversa,))
        return FORA if regra == "janela" else AGORA


def _celula(regra, origem, esperado):
    def teste(self):
        r = self.mandar(origem, agora=self.preparar(regra, origem))
        if esperado is None:
            self.enviado(r)
        else:
            self.negado(r, esperado)
    return teste


def _dedupe(origem):
    def teste(self):
        self.preparar("dedupe", origem)
        self.enviado(self.mandar(origem))
        r = self.mandar(origem)
        self.assertEqual(r["estado"], "duplicado")
        self.assertEqual(self.c.envios(), 1)
        ativos = self.con.execute("SELECT COUNT(*) FROM envios WHERE estado <> 'negado'").fetchone()[0]
        self.assertEqual(ativos, 1)
    return teste


for _regra, _linha in CELULAS.items():
    for _origem, _esperado in _linha.items():
        setattr(TesteTabela, "test_%s__%s" % (_origem, _regra), _celula(_regra, _origem, _esperado))
for _origem in portao.ORIGENS:
    setattr(TesteTabela, "test_%s__dedupe" % _origem, _dedupe(_origem))


class TesteTetos(Base):
    """Coluna teto/ritmo, uma célula por origem."""
    DEPOIS = AGORA + datetime.timedelta(minutes=2)

    def test_manual__teto(self):
        self.encher(200, AGORA - datetime.timedelta(minutes=30), numero=OUTRO)
        self.enviado(self.mandar("manual", chave="a"))            # 200/h não vale para manual
        self.encher(8, AGORA - datetime.timedelta(seconds=10))
        self.negado(self.mandar("manual", chave="b"), "teto_minuto", chamadas=1)

    def test_rascunho_aprovado__teto(self):
        self.encher(200, AGORA - datetime.timedelta(minutes=30))
        self.enviado(self.mandar("rascunho_aprovado", chave="a"))
        self.encher(8, AGORA - datetime.timedelta(seconds=10))
        self.negado(self.mandar("rascunho_aprovado", chave="b"), "teto_minuto", chamadas=1)

    def _minuto_e_hora(self, origem):
        self.encher(8, AGORA - datetime.timedelta(seconds=10))
        self.negado(self.mandar(origem, chave="a"), "teto_minuto")
        self.encher(192, AGORA - datetime.timedelta(minutes=30))   # 200 na última hora, 0 no último minuto
        self.negado(self.mandar(origem, chave="b", agora=self.DEPOIS), "teto_hora")

    def test_ia__teto(self):
        self._minuto_e_hora("ia")

    def test_campanha__teto(self):
        self._minuto_e_hora("campanha")

    def test_campanha__teto_contatos_novos_hook(self):
        antigo = "+55 11 90000-0003"
        self.encher(1, AGORA - datetime.timedelta(days=3), numero=antigo)   # já recebeu antes: não é novo
        self.encher(1, AGORA - datetime.timedelta(hours=1), numero=OUTRO)    # 1 contato novo hoje
        inicio = portao._iso(datetime.datetime(2026, 11, 10, 3, 0, tzinfo=UTC))  # 00:00 no fuso -03:00
        self.assertEqual(portao.contatos_novos_no_dia(self.con, inicio), 1)
        with mock.patch.object(portao, "teto_contatos_novos", return_value=1):
            self.negado(self.mandar("campanha", chave="a"), "teto_contatos_novos_dia")
            self.enviado(self.mandar("campanha", numero=antigo, chave="a"))
        self.enviado(self.mandar("campanha", chave="b"), chamadas=2)        # gancho padrão: dia 1 = 5 novos
        self.assertEqual(portao.contatos_novos_no_dia(self.con, inicio), 2)

    def test_audio_ia__teto(self):
        self._minuto_e_hora("audio_ia")

    def test_audio_ia__teto_de_audio_por_dia(self):
        banco.gravar_config(self.con, "teto_audio_dia", "2")
        self.encher(2, AGORA - datetime.timedelta(hours=2), origem="audio_ia")
        self.negado(self.mandar("audio_ia"), "teto_audio_dia")
        self.encher(5, AGORA - datetime.timedelta(days=1), origem="ia")
        self.enviado(self.mandar("ia"))   # o teto de áudio não vale para texto

    def test_teste_audio__teto(self):
        self.encher(8, AGORA - datetime.timedelta(seconds=10))
        self.enviado(self.mandar("teste_audio", chave="a"))   # 8/min não vale; 5/dia vale
        self.encher(4, AGORA - datetime.timedelta(hours=3), origem="teste_audio")
        self.negado(self.mandar("teste_audio", chave="b"), "teto_teste_audio_dia", chamadas=1)
        amanha = AGORA + datetime.timedelta(days=1)
        self.enviado(self.mandar("teste_audio", chave="c", agora=amanha), chamadas=2)

    def test_confirmacao_sair__teto(self):
        banco.marcar_optout(self.con, CLIENTE)
        self.encher(8, AGORA - datetime.timedelta(seconds=10))
        self.enviado(self.mandar("confirmacao_sair"))   # 8/min não vale
        self.assertEqual(self.mandar("confirmacao_sair")["estado"], "duplicado")   # 1 por contato
        self.assertEqual(self.c.envios(), 1)


class TesteRegrasExtras(Base):
    def test_manual_para_optout_com_confirmacao_vai_e_negado_nao_ocupa_a_chave(self):
        banco.marcar_optout(self.con, CLIENTE)
        self.negado(self.mandar("manual", chave="x"), "optout_pede_confirmacao")
        self.negado(self.mandar("manual", chave="x", confirmar="sim"), "optout_pede_confirmacao")
        self.enviado(self.mandar("manual", chave="x", confirmar=True))

    def test_confirmacao_sair_sem_optout_negada(self):
        self.negado(self.mandar("confirmacao_sair"), "sem_optout")

    def test_teste_audio_so_para_o_dono(self):
        self.negado(self.mandar("teste_audio", numero=CLIENTE), "nao_e_o_dono")
        self.con.execute("DELETE FROM config WHERE chave = 'numero_dono'")
        self.negado(self.mandar("teste_audio", chave="k2"), "sem_numero_do_dono")
        banco.gravar_config(self.con, "numero_dono", "+55 11 8000-0009")   # sem o 9º dígito
        self.enviado(self.mandar("teste_audio", numero="5511980000009", chave="k3"))
        self.assertIsNone(banco.buscar_contato(self.con, DONO))   # o dono não vira contato

    def test_pausa_por_tempo(self):
        conversa = banco.abrir_conversa(self.con, banco.salvar_contato(self.con, CLIENTE))
        ate = portao._iso(AGORA + datetime.timedelta(minutes=15))
        self.con.execute("UPDATE conversas SET pausada_ate = ? WHERE id = ?", (ate, conversa))
        self.negado(self.mandar("ia"), "pausa_humana")
        self.enviado(self.mandar("ia", chave="k2", agora=AGORA + datetime.timedelta(minutes=16)))

    def test_bordas_da_janela(self):
        local = datetime.timezone(datetime.timedelta(hours=-3))
        for hora, minuto, ok in ((8, 59, False), (9, 0, True), (18, 59, True), (19, 0, False)):
            with self.subTest(hora=hora, minuto=minuto):
                agora = datetime.datetime(2026, 11, 10, hora, minuto, tzinfo=local)
                r = self.mandar("campanha", chave="%d%d" % (hora, minuto), agora=agora)
                self.assertEqual(r["estado"], "enviado" if ok else "negado", r)

    def test_fuso_invalido_fecha(self):
        banco.gravar_config(self.con, "fuso", "Marte/Base")
        self.negado(self.mandar("campanha"), "fuso_invalido")
        self.enviado(self.mandar("manual"))   # manual não depende de fuso

    def test_fuso_iana(self):
        try:
            from zoneinfo import ZoneInfo
            ZoneInfo("America/Sao_Paulo")
        except Exception:
            self.skipTest("sem base de fusos IANA nesta máquina (Windows sem tzdata)")
        banco.gravar_config(self.con, "fuso", "America/Sao_Paulo")
        self.negado(self.mandar("campanha", agora=FORA), "fora_da_janela")
        self.enviado(self.mandar("campanha", chave="k2"))

    def test_origem_desconhecida_e_telefone_invalido(self):
        with self.assertRaises(ValueError):
            portao.pode_enviar(self.con, "spam", CLIENTE)
        with self.assertRaises(ValueError):
            self.mandar("manual", numero="123")
        self.assertEqual(self.c.envios(), 0)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM envios").fetchone()[0], 0)


if __name__ == "__main__":
    unittest.main()
