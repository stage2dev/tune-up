"""Preparo em um passo: cada passo confere antes de agir; instaladores certos por sistema; nunca sudo; esperas com
relógio falso; nada de Docker, rede ou processo de verdade."""
import sys

sys.dont_write_bytecode = True

import io  # noqa: E402
import os  # noqa: E402
import shutil  # noqa: E402
import tempfile  # noqa: E402
import unittest  # noqa: E402

AQUI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(AQUI))
sys.path.insert(0, AQUI)

from servico import evolution_local, pasta, preparo, preparo_docker  # noqa: E402
from preparo_falso import SistemaFalso  # noqa: E402


def mudo(*_a, **_k):
    pass


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = os.path.realpath(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, self.tmp, True)
        self.projeto = os.path.join(self.tmp, "projeto")
        os.makedirs(self.projeto)
        self.base = os.path.join(self.tmp, "dados")
        self.pasta_dados = pasta.caminho_da_pasta(self.projeto, self.base)

    def sistema(self, **k):
        k.setdefault("marca", os.path.basename(self.pasta_dados))
        return SistemaFalso(**k)

    def rodar(self, s, porta=None):
        ex = preparo.Execucao(self.projeto, self.base, sistema=s, avisar=mudo, porta=porta)
        return ex.rodar()

    def passo(self, estado, nome):
        return [p for p in estado["passos"] if p["nome"] == nome][0]

    def estados(self, estado):
        return [p["estado"] for p in estado["passos"]]


class TestePreparoMac(Base):
    def test_tudo_presente_feito_sem_instalador(self):
        s = self.sistema(evolution_no_ar=False)
        e = self.rodar(s)
        self.assertEqual(e["estado"], "feito", e)
        self.assertEqual(self.estados(e), ["feito"] * 5)
        self.assertEqual(s.instaladores(), [])
        self.assertNotIn("colima", s.programas())
        self.assertTrue(any("pull" in c for c in s.chamadas) and any("up" in c for c in s.chamadas))
        self.assertTrue(any(a.endswith("servico.py") for a in s.soltos[0]))
        self.assertIn("--projeto", s.soltos[0])
        self.assertEqual(s.soltos[0][0], sys.executable)
        self.assertNotIn("down", [a for c in s.chamadas for a in c])

    def test_sem_docker_com_brew_chama_brew_com_os_argumentos(self):
        s = self.sistema(tem=("brew",), ligado=False)
        e = self.rodar(s)
        self.assertEqual(e["estado"], "feito", e)
        self.assertEqual(s.instaladores(), [["/falso/bin/brew", "install", "colima", "docker", "docker-compose"]])
        self.assertIn(["/falso/bin/colima", "start"], s.chamadas)

    def test_sem_brew_precisa_do_dono_sem_rodar_nada(self):
        s = self.sistema(tem=())
        e = self.rodar(s)
        p = self.passo(e, "docker_instalado")
        self.assertEqual(e["estado"], "precisa_do_dono")
        self.assertEqual(p["estado"], "precisa_do_dono")
        self.assertEqual(p["comando"], preparo_docker.HOMEBREW)
        self.assertIn("raw.githubusercontent.com/Homebrew/install/HEAD/install.sh", p["comando"])
        self.assertEqual(s.chamadas, [])
        self.assertEqual(self.estados(e)[1:], ["pendente"] * 4)
        self.assertFalse(os.path.exists(evolution_local.caminho_env(self.pasta_dados)))

    def test_brew_falha_vira_falhou_com_o_final_da_saida(self):
        s = self.sistema(tem=("brew",))
        s.brew_instala = False
        e = self.rodar(s)
        p = self.passo(e, "docker_instalado")
        self.assertEqual(p["estado"], "falhou")
        self.assertIn("brew falhou", p["detalhe"])

    def test_docker_parado_liga_o_colima_e_espera(self):
        s = self.sistema(ligado=False)
        e = self.rodar(s)
        self.assertEqual(self.passo(e, "docker_ligado")["estado"], "feito")
        self.assertIn(["/falso/bin/colima", "start"], s.chamadas)

    def test_docker_desktop_aberto_quando_nao_ha_colima(self):
        s = self.sistema(tem=("docker",), ligado=False)
        s.arquivos.add("/Applications/Docker.app")
        e = self.rodar(s)
        self.assertEqual(self.passo(e, "docker_ligado")["estado"], "feito")
        self.assertIn(["/usr/bin/open", "-a", "Docker"], s.chamadas)

    def test_docker_que_demora_a_responder_e_esperado(self):
        s = self.sistema(ligado=False)
        s.colima_liga = False
        s.respostas[("colima", "start")] = (0, "done")   # liga, mas o docker só responde 30 s depois

        original = s.rodar

        def rodar(args, tempo, pasta=None):
            if args[1:2] == ["info"] and s.agora >= 30:
                s.ligado = True
            return original(args, tempo, pasta)
        s.rodar = rodar
        e = self.rodar(s)
        self.assertEqual(self.passo(e, "docker_ligado")["estado"], "feito", e)
        self.assertEqual(e["estado"], "feito", e)
        self.assertGreaterEqual(s.agora, 30)
        self.assertLess(s.agora, preparo_docker.ESPERA_LIGAR)

    def test_docker_que_nunca_liga_falha_depois_da_espera(self):
        s = self.sistema(tem=("docker",), ligado=False)
        s.arquivos.add("/Applications/Docker.app")
        s.respostas[("open", "-a")] = (0, "")   # abre, mas o Docker nunca responde
        e = self.rodar(s)
        p = self.passo(e, "docker_ligado")
        self.assertEqual(p["estado"], "falhou")
        self.assertGreaterEqual(s.agora, preparo_docker.ESPERA_LIGAR)
        self.assertLess(s.agora, preparo_docker.ESPERA_LIGAR + 10)
        self.assertEqual(self.passo(e, "evolution_preparada")["estado"], "pendente")

    def test_compose_avulso_quando_falta_o_plugin(self):
        s = self.sistema(tem=("docker", "docker-compose", "colima"), compose_plugin=False)
        e = self.rodar(s)
        self.assertEqual(e["estado"], "feito", e)
        self.assertTrue(any(c[0] == "/falso/bin/docker-compose" and "pull" in c for c in s.chamadas))


class TesteOutrosSistemas(Base):
    def test_windows_com_winget(self):
        s = self.sistema(plataforma="win32", tem=("winget",), ligado=False)
        s.arquivos.add(os.path.join("C:\\PF", "Docker", "Docker", "Docker Desktop.exe"))
        s.compose_plugin = True
        e = self.rodar(s)
        self.assertEqual(s.instaladores()[0], ["/falso/bin/winget"] + list(preparo_docker.WINGET))
        self.assertEqual(e["estado"], "feito", e)
        self.assertTrue(any(a.endswith("Docker Desktop.exe") for a in s.soltos[0]))

    def test_windows_sem_winget_aponta_a_pagina_e_a_licenca(self):
        s = self.sistema(plataforma="win32", tem=())
        p = self.passo(self.rodar(s), "docker_instalado")
        self.assertEqual(p["estado"], "precisa_do_dono")
        self.assertEqual(p["comando"], preparo_docker.URL_WINDOWS)
        self.assertIn("reiniciar", p["mensagem"])
        self.assertIn("empresas maiores", p["mensagem"])
        self.assertEqual(s.chamadas, [])

    def test_linux_nunca_roda_sudo_e_mostra_o_comando_da_distro(self):
        for os_release, esperado in (('ID=ubuntu\nID_LIKE=debian\n', "docker-compose-v2"),
                                     ('ID="fedora"\n', "dnf install"), ("ID=arch\n", "pacman -S"),
                                     ("ID=linuxmint\nID_LIKE=\"ubuntu debian\"\n", "apt-get")):
            s = self.sistema(plataforma="linux", tem=())
            s.os_release = os_release
            p = self.passo(self.rodar(s), "docker_instalado")
            self.assertEqual(p["estado"], "precisa_do_dono")
            self.assertIn(esperado, p["comando"])
            self.assertIn("usermod -aG docker", p["comando"])
            self.assertEqual(s.chamadas, [])

    def test_linux_distro_desconhecida_aponta_o_guia(self):
        s = self.sistema(plataforma="linux", tem=())
        s.os_release = "ID=gentoo\n"
        self.assertEqual(self.passo(self.rodar(s), "docker_instalado")["comando"], preparo_docker.URL_LINUX)

    def test_linux_docker_parado_pede_systemctl_sem_sudo_nosso(self):
        s = self.sistema(plataforma="linux", tem=("docker",), ligado=False)
        p = self.passo(self.rodar(s), "docker_ligado")
        self.assertEqual(p["estado"], "precisa_do_dono")
        self.assertEqual(p["comando"], "sudo systemctl start docker")
        self.assertFalse(any("sudo" in c or "systemctl" in os.path.basename(c[0]) for c in s.chamadas))


class TesteEvolutionEServico(Base):
    def test_compose_falha_guarda_o_final_sem_segredo(self):
        s = self.sistema()
        e1 = None
        evolution_local.preparar(self.projeto, self.base)
        chave = evolution_local.ler_ambiente(self.pasta_dados)["VENDAS_EVOLUTION_CHAVE"]
        senha = evolution_local._ler_env(evolution_local.caminho_env(self.pasta_dados))["POSTGRES_PASSWORD"]
        s.respostas[("docker", "compose")] = (0, "v2")
        saida = "linha 1\nerro: chave=%s senha=%s\nError response from daemon: falhou" % (chave, senha)
        s.rodar = self._com_pull(s, (1, saida))
        e1 = self.rodar(s)
        p = self.passo(e1, "evolution_no_ar")
        self.assertEqual(p["estado"], "falhou")
        self.assertIn("Error response from daemon", p["detalhe"])
        self.assertIn("***", p["detalhe"])
        for arquivo in (preparo.caminhos(self.pasta_dados)["estado"], preparo.caminhos(self.pasta_dados)["log"]):
            with open(arquivo, encoding="utf-8") as f:
                texto = f.read()
            self.assertNotIn(chave, texto)
            self.assertNotIn(senha, texto)
        self.assertEqual(self.passo(e1, "servico_ligado")["estado"], "pendente")

    def _com_pull(self, s, resposta):
        original = s.rodar

        def rodar(args, tempo, pasta=None):
            if "pull" in args:
                s.chamadas.append(list(args))
                return resposta
            return original(args, tempo, pasta)
        return rodar

    def test_evolution_que_nunca_responde_falha_depois_da_espera(self):
        s = self.sistema()
        s.evolution_sobe = False
        e = self.rodar(s)
        p = self.passo(e, "evolution_no_ar")
        self.assertEqual(p["estado"], "falhou")
        self.assertIn("5 minutos", p["mensagem"])
        self.assertGreaterEqual(s.agora, 300)
        self.assertLess(s.agora, 310)

    def test_env_existente_fica_intocado(self):
        evolution_local.preparar(self.projeto, self.base)
        env = evolution_local.caminho_env(self.pasta_dados)
        with open(env, "rb") as f:
            antes = f.read()
        e = self.rodar(self.sistema())
        self.assertEqual(e["estado"], "feito", e)
        with open(env, "rb") as f:
            self.assertEqual(f.read(), antes)

    def test_porta_da_evolution_ocupada_por_outro_escolhe_outra(self):
        s = self.sistema()
        s.ocupadas.add(8080)
        e = self.rodar(s)
        self.assertEqual(e["estado"], "feito", e)
        url = evolution_local.ler_ambiente(self.pasta_dados)["VENDAS_EVOLUTION_URL"]
        self.assertEqual(url, "http://127.0.0.1:18081")
        self.assertEqual(e["portas"]["evolution"], 18081)

    def test_servico_ja_rodando_nao_sobe_outro(self):
        from servico import travas
        os.makedirs(self.pasta_dados, exist_ok=True)
        trava = travas.TravaDoProcesso(self.pasta_dados).pegar()
        self.addCleanup(trava.soltar)
        s = self.sistema()
        e = self.rodar(s)
        self.assertEqual(self.passo(e, "servico_ligado")["estado"], "feito")
        self.assertEqual(s.soltos, [])

    def test_servico_que_sai_ao_subir_falha_com_o_log(self):
        s = self.sistema()
        s.servico_sai = True
        p = self.passo(self.rodar(s), "servico_ligado")
        self.assertEqual(p["estado"], "falhou")
        self.assertIn("porta ocupada", p["detalhe"])

    def test_servico_com_marca_de_outro_projeto_nao_conta(self):
        s = self.sistema(marca="outro")
        p = self.passo(self.rodar(s), "servico_ligado")
        self.assertEqual(p["estado"], "falhou")
        self.assertGreaterEqual(s.agora, 60)

    def test_segunda_rodada_retoma_sem_repetir_nada(self):
        s = self.sistema(tem=("brew",), ligado=False)
        s.evolution_sobe = False
        e = self.rodar(s)
        self.assertEqual(self.passo(e, "evolution_no_ar")["estado"], "falhou")
        env = evolution_local.caminho_env(self.pasta_dados)
        with open(env, "rb") as f:
            antes = f.read()
        s.evolution_no_ar = True   # o dono resolveu e clicou de novo
        s.chamadas, s.soltos = [], []
        e2 = self.rodar(s)
        self.assertEqual(e2["estado"], "feito", e2)
        self.assertNotEqual(e2["id"], e["id"])
        self.assertEqual(s.instaladores(), [])
        self.assertNotIn("colima", s.programas())
        self.assertFalse(any("pull" in c or "up" in c for c in s.chamadas))
        with open(env, "rb") as f:
            self.assertEqual(f.read(), antes)
        self.assertEqual(len(s.soltos), 1)   # só o serviço, que ainda não estava ligado

    def test_erro_inesperado_num_passo_vira_falhou(self):
        s = self.sistema()

        def explode(*_a, **_k):
            raise RuntimeError("quebrou")
        s.achar = explode
        e = self.rodar(s)
        p = self.passo(e, "docker_instalado")
        self.assertEqual(p["estado"], "falhou")
        self.assertIn("RuntimeError", p["detalhe"])
        self.assertEqual(e["estado"], "falhou")

    def test_saida_na_tela_sem_segredo(self):
        evolution_local.preparar(self.projeto, self.base)
        chave = evolution_local.ler_ambiente(self.pasta_dados)["VENDAS_EVOLUTION_CHAVE"]
        s = self.sistema()
        s.respostas[("docker", "info")] = (1, "falhou com %s" % chave)
        s.tem = {"docker"}
        tela = io.StringIO()

        def avisar(*a, **k):
            k.pop("flush", None)
            k.pop("file", None)
            print(*a, file=tela)
        ex = preparo.Execucao(self.projeto, self.base, sistema=s, avisar=avisar)
        ex.progresso("vazou %s" % chave)
        ex.rodar()
        self.assertIn("***", tela.getvalue())
        self.assertNotIn(chave, tela.getvalue())


if __name__ == "__main__":
    unittest.main()
