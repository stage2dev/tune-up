"""Voz (F1): ElevenLabs falsa em 127.0.0.1 + ffmpeg real quando existe. Teto de caracteres antes da chamada, voz
desligada sem ffmpeg/chave, voz clonada só com consentimento e com o aviso falado primeiro, teste de áudio só para o
dono, temporários apagados no sucesso e na falha, envio pelo portão."""
import sys

sys.dont_write_bytecode = True

import os  # noqa: E402
import shutil  # noqa: E402
import subprocess  # noqa: E402
import tempfile  # noqa: E402
import types  # noqa: E402
import unittest  # noqa: E402
from unittest import mock  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from servico import banco, chave, pasta, voz, voz_cliente  # noqa: E402
from servico.conectores.falso import ConectorFalso  # noqa: E402
from testes.elevenlabs_falsa import ElevenLabsFalsa, mp3_de_teste  # noqa: E402

FFMPEG = shutil.which("ffmpeg")
CHAVE = "sk_" + "a1b2c3d4e5f6a7b8c9d0" + "e1f2a3b4c5d6WXYZ"
DONO = "5511900000001"
OUTRO = "5511900000002"
VOZ = "VozCatalogo0001"
SEM_FFMPEG = os.path.join(tempfile.gettempdir(), "nao-existe-ffmpeg-vendas")


def ogg_opus(bruto):
    """(é Ogg, canais, taxa de entrada) lidos do cabeçalho OpusHead."""
    i = bruto.find(b"OpusHead")
    if not bruto.startswith(b"OggS") or i < 0:
        return False, None, None
    return True, bruto[i + 9], int.from_bytes(bruto[i + 12:i + 16], "little")


class BaseVoz(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.projeto = os.path.join(self.tmp, "projeto")
        os.makedirs(self.projeto)
        self.pasta = pasta.pasta_de_dados(self.projeto, base=os.path.join(self.tmp, "dados"))
        self.falsa = ElevenLabsFalsa()
        self.addCleanup(self.falsa.fechar)
        self.conector = ConectorFalso()
        self.lidos = []   # bytes do arquivo no instante do envio (depois ele é apagado)
        original = self.conector.enviar_audio

        def enviar_audio(instancia, numero, caminho):
            with open(caminho, "rb") as f:
                self.lidos.append(f.read())
            return original(instancia, numero, caminho)
        self.conector.enviar_audio = enviar_audio
        self.app = types.SimpleNamespace(pasta_dados=self.pasta, elevenlabs_url=self.falsa.url, conector=self.conector)
        self.con = banco.abrir(self.pasta)
        self.addCleanup(self.con.close)
        for k, v in (("instancia", "loja"), ("numero_dono", DONO), ("voz_id", VOZ)):
            banco.gravar_config(self.con, k, v)
        chave.gravar(self.pasta, CHAVE, voz.ARQUIVO_CHAVE)

    def temporarios(self):
        return [n for n in os.listdir(self.pasta) if n.startswith("voz-")]

    def sem_ffmpeg_real(self):
        """ffmpeg 'achado' num caminho que não existe: passa da prontidão e falha na conversão (vale sem ffmpeg)."""
        p = mock.patch.object(voz_cliente, "achar_ffmpeg", return_value=SEM_FFMPEG)
        p.start()
        self.addCleanup(p.stop)

    def assert_nada_saiu(self):
        self.assertEqual(self.conector.envios(), 0)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM envios").fetchone()[0], 0)


@unittest.skipUnless(FFMPEG, "ffmpeg ausente: conversão real não roda aqui")
class TesteConversaoReal(BaseVoz):
    def setUp(self):
        super().setUp()
        self.falsa.padrao = (200, mp3_de_teste(os.path.join(self.tmp, "seno.mp3")))

    def test_converte_mp3_em_ogg_opus_mono_48k(self):
        entrada = os.path.join(self.tmp, "seno.mp3")
        saida = os.path.join(self.tmp, "saida.ogg")
        voz_cliente.converter(FFMPEG, entrada, saida)
        with open(saida, "rb") as f:
            e_ogg, canais, taxa = ogg_opus(f.read())
        self.assertEqual((e_ogg, canais, taxa), (True, 1, 48000))
        ffprobe = shutil.which("ffprobe")
        if ffprobe:
            r = subprocess.run([ffprobe, "-v", "error", "-show_entries", "stream=codec_name,channels,sample_rate",
                                "-of", "default=nw=1", saida], capture_output=True, text=True, timeout=30)
            self.assertIn("codec_name=opus", r.stdout)
            self.assertIn("channels=1", r.stdout)
            self.assertIn("sample_rate=48000", r.stdout)

    def test_teste_de_audio_sai_pelo_portao_como_voz(self):
        r = voz.enviar_teste(self.app, self.con, "tela-0000001", "Oi, teste de voz.")
        self.assertEqual(r["estado"], "enviado", r)
        self.assertEqual(len(self.falsa.pedidos), 1)
        pedido = self.falsa.pedidos[0]
        self.assertEqual(pedido["caminho"], "/v1/text-to-speech/%s?output_format=mp3_44100_128" % VOZ)
        self.assertEqual(pedido["cabecalhos"].get("xi-api-key"), CHAVE)
        self.assertEqual(pedido["corpo"], {"text": "Oi, teste de voz.", "model_id": voz.MODELO_PADRAO})
        self.assertNotIn("teste", pedido["caminho"] + "".join(pedido["cabecalhos"].values()))
        self.assertEqual([c[0] for c in self.conector.chamadas], ["enviar_audio"])
        self.assertEqual(self.conector.chamadas[0][1][1], DONO)
        self.assertEqual(ogg_opus(self.lidos[0]), (True, 1, 48000))
        linha = self.con.execute("SELECT origem, estado, tipo FROM envios").fetchone()
        self.assertEqual(tuple(linha), ("teste_audio", "enviado", "audio"))
        self.assertEqual(self.temporarios(), [], "temporários ficaram depois do sucesso")
        self.assertEqual(voz.usados_hoje(self.con), len("Oi, teste de voz."))

    def test_voz_clonada_com_consentimento_fala_o_aviso_primeiro(self):
        banco.gravar_config(self.con, "voz_clonada", "1")
        self.con.execute("INSERT INTO voz_consentimentos (voz_id, nome, data, texto, criado_em) VALUES "
                         "(?, 'Fulana de Teste', '2026-01-02', 'Autorizo o uso da minha voz clonada.', 'x')", (VOZ,))
        r = voz.enviar_teste(self.app, self.con, "tela-0000002", "Bom dia.")
        self.assertEqual(r["estado"], "enviado", r)
        self.assertEqual(self.falsa.pedidos[0]["corpo"]["text"], voz.AVISO_IA + " Bom dia.")
        self.assertEqual(voz.usados_hoje(self.con), len(voz.AVISO_IA + " Bom dia."))


class TesteRegras(BaseVoz):
    def test_teto_atingido_nao_chama_a_elevenlabs(self):
        self.sem_ffmpeg_real()
        banco.gravar_config(self.con, "voz_teto_caracteres_dia", "10")
        r = voz.enviar_teste(self.app, self.con, "tela-0000003", "Texto com mais de dez letras.")
        self.assertEqual(r["estado"], "teto")
        self.assertEqual(self.falsa.pedidos, [])
        self.assert_nada_saiu()

    def test_reserva_soma_e_para_no_teto(self):
        banco.gravar_config(self.con, "voz_teto_caracteres_dia", "30")
        self.assertIsNotNone(voz.reservar(self.con, 20))
        self.assertIsNone(voz.reservar(self.con, 11))
        self.assertIsNotNone(voz.reservar(self.con, 10))
        self.assertEqual(voz.usados_hoje(self.con), 30)

    def test_sem_ffmpeg_voz_desligada_com_aviso(self):
        with mock.patch.object(voz_cliente.shutil, "which", return_value=None):
            est = voz.estado(self.app, self.con)
            r = voz.enviar_teste(self.app, self.con, "tela-0000004", "Oi.")
        self.assertFalse(est["ligada"])
        self.assertFalse(est["ffmpeg"])
        self.assertTrue(any("ffmpeg" in a for a in est["avisos"]))
        self.assertEqual(r["estado"], "desligada")
        self.assertIn("ffmpeg", r["erro"])
        self.assertEqual(self.falsa.pedidos, [])
        self.assert_nada_saiu()

    def test_sem_chave_voz_desligada(self):
        self.sem_ffmpeg_real()
        chave.apagar(self.pasta, voz.ARQUIVO_CHAVE)
        r = voz.enviar_teste(self.app, self.con, "tela-0000005", "Oi.")
        self.assertEqual(r["estado"], "desligada")
        self.assertIn("ElevenLabs", r["erro"])
        self.assertEqual(self.falsa.pedidos, [])

    def test_voz_clonada_sem_consentimento_recusada(self):
        self.sem_ffmpeg_real()
        banco.gravar_config(self.con, "voz_clonada", "1")
        r = voz.enviar_teste(self.app, self.con, "tela-0000006", "Oi.")
        self.assertEqual(r["estado"], "desligada")
        self.assertIn("consentimento", r["erro"])
        self.assertEqual(self.falsa.pedidos, [])
        self.assert_nada_saiu()

    def test_consentimento_de_outra_voz_nao_vale(self):
        self.sem_ffmpeg_real()
        banco.gravar_config(self.con, "voz_clonada", "1")
        self.con.execute("INSERT INTO voz_consentimentos (voz_id, nome, data, texto, criado_em) VALUES "
                         "('OutraVoz00001', 'Fulana', '2026-01-02', 'Autorizo o uso da minha voz.', 'x')")
        self.assertFalse(voz.estado(self.app, self.con)["ligada"])

    def test_aviso_vai_no_pedido_da_voz_clonada_mesmo_sem_ffmpeg_real(self):
        self.sem_ffmpeg_real()
        banco.gravar_config(self.con, "voz_clonada", "1")
        self.con.execute("INSERT INTO voz_consentimentos (voz_id, nome, data, texto, criado_em) VALUES "
                         "(?, 'Fulana', '2026-01-02', 'Autorizo o uso da minha voz.', 'x')", (VOZ,))
        voz.enviar_teste(self.app, self.con, "tela-0000007", "Oi.")
        self.assertTrue(self.falsa.pedidos[0]["corpo"]["text"].startswith(voz.AVISO_IA))

    def test_teste_de_audio_para_outro_numero_negado_pelo_portao(self):
        self.sem_ffmpeg_real()
        r = voz.enviar_teste(self.app, self.con, "tela-0000008", "Oi.", numero=OUTRO)
        self.assertEqual((r["estado"], r["motivo"]), ("negado", "nao_e_o_dono"))
        self.assertEqual(self.falsa.pedidos, [])
        self.assertEqual(voz.usados_hoje(self.con), 0)
        self.assert_nada_saiu()

    def test_audio_da_ia_respeita_optout_do_portao(self):
        self.sem_ffmpeg_real()
        banco.marcar_optout(self.con, OUTRO)
        r = voz.enviar_audio_ia(self.app, self.con, OUTRO, "Oi.", 1, "msg-1", 1)
        self.assertEqual((r["estado"], r["motivo"]), ("negado", "optout"))
        self.assertEqual(self.falsa.pedidos, [])
        self.assertEqual(self.conector.envios(), 0)

    def test_texto_longo_demais_recusado(self):
        r = voz.enviar_teste(self.app, self.con, "tela-0000009", "a" * (voz.LIMITE_TEXTO + 1))
        self.assertEqual(r["estado"], "erro")
        self.assertEqual(self.falsa.pedidos, [])

    def test_erros_da_elevenlabs_nada_sai_e_reserva_volta(self):
        self.sem_ffmpeg_real()
        casos = [((401, {"detail": {"status": "invalid_api_key", "message": "x"}}), "chave"),
                 ((429, {"detail": {"status": "too_many_concurrent_requests"}}), "429"),
                 ((401, {"detail": {"status": "quota_exceeded", "message": "x"}}), "créditos")]
        for i, (resposta, trecho) in enumerate(casos):
            self.falsa.fila.append(resposta)
            r = voz.enviar_teste(self.app, self.con, "tela-erro-%d" % i, "Oi, tudo bem?")
            self.assertEqual(r["estado"], "erro")
            self.assertIn(trecho, r["erro"])
            self.assertNotIn(CHAVE, repr(r))
        self.assertEqual(len(self.falsa.pedidos), 3)
        self.assertEqual(voz.usados_hoje(self.con), 0)
        self.assertEqual(self.temporarios(), [])
        self.assert_nada_saiu()

    def test_temporarios_apagados_quando_a_conversao_falha(self):
        self.sem_ffmpeg_real()
        criados = []
        original = voz_cliente.arquivo_temporario

        def anotar(pasta_dados, sufixo):
            criados.append(original(pasta_dados, sufixo))
            if os.name != "nt":
                self.assertEqual(os.stat(criados[-1]).st_mode & 0o777, 0o600)
            return criados[-1]
        with mock.patch.object(voz_cliente, "arquivo_temporario", side_effect=anotar):
            r = voz.enviar_teste(self.app, self.con, "tela-0000010", "Oi.")
        self.assertEqual((r["estado"], r["codigo"]), ("erro", "ffmpeg_ausente"))
        self.assertEqual(len(criados), 2)
        self.assertTrue(all(os.path.dirname(c) == self.pasta for c in criados))
        self.assertEqual(self.temporarios(), [], "temporários ficaram depois da falha")
        self.assertEqual(voz.usados_hoje(self.con), 3, "a ElevenLabs gerou: a reserva fica")
        self.assert_nada_saiu()

    def test_ffmpeg_recebe_lista_sem_o_texto(self):
        with mock.patch.object(voz_cliente.subprocess, "run") as run:
            run.return_value = types.SimpleNamespace(returncode=1)
            with self.assertRaises(voz_cliente.ErroVoz):
                voz_cliente.converter("ffmpeg", "/e.mp3", "/s.ogg")
        args, kwargs = run.call_args
        self.assertIsInstance(args[0], list)
        self.assertNotIn("shell", kwargs)
        self.assertIn("timeout", kwargs)
        self.assertEqual(args[0][args[0].index("-ar") + 1], "48000")
        self.assertEqual(args[0][args[0].index("-ac") + 1], "1")
        self.assertEqual(args[0][args[0].index("-b:a") + 1], "32k")


if __name__ == "__main__":
    unittest.main()
