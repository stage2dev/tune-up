"""Pasta de dados externa (C9), banco SQLite (unicidade, migração) e telefone com o 9º dígito."""
import sys

sys.dont_write_bytecode = True

import os  # noqa: E402
import shutil  # noqa: E402
import sqlite3  # noqa: E402
import stat  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))

from servico import banco, pasta, telefone  # noqa: E402

CEL = "+55 11 90000-0001"


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.projeto = os.path.join(self.tmp, "projeto")
        os.makedirs(self.projeto)
        self.base = os.path.join(self.tmp, "dados")


class TestePasta(Base):
    def test_cria_fora_do_projeto_com_hash_da_raiz(self):
        p = pasta.pasta_de_dados(self.projeto, base=self.base)
        self.assertTrue(os.path.isdir(p))
        self.assertEqual(os.path.dirname(p), self.base)
        self.assertEqual(p, pasta.pasta_de_dados(self.projeto, base=self.base))
        outro = os.path.join(self.tmp, "outro")
        os.makedirs(outro)
        self.assertNotEqual(p, pasta.pasta_de_dados(outro, base=self.base))

    def test_recusa_pasta_dentro_do_projeto(self):
        with self.assertRaisesRegex(pasta.PastaRecusada, "dentro do projeto"):
            pasta.pasta_de_dados(self.projeto, base=os.path.join(self.projeto, "dados"))
        self.assertFalse(os.path.exists(os.path.join(self.projeto, "dados")))

    def test_recusa_pasta_sob_stfolder_ou_stignore(self):
        for marca in (".stfolder", ".stignore"):
            sync = os.path.join(self.tmp, "sync" + marca)
            os.makedirs(os.path.join(sync, "a", "b"))
            open(os.path.join(sync, marca), "w").close()
            with self.assertRaisesRegex(pasta.PastaRecusada, "sincronizada"):
                pasta.pasta_de_dados(self.projeto, base=os.path.join(sync, "a", "b", "dados"))

    def test_base_por_sistema(self):
        self.assertIn(os.path.join("Library", "Application Support", "tune-up-vendas"), pasta.pasta_base("darwin", {}))
        self.assertEqual(pasta.pasta_base("linux", {"XDG_DATA_HOME": "/x"}), os.path.join("/x", "tune-up-vendas"))
        self.assertIn(os.path.join(".local", "share"), pasta.pasta_base("linux", {}))
        self.assertEqual(pasta.pasta_base("win32", {"LOCALAPPDATA": "C:\\L"}), os.path.join("C:\\L", "tune-up-vendas"))

    @unittest.skipIf(os.name == "nt", "Windows não tem modos 0700/0600")
    def test_permissoes_0700_e_0600(self):
        p = pasta.pasta_de_dados(self.projeto, base=self.base)
        os.chmod(p, 0o755)
        p = pasta.pasta_de_dados(self.projeto, base=self.base)
        self.assertEqual(stat.S_IMODE(os.stat(p).st_mode), 0o700)
        con = banco.abrir(p)
        self.addCleanup(con.close)
        banco.registrar_evento(con, "teste")
        nomes = sorted(os.listdir(p))
        self.assertEqual(nomes, ["vendas.db", "vendas.db-shm", "vendas.db-wal"])
        for nome in nomes:
            self.assertEqual(stat.S_IMODE(os.stat(os.path.join(p, nome)).st_mode), 0o600, nome)


class TesteBanco(Base):
    def setUp(self):
        super().setUp()
        self.dados = pasta.pasta_de_dados(self.projeto, base=self.base)
        self.con = banco.abrir(self.dados)
        self.addCleanup(self.con.close)

    def test_pragmas(self):
        self.assertEqual(self.con.execute("PRAGMA journal_mode").fetchone()[0], "wal")
        self.assertEqual(self.con.execute("PRAGMA foreign_keys").fetchone()[0], 1)
        self.assertEqual(self.con.execute("PRAGMA busy_timeout").fetchone()[0], banco.ESPERA_MS)
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute("INSERT INTO conversas (contato_id, criado_em) VALUES (999, 'x')")

    def test_migracao_da_versao_0_e_reabrir_idempotente(self):
        self.assertEqual(self.con.execute("PRAGMA user_version").fetchone()[0], banco.VERSAO)
        cid = banco.salvar_contato(self.con, CEL, nome="Ana")
        self.con.close()
        for _ in range(2):
            con = banco.abrir(self.dados)
            self.assertEqual(con.execute("PRAGMA user_version").fetchone()[0], banco.VERSAO)
            self.assertEqual(banco.buscar_contato(con, CEL)["id"], cid)
            con.close()
        self.con = banco.abrir(self.dados)

    def test_migracao_3_preenche_tentado_em_das_linhas_que_ja_existem(self):
        con = sqlite3.connect(":memory:", isolation_level=None)
        for comando in banco.MIGRACOES[0] + banco.MIGRACOES[1]:
            con.execute(comando)
        con.execute("PRAGMA user_version = 2")
        con.execute("INSERT INTO envios (chave_dedupe, estado, origem, criado_em) "
                    "VALUES ('k', 'incerto', 'manual', '2026-11-10T10:00:00+00:00')")
        for _ in range(2):   # rodar de novo não muda nada
            banco.migrar(con)
        self.assertEqual(con.execute("SELECT tentado_em FROM envios").fetchone()[0], "2026-11-10T10:00:00+00:00")
        con.close()

    def test_versao_mais_nova_que_o_codigo_e_recusada(self):
        self.con.execute("PRAGMA user_version = %d" % (banco.VERSAO + 1))
        with self.assertRaisesRegex(RuntimeError, "só conhece"):
            banco.migrar(self.con)
        self.assertFalse(self.con.in_transaction)

    def test_id_externo_repetido_vira_uma_linha(self):
        conversa = banco.abrir_conversa(self.con, banco.salvar_contato(self.con, CEL))
        self.assertIsNotNone(banco.registrar_mensagem(self.con, conversa, "entrada", "oi", id_externo="M1"))
        self.assertIsNone(banco.registrar_mensagem(self.con, conversa, "entrada", "oi", id_externo="M1"))
        n = self.con.execute("SELECT COUNT(*) FROM mensagens WHERE id_externo = 'M1'").fetchone()[0]
        self.assertEqual(n, 1)

    def test_mensagem_com_conversa_inexistente_sobe_erro(self):
        with self.assertRaises(sqlite3.IntegrityError):
            banco.registrar_mensagem(self.con, 999, "entrada", "oi", id_externo="M2")

    def test_chave_dedupe_repetida_recusada_mas_negado_nao_ocupa(self):
        self.assertIsNotNone(banco.registrar_envio(self.con, "k1", "manual", estado="negado", motivo="optout"))
        self.assertIsNotNone(banco.registrar_envio(self.con, "k1", "manual", estado="negado", motivo="teto"))
        primeiro = banco.registrar_envio(self.con, "k1", "manual")
        self.assertIsNotNone(primeiro)
        self.assertIsNone(banco.registrar_envio(self.con, "k1", "manual"))
        banco.mudar_envio(self.con, primeiro, "enviado", id_externo="X1")
        self.assertIsNone(banco.registrar_envio(self.con, "k1", "ia"))
        self.assertIsNotNone(banco.registrar_envio(self.con, "k1", "manual", estado="negado"))
        ocupando = self.con.execute("SELECT COUNT(*) FROM envios WHERE chave_dedupe='k1' AND estado<>'negado'")
        self.assertEqual(ocupando.fetchone()[0], 1)

    def test_estado_invalido_e_envio_inexistente(self):
        with self.assertRaises(ValueError):
            banco.registrar_envio(self.con, "k2", "manual", estado="talvez")
        with self.assertRaises(banco.EscritaSemEfeito):
            banco.mudar_envio(self.con, 999, "enviado")

    def test_optout_casa_as_duas_variantes_do_9(self):
        banco.marcar_optout(self.con, "11 98000-0001")
        self.assertTrue(banco.em_optout(self.con, "+55 11 98000-0001"))
        self.assertTrue(banco.em_optout(self.con, "551180000001"))  # a mesma pessoa, sem o 9º dígito
        self.assertFalse(banco.em_optout(self.con, "11 98000-0003"))

    def test_optout_gravado_sem_9_casa_com_9(self):
        banco.marcar_optout(self.con, "551180000002")  # celular antigo, sem o 9º dígito
        self.assertTrue(banco.em_optout(self.con, "5511980000002"))
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM contatos").fetchone()[0], 1)
        self.assertEqual(banco.salvar_contato(self.con, "11 98000-0002"),
                         banco.buscar_contato(self.con, "551180000002")["id"])

    def test_celular_e_fixo_parecidos_sao_dois_contatos(self):
        for cel, fixo in (("11 93333-4444", "11 3333-4444"), ("+55 11 92333-4444", "+55 11 2333-4444")):
            a = banco.salvar_contato(self.con, fixo, nome="Padaria")
            b = banco.salvar_contato(self.con, cel, nome="Joao")
            self.assertNotEqual(a, b, cel)
            self.assertEqual(banco.buscar_contato(self.con, cel)["nome"], "Joao")
            self.assertEqual(banco.buscar_contato(self.con, fixo)["nome"], "Padaria")
            banco.marcar_optout(self.con, cel)
            self.assertTrue(banco.em_optout(self.con, cel))
            self.assertFalse(banco.em_optout(self.con, fixo), fixo)

    def test_config_recusa_segredo(self):
        banco.gravar_config(self.con, "janela_inicio", "09:00")
        banco.gravar_config(self.con, "janela_inicio", "10:00")
        self.assertEqual(banco.ler_config(self.con, "janela_inicio"), "10:00")
        for nome in ("openai_api_key", "token_evolution", "senha"):
            with self.assertRaises(ValueError):
                banco.gravar_config(self.con, nome, "x")
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM config").fetchone()[0], 1)

    def test_batimento_uma_linha(self):
        banco.bater(self.con, pid=1)
        banco.bater(self.con, pid=2)
        self.assertEqual([tuple(r) for r in self.con.execute("SELECT id, pid FROM batimento")], [(1, 2)])


class TesteTelefone(unittest.TestCase):
    def test_normaliza_com_55_e_9(self):
        self.assertEqual(telefone.normalizar("(11) 90000-0001"), "5511900000001")
        self.assertEqual(telefone.normalizar("+55 11 90000-0001"), "5511900000001")
        self.assertEqual(telefone.normalizar("551180000002"), "5511980000002")
        self.assertEqual(telefone.normalizar("5511980000002@s.whatsapp.net"), "5511980000002")
        self.assertEqual(telefone.normalizar("1132000000"), "551132000000")  # fixo

    def test_variantes(self):
        self.assertEqual(telefone.variantes("11 98000-0001"), ["5511980000001", "551180000001"])
        # 9 seguido de 0 a 5 não tem forma antiga de 8 dígitos: sem o 9 seria um fixo de outra pessoa
        for cel in ("11 90000-0001", "11 92333-4444", "11 93333-4444", "11 95000-0001"):
            self.assertEqual(len(telefone.variantes(cel)), 1, cel)
        self.assertEqual(telefone.variantes("11 3333-4444"), ["551133334444"])
        self.assertEqual(telefone.variantes("1132000000"), ["551132000000"])
        self.assertEqual(telefone.variantes("+1 650 555 0000"), ["16505550000"])

    def test_recusa_lid_e_tamanho(self):
        for ruim in ("123456789012345@lid", "120363000000000000@g.us", "", "123", "5511", "55119000000012",
                     "5501900000001", "5511800000001"):
            with self.assertRaises(telefone.TelefoneInvalido, msg=ruim):
                telefone.normalizar(ruim)


if __name__ == "__main__":
    unittest.main()
