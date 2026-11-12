"""traduzir_evento da Evolution: texto, áudio, imagem, documento, grupo, fromMe, @lid com e sem remoteJidAlt/senderPn,
estado de conexão, QR e corpo malformado."""
import sys

sys.dont_write_bytecode = True

import os  # noqa: E402
import unittest  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from servico.conectores import evolution  # noqa: E402

LEAD = "5511900000001@s.whatsapp.net"
LID = "123456789012345@lid"


def upsert(chave, mensagem, evento="messages.upsert", **extra):
    dados = dict({"key": chave, "pushName": "Lead", "message": mensagem, "messageTimestamp": 1700000000}, **extra)
    return {"event": evento, "instance": "loja", "data": dados}


def traduzir(corpo):
    return evolution.Evolution("http://127.0.0.1:9", "k", "http://x", "s").traduzir_evento(corpo)


class TestTraducao(unittest.TestCase):
    def um(self, corpo):
        eventos = traduzir(corpo)
        self.assertEqual(len(eventos), 1, eventos)
        return eventos[0]

    def test_texto_recebido(self):
        e = self.um(upsert({"remoteJid": LEAD, "fromMe": False, "id": "M1"}, {"conversation": "quero saber o preço"}))
        self.assertEqual(e, {"tipo_evento": "mensagem", "direcao": "recebida", "id_externo": "M1",
                             "remetente": "5511900000001", "fromMe": False, "grupo": False, "tipo": "texto",
                             "texto": "quero saber o preço", "timestamp": 1700000000, "lid": None,
                             "alternativa": None, "nome_perfil": "Lead"})

    def test_texto_estendido(self):
        e = self.um(upsert({"remoteJid": LEAD, "fromMe": False, "id": "M2"},
                           {"extendedTextMessage": {"text": "veja https://exemplo.invalid"}}))
        self.assertEqual((e["tipo"], e["texto"]), ("texto", "veja https://exemplo.invalid"))

    def test_audio_imagem_documento_outro(self):
        casos = (({"audioMessage": {"seconds": 4, "ptt": True}}, "audio", None),
                 ({"imageMessage": {"caption": "foto"}}, "imagem", "foto"),
                 ({"documentMessage": {"fileName": "a.pdf"}}, "documento", None),
                 ({"documentWithCaptionMessage": {"message": {"documentMessage": {"caption": "nota"}}}},
                  "documento", "nota"),
                 ({"stickerMessage": {}}, "outro", None))
        for mensagem, tipo, texto in casos:
            e = self.um(upsert({"remoteJid": LEAD, "fromMe": False, "id": "X"}, mensagem))
            self.assertEqual((e["tipo"], e["texto"]), (tipo, texto), mensagem)

    def test_grupo(self):
        e = self.um(upsert({"remoteJid": "120363000000000001@g.us", "fromMe": False, "id": "G1",
                            "participant": "5511900000002@s.whatsapp.net"}, {"conversation": "oi grupo"}))
        self.assertTrue(e["grupo"])
        self.assertEqual(e["remetente"], "5511900000002")

    def test_from_me(self):
        e = self.um(upsert({"remoteJid": LEAD, "fromMe": True, "id": "E1"}, {"conversation": "resposta"}))
        self.assertEqual((e["direcao"], e["fromMe"], e["remetente"]), ("enviada", True, "5511900000001"))

    def test_send_message_e_enviada(self):
        e = self.um(upsert({"remoteJid": LEAD, "id": "E2"}, {"conversation": "x"}, evento="send.message"))
        self.assertEqual((e["direcao"], e["fromMe"]), ("enviada", True))

    def test_lid_com_remote_jid_alt(self):
        e = self.um(upsert({"remoteJid": LID, "remoteJidAlt": LEAD, "addressingMode": "lid", "fromMe": False,
                            "id": "L1"}, {"conversation": "oi"}))
        self.assertEqual((e["lid"], e["alternativa"], e["remetente"]), (LID, LEAD, "5511900000001"))

    def test_lid_com_sender_pn(self):
        e = self.um(upsert({"remoteJid": LID, "senderPn": LEAD, "fromMe": False, "id": "L2"}, {"conversation": "oi"}))
        self.assertEqual((e["lid"], e["alternativa"], e["remetente"]), (LID, LEAD, "5511900000001"))

    def test_lid_sem_alternativa(self):
        e = self.um(upsert({"remoteJid": LID, "fromMe": False, "id": "L3"}, {"conversation": "oi"}))
        self.assertEqual((e["lid"], e["alternativa"], e["remetente"]), (LID, None, None))

    def test_jid_com_dispositivo(self):
        e = self.um(upsert({"remoteJid": "5511900000001:12@s.whatsapp.net", "fromMe": False, "id": "D1"},
                           {"conversation": "oi"}))
        self.assertEqual(e["remetente"], "5511900000001")

    def test_estado_e_qr(self):
        self.assertEqual(self.um({"event": "connection.update", "data": {"instance": "loja", "state": "open"}}),
                         {"tipo_evento": "estado", "estado": "conectado"})
        self.assertEqual(self.um({"event": "CONNECTION_UPDATE", "data": {"state": "close"}})["estado"],
                         "desconectado")
        qr = self.um({"event": "qrcode.updated", "data": {"qrcode": {"base64": "data:image/png;base64,AAAA"}}})
        self.assertEqual(qr, {"tipo_evento": "qr", "qr": "data:image/png;base64,AAAA"})

    def test_malformado_ou_desconhecido_vira_lista_vazia(self):
        for corpo in (None, [], "x", {}, {"event": "presence.update", "data": {}},
                      {"event": "messages.upsert", "data": {"key": {"remoteJid": LEAD}}},
                      {"event": "messages.upsert", "data": "lixo"},
                      {"event": "qrcode.updated", "data": {"qrcode": "x"}}):
            self.assertEqual(traduzir(corpo), [], corpo)

    def test_timestamp_em_texto(self):
        e = self.um(upsert({"remoteJid": LEAD, "fromMe": False, "id": "T1"}, {"conversation": "oi"},
                           messageTimestamp="1700000001"))
        self.assertEqual(e["timestamp"], 1700000001)


if __name__ == "__main__":
    unittest.main()
