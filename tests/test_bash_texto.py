"""Tests: the Bash text as the tokenizer reads it (bash_texto.legivel). Commands that Bash runs
but shlex used to read as part of a string: `$'...'`, comments, heredocs, `$(...)` inside double
quotes, backticks, `\\<newline>`; and `wsl <cmd>` with `/mnt/<drive>` paths.
Run: python3 -m unittest discover -s tests -q"""
import os
import random
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

from base import IS_WIN, SCRIPT, Base

sys.path.insert(0, os.path.dirname(SCRIPT))
from tuneup import bash_guarda, caminhos  # noqa: E402
from tuneup.bash_parse import ESCOPO, comando_wsl, comandos, sem_heredoc  # noqa: E402
from tuneup.bash_texto import OUTRA, ansi_c, legivel  # noqa: E402

BASH = None if IS_WIN else shutil.which("bash")
SETTINGS = "~/.claude/settings.json"


def exes(cmd):
    """First word of every command the guard reads in `cmd`."""
    return [t[0] for _, t in comandos(sem_heredoc(cmd)) if t and t[0] != ESCOPO]


class TestAnsiC(unittest.TestCase):
    def test_decodifica(self):
        for corpo, valor in ((r"a\nb", "a\nb"), (r"\'", "'"), (r"\x72m", "rm"), (r"\162\155", "rm"), (r"\u0072m", "rm"),
                             (r"\U00000072m", "rm"), (r"a\\b", "a\\b"), (r"\z", "\\z"), (r"\cA", "\x01"),
                             (r"a\x00b", "a"), (r"a\0b", "a"), (r"\e[0m", "\x1b[0m"), ("", ""), ("a\\", "a\\")):
            self.assertEqual(ansi_c(corpo), valor, corpo)

    def test_vira_palavra_comum(self):
        self.assertEqual(legivel("printf $'a\\tb'"), "printf 'a\tb'")
        self.assertEqual(legivel("echo $'it\\'s'"), "echo 'it'\\''s'")
        self.assertEqual(legivel("IFS=$'\\n' read x"), "IFS='\n' read x")
        self.assertEqual(legivel('echo $"oi"'), 'echo "oi"')
        self.assertEqual(legivel('echo "it\'s $\'x\'"'), 'echo "it\'s $\'x\'"')  # no ANSI-C inside "..."
        self.assertEqual(legivel("echo '$'\\''x'"), "echo '$'\\''x'")  # nor inside '...'

    def test_comando_depois_da_aspa_aparece(self):
        for c in ("echo $'\\'' ; rm app.py ; echo \\'", "$'rm' app.py", "$'\\x72m' app.py", "$'\\162m' app.py",
                  "echo $'\\\\' ; rm app.py ; echo '", 'bash -c "echo \\$\'\\\\\'\' ; rm app.py ; echo \\\\\'"',
                  "echo $'a\nb' ; rm app.py", "eval $'rm app.py'"):
            with self.subTest(c=c):
                self.assertIn("rm", exes(c))

    def test_nao_fechada_nao_esconde_o_que_veio_antes(self):
        self.assertIn("rm", exes("rm app.py\necho $'abc"))
        self.assertIn("rm", exes('rm app.py\necho "abc'))
        self.assertIn("rm", exes("rm app.py ; echo 'abc"))
        self.assertIn("rm", exes("$(rm app.py)\necho $'abc"))


class TestComentarioEContinuacao(unittest.TestCase):
    def test_comentario_sai(self):
        self.assertEqual(legivel("ls # it's here\npwd"), "ls \npwd")
        self.assertEqual(legivel("#!/bin/sh\nls"), "\nls")
        self.assertIn("rm", exes("echo # it's\necho $'\\'' ; rm app.py ; echo \\'"))
        self.assertIn("rm", exes("`# it's\n` ; echo $'\\'' ; rm app.py; echo \\'"))

    def test_nao_e_comentario(self):
        for c in ("echo a#b", "echo ${x#y}", "echo $#", "echo ${#x}", "echo '# x'", 'echo "# x"', "echo \\# x",
                  "echo $((16#ff))"):
            self.assertEqual(legivel(c), c, c)

    def test_continuacao_de_linha(self):
        self.assertEqual(exes("r\\\nm app.py"), ["rm"])
        self.assertEqual(exes("echo a \\\\\nrm app.py"), ["echo", "rm"])  # `\\` then a real line end
        self.assertEqual(exes("git status \\\n  --short"), ["git"])
        self.assertEqual(exes("\\\n# x\nls"), ["ls"])

    def test_barra_cr_lf_nas_duas_leituras(self):
        c = "echo a \\\r\nrm app.py"  # Bash: an escaped CR, then a new command
        self.assertIn(OUTRA, legivel(c))
        self.assertIn("rm", exes(c))
        self.assertIn(["git", "stash", "-u"], [t for _, t in comandos(sem_heredoc("git stash \\\r\n -u"))])

    def test_fim_de_linha_grudado_em_redirecao(self):
        self.assertEqual(exes("echo a\n<<<x rm app.py"), ["echo", "rm"])
        self.assertEqual(exes("echo a\n</dev/null rm app.py"), ["echo", "rm"])
        self.assertEqual(exes("ls 2>&1 | cat ; (cd x && ls) >o\nls"), ["ls", "cat", "cd", "ls", "ls"])
        self.assertEqual(exes("a &> f ; b |& c ; d >| e"), ["a", "b", "c", "d"])


class TestHeredoc(unittest.TestCase):
    def test_corpo_sai(self):
        self.assertEqual(legivel("cat <<EOF\nrm app.py\nEOF\nls"), "cat <<EOF\nls")
        self.assertEqual(legivel("cat <<-'E' | tee x <<A\n1\n\tE\n2\nA\nls"), "cat <<-'E' | tee x <<A\nls")
        self.assertEqual(exes("python3 - <<'PY'\nimport os\nos.remove('x')\nPY\nls"), ["python3", "ls"])
        self.assertEqual(exes("cat <<\\EOF\n$(rm x)\nEOF"), ["cat"])
        self.assertEqual(exes('cat <<"E O F"\nit\'s\nE O F\nls'), ["cat", "ls"])

    def test_depois_do_fim_aparece(self):
        for c in ("cat <<'E-F'\nx\nE-F\nrm app.py", "cat <<'E F'\nit's\nE F\nrm app.py", "cat <<E\\OF\nx\nEOF\nrm app.py",
                  "echo 'a\n<<EOF\n' ; rm app.py\nEOF", "echo $'\\'' '<<EOF' \\'\nrm app.py\nEOF",
                  "cat <<EOF\nit's\nEOF\necho $'\\'' ; rm app.py ; echo \\'"):
            with self.subTest(c=c):
                self.assertIn("rm", exes(c))

    def test_deslocamento_nao_e_heredoc(self):
        for c in ("x=$(( 1 << 2 ))\nrm app.py\n2", "(( 1 << 2 ))\nrm app.py\n2", "a[1<<2]=5\nrm app.py\n2",
                  "echo $[1<<2]\nrm app.py\n2", "echo ${x:1<<2}\nrm app.py\n2", 'echo "$((1<<2))"\nrm app.py\n2'):
            with self.subTest(c=c):
                self.assertIn("rm", exes(c))

    def test_duvida_da_as_duas_leituras(self):
        c = "echo a[1<<2]=3\n# it's $(rm app.py)\n2"  # an argument: here `<<2]=3` IS a heredoc
        self.assertIn(OUTRA, legivel(c))
        self.assertIn("rm", exes(c))
        self.assertNotIn(OUTRA, legivel("cat <<EOF\nx\nEOF"))
        self.assertEqual(OUTRA, ESCOPO)

    def test_corpo_sem_aspas_expande(self):
        self.assertIn("rm", exes("cat <<EOF\n$(rm app.py)\nEOF"))
        self.assertIn("rm", exes("cat <<EOF\n`rm app.py`\nEOF"))
        self.assertIn("rm", exes("cat <<EOF\nit's $(rm app.py)"))  # ended by the end of the text
        self.assertNotIn("rm", exes("cat <<'EOF'\n$(rm app.py)\nEOF"))
        self.assertNotIn("rm", exes("cat <<EOF\n\\$(rm app.py)\nEOF"))


class TestSubstituicao(unittest.TestCase):
    def test_dentro_de_aspas_duplas(self):
        for c in ('echo "$(rm app.py)"', 'echo "`rm app.py`"', 'echo "a $(echo ")" ; rm app.py)"', 'x="$(rm app.py)"',
                  'echo "$(echo "$(rm app.py)")"', 'echo "$(case x in x) rm app.py;; esac)"', "echo `rm app.py`",
                  "echo x`rm app.py`", 'echo "$(echo `rm app.py`)"', 'echo "$(cat <<EOF\n$(rm app.py)\nEOF\n)"'):
            with self.subTest(c=c):
                self.assertIn("rm", exes(c))

    def test_o_que_o_bash_nao_roda(self):
        for c in ("echo '$(rm app.py)'", "echo '`rm app.py`'", 'echo "\\$(rm app.py)"', 'echo "\\`rm app.py\\`"',
                  "echo \\$\\(rm app.py\\)", "git commit -m \"$(cat <<'EOF'\nfix: it's \"x\" `rm y` $(rm z)\nEOF\n)\""):
            with self.subTest(c=c):
                self.assertNotIn("rm", exes(c))

    def test_commit_com_heredoc_fica_um_comando(self):
        c = "git commit -m \"$(cat <<'EOF'\nfix: it's \"quoted\"\n\nCo-Authored-By: X <x@y.z>\nEOF\n)\""
        self.assertEqual(exes(c), ["git", "cat"])
        self.assertEqual(comandos(sem_heredoc(c))[0][1][:3], ["git", "commit", "-m"])

    def test_corpo_de_heredoc_nao_entra_na_palavra(self):
        c = "gh pr create --body \"$(cat <<'EOF'\nit's guarda.py trust ~/.claude/settings.json\nEOF\n)\" 2>&1 | tail -2"
        self.assertEqual(comandos(sem_heredoc(c))[0][1], ["gh", "pr", "create", "--body", "$(cat <<'EOF'\n)"])
        self.assertEqual(set(exes('echo "$(ls')), {"echo", "ls"})  # unclosed: still read (and read twice)

    def test_aspas_duplas_que_o_shlex_le_igual_ficam(self):
        for c in ('echo "a b" "c\\"d" "e\\\\f"', 'x="a $b ${c} $(date)"', 'psql "$URL" -c "select 1"'):
            self.assertEqual(legivel(c).split("\n")[0], c)
        self.assertEqual(legivel('echo "\\$HOME \\`x\\`"'), "echo '$HOME `x`'")

    def test_muito_fundo_nao_trava(self):
        self.assertIn("rm", exes('echo ' + '"$(echo ' * 40 + "rm app.py" + ')"' * 40 + " ; rm app.py"))
        legivel("(" * 5000 + '"$(' * 5000)  # no RecursionError


class TestRevisao(unittest.TestCase):
    """Findings of the security review of this reader (17/11): each one hid the command after it."""

    def test_comando_depois_aparece(self):
        for c in ("echo $(true)#; rm app.py", "echo <(true)#; rm app.py", "x=$(echo hi)#; rm app.py",
                  "echo $((1))#; rm app.py", 'echo "$(echo case)"; rm app.py; echo "x"',
                  'git log --grep "$(echo case)" ; rm app.py ; echo "done"', "cat <<$(x)\nhi\n$(x)\nrm app.py",
                  'cat <<$"E"\nhi\nE\nrm app.py', "cat <<$X\nhi\n$X\nrm app.py", "echo \"${x#'\"'}\" ; rm app.py",
                  "echo \"${x#'\"'}\" ; rm app.py\n: \\'", "echo \"${x:-'}\" ; rm app.py ; : \\'",
                  'echo "$((1<<2\n))"; rm app.py', "cat <<EOF\nx\nrm app.py", "if true; then case x in x) rm app.py;; esac; fi"):
            with self.subTest(c=c):
                self.assertIn("rm", exes(c))

    def test_segunda_volta(self):
        for c in ('echo "$(echo if case)"; rm app.py; echo "x) ; echo if esac )"',
                  'git commit -m "$(echo do case)"; rm app.py; echo "; echo if esac )"',
                  "echo \"${x#${y}'\"'}\"; rm app.py #'", "echo \"${x#'\"'}\"; r\\\nm app.py", "$(true) rm app.py",
                  "$(true)rm app.py", "{ $(true) rm app.py; }", "if $(true) rm app.py; then :; fi",
                  "[[ x =~ (#) ]] ; rm app.py", "[[ x =~ (a|#) ]] ; rm app.py", "shopt -s extglob\necho @(#x) ; rm app.py",
                  "cat <<E\n E\n'\nE\nrm app.py #'", '"rm" -rf x; echo \\', "cat <<E\\\nF\n$(rm app.py)\nEF",
                  'echo "`echo \\"\'\\"; rm app.py; echo \\"\'\\"`"', "cat <<-E\n\tx\n\tE\nrm app.py",
                  "echo `cd /tmp; echo \\\\`; echo \"${x#'\"'}\"; rm app.py", "ls | rm app.py # it's"):
            with self.subTest(c=c):
                self.assertIn("rm", exes(c))

    def test_alvo_fica_no_comando_na_leitura_cega(self):
        c = "echo \"${x#'\"'}\"; cp x ~/.config/tune-up/user.json #'"
        self.assertIn(["cp", "x", "~/.config/tune-up/user.json"], [t for _, t in comandos(sem_heredoc(c))])

    def test_aninhado_nao_cresce(self):
        import time
        for c in ("echo " + "$(echo " * 20 + "x" + ")" * 20, "echo " + '"$(echo ' * 20 + "x" + ')"' * 20):
            t0 = time.time()
            self.assertLess(len(legivel(c)), 20000)
            self.assertLess(time.time() - t0, 1)

    def test_substituicao_solta_nao_separa_o_alvo(self):
        self.assertIn(["rm", "$(true)", "f"], [t for _, t in comandos(sem_heredoc("rm $(true) f"))])
        self.assertIn(["rm", "f"], [t for _, t in comandos(sem_heredoc("rm$(true) f"))])
        self.assertEqual(exes("x=$(ls) ; cd $(dirname f) && echo done"), ["cd", "echo", "ls", "dirname"])

    def test_comentario_depois_de_subshell(self):
        self.assertEqual(exes("(true)# it's\nrm app.py"), ["true", "rm"])

    def test_sem_duvida_nao_ha_leitura_cega(self):
        for c in ('echo "${HOME}/x; rm y"', "echo 'a; rm y'", 'git commit -m "fix; rm y"', 'echo "$(date); rm y"'):
            with self.subTest(c=c):
                self.assertNotIn("rm", exes(c))

    def test_cd_do_wsl_nao_vaza_com_aspa_ansi_no_texto(self):
        toks = [t for _, t in comandos(sem_heredoc("wsl --cd /tmp true; cp x y; echo \"$'\""))]
        self.assertEqual(toks[1:5], [[ESCOPO, "+"], ["cd", "/tmp"], ["true"], [ESCOPO, "-"]])


class TestWsl(unittest.TestCase):
    def test_texto_do_shell(self):
        self.assertEqual(comando_wsl(["wsl", "rm", "/mnt/c/x"]), ["rm /mnt/c/x"])
        self.assertEqual(comando_wsl(["wsl.exe", "-d", "Ubuntu", "-u", "root", "--", "ls", "-la"]), ["ls -la"])
        self.assertEqual(comando_wsl(["wsl", "-e", "rm", "a b"]), ["rm 'a b'"])
        self.assertEqual(comando_wsl(["wsl", "--cd", "/mnt/c/x", "rm", "y"]), ["cd /mnt/c/x ; rm y"])
        self.assertEqual(comando_wsl(["wsl", "rm x ; rm y"]), ['"rm x ; rm y"', "rm x ; rm y"])
        for toks in (["wsl", "--list", "-v"], ["wsl", "--shutdown"], ["ls"], []):
            self.assertIsNone(comando_wsl(toks), toks)

    def test_abre(self):
        for c in ("wsl rm /mnt/c/Users/u/.claude/settings.json", "wsl.exe -d Ubuntu -- rm x", "wsl -e rm x",
                  "C:/Windows/System32/wsl.exe sh -c 'rm x'", "wsl bash -c 'bash -c \"rm x\"'", "wsl 'ls ; rm x'",
                  "wsl --cd /mnt/c/Users/u/.claude rm settings.json", "bash -c \"wsl rm x\""):
            with self.subTest(c=c):
                self.assertIn("rm", exes(c))
        self.assertEqual(comandos("wsl tuneup trust")[0][1], ["wsl", "tuneup", "trust"])  # the wrapper itself stays first
        self.assertEqual(exes("wsl --list -v"), ["wsl"])

    def test_cd_de_dentro_nao_vaza(self):
        toks = [t for _, t in comandos("wsl --cd /x rm y ; rm z")]
        self.assertEqual(toks[1:], [[ESCOPO, "+"], ["cd", "/x"], ["rm", "y"], [ESCOPO, "-"], ["rm", "z"]])

    def test_tres_niveis(self):
        self.assertIn("rm", exes("bash -c \"bash -c 'rm x'\""))
        self.assertIn("rm", exes("bash -c \"sh -c 'eval rm x'\""))

    def test_mnt_e_a_unidade(self):
        with mock.patch.object(caminhos, "NT", True):
            self.assertEqual(caminhos.nativo("/mnt/c/Users/x/.claude/settings.json"), "C:/Users/x/.claude/settings.json")
            self.assertEqual(caminhos.nativo("/mnt/d"), "D:/")
            self.assertEqual(caminhos.nativo("/mnt/data/x"), "/mnt/data/x")  # not a drive letter
            self.assertEqual(caminhos.nativo("/mntx/c/x"), "/mntx/c/x")
        with mock.patch.object(caminhos, "NT", False):
            self.assertEqual(caminhos.nativo("/mnt/c/x"), "/mnt/c/x")
        with mock.patch.object(bash_guarda, "NT", True):
            self.assertEqual(bash_guarda._nt("rm /mnt/c/users/x/.claude/settings.json"), "rm c:/users/x/.claude/settings.json")
            self.assertEqual(bash_guarda._nt("ls /mnt/data/x"), "ls /mnt/data/x")


class TestGuarda(Base):
    """The hook itself, in the three modes."""
    USER_JSON = {"language": "en"}
    ESCONDIDOS = ["echo $'\\'' ; rm %s ; echo \\'", 'bash -c "echo \\$\'\\\\\'\' ; rm %s ; echo \\\\\'"', 'echo "$(rm %s)"',
                  "echo `rm %s`", "cat <<EOF\n$(rm %s)\nEOF", "cat <<'E-F'\nx\nE-F\nrm %s", "echo a \\\\\nrm %s",
                  "r\\\nm %s", "echo a\n<<<x rm %s", "a[1<<2]=5\nrm %s\n2", "bash -c \"bash -c 'rm %s'\"",
                  "wsl rm %s", "wsl bash -c 'rm %s'"]

    def setUp(self):
        super().setUp()
        subprocess.run(["git", "init", "-q", self.cwd], check=True)
        os.makedirs(os.path.join(self.cwd, ".tune-up"))
        for nome in ("app.py", os.path.join(".tune-up", "config.json")):
            with open(os.path.join(self.cwd, nome), "w", encoding="utf-8") as f:
                f.write("{}")

    def test_conversa_nega(self):
        self.sessao(modo_conversa=True, modo_pesquisa=True)
        for c in self.ESCONDIDOS:
            with self.subTest(c=c):
                self.assertEqual(self.bash(c % "app.py"), "bloquear")

    def test_pesquisa_pergunta(self):
        self.sessao(modo_pesquisa=True)
        for c in self.ESCONDIDOS:
            with self.subTest(c=c):
                self.assertEqual(self.bash(c % "app.py"), "perguntar")

    def test_alvo_depois_de_substituicao(self):
        self.assertEqual(self.bash("rm $(true) " + SETTINGS), "perguntar")
        self.assertEqual(self.bash("rm$(true) " + SETTINGS), "perguntar")

    def test_codigo_pergunta_no_perfil_e_no_settings(self):
        for alvo in ("-r .tune-up", SETTINGS):
            for c in self.ESCONDIDOS:
                with self.subTest(c=c, alvo=alvo):
                    self.assertEqual(self.bash(c % alvo), "perguntar")

    def test_comum_segue_passando(self):
        comuns = ["printf $'a\\nb'", "IFS=$'\\n' read -r x", "echo $'a b' && ls", "grep -c $'\\t' docs/x.md",
                  "ls # it's fine", 'echo "it\'s $(date)" ; ls', "cat <<EOF\ntotal: $(wc -l < app.py)\nEOF",
                  "cat <<'EOF'\nrm -rf / and $(rm app.py) and it's\nEOF", "echo \"$(git status --short | head -3)\"",
                  "git log --oneline \\\n  -3", "echo $((1<<2))", "wsl ls", "echo `date`",
                  "gh pr view 1 --json body -q \"$(cat <<'EOF'\nit's guarda.py trust ~/.claude/settings.json\nEOF\n)\""]
        for campos in ({}, {"modo_pesquisa": True}, {"modo_conversa": True, "modo_pesquisa": True}):
            self.sessao(**campos)
            for c in comuns:
                with self.subTest(c=c, campos=campos):
                    self.assertIsNone(self.bash(c))


PECAS = ["$'\\''", "$'", "'", '"', "\\'", '\\"', "\\\\", " ; MARK ; ", " MARK ", "\n", " # it's ", "#", " ", "echo ", ": ",
         "$'a\\\\'", "$'\\x27'", "$'\\047'", "<<EOF\n", "<<'E'\n", "EOF\n", "E\n", "$(", ")", "`", "$\"", "${x#", "}", "((",
         "))", "$((1<<2", "a[1<<2]=3\n", "2\n", "$'\\n'", "<<-X\n", "\tX\n", "\\\n", "\\$", "$'\\c'", "$[1<<2]\n", "<<<x ",
         "x", "|", "&&", "$'\\u0027'", "<<\\Q\n", "Q\n", "bash -c ", "eval ", "\"$(", "\"$( MARK )\"", "\"`MARK`\"",
         "$( MARK )\n", "case x in x) ", ";; esac", "\"a\\\"b\"", "<<EOF\n$( MARK )\nEOF\n", "<<'EOF'\n$( MARK )\nEOF\n",
         "\\`", "$(( 1 + ", "MARK", ")#", "$(true)#", "\"$(echo case)\"", "case", "\"${x#'\"'}\"", "<<$(x)\n", "$(x)\n",
         "${x:-'}", ": \\'\n", "<(", "$\"E\"", "then ", "{ ", "}\n",
         "$(true) ", "if ", "do ", "[[ x =~ (#) ]] ", "(#", "@(", " E\n", "#'", "\"`", "`\"", "\\\"", "x${y}", "x) ", "esac )"]


@unittest.skipUnless(BASH, "needs a real bash to compare with")
class TestContraOBash(unittest.TestCase):
    """Random text built from the pieces that confuse a tokenizer, run by the real Bash with MARK
    as a harmless function: whenever Bash runs MARK, the guard's reading must show a MARK command."""

    def test_o_que_o_bash_roda_a_guarda_ve(self):
        rnd = random.Random(20261117)
        tmp = tempfile.mkdtemp(prefix="tuneup-fuzz-")
        self.addCleanup(shutil.rmtree, tmp, True)
        conta, rodou = os.path.join(tmp, "c"), 0
        for _ in range(500):
            cmd = "".join(rnd.choice(PECAS) for _ in range(rnd.randint(2, 12)))
            open(conta, "w").close()
            script = "MARK() { echo x >> '%s'; }\nexport -f MARK\n%s\n" % (conta, cmd)
            try:
                subprocess.run([BASH, "--norc", "--noprofile", "-c", script], cwd=tmp, stdin=subprocess.DEVNULL,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=10,
                               env={"PATH": "/nonexistent", "HOME": tmp})
            except subprocess.TimeoutExpired:
                continue
            if os.path.getsize(conta):
                rodou += 1
                # `"$x"MARK` is a command word the guard cannot resolve: MARK inside the word counts
                self.assertTrue(any("MARK" in e for e in exes(cmd)), "Bash ran MARK, the guard does not see it: %r" % cmd)
        self.assertGreater(rodou, 30)


if __name__ == "__main__":
    unittest.main()
