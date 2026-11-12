"""Mídia recebida (áudio, imagem, documento do lead): o recebimento grava a linha em `midias` (estado pendente) na
mesma transação da mensagem; DEPOIS do commit a linha entra numa fila curta e um único trabalhador baixa pelo
conector, sem transação aberta e sem segurar a resposta do webhook.

- Tetos: áudio 16 MB, imagem 10 MB, documento 20 MB; acima disso nada é gravado (falhou, grande_demais).
- O tipo vem do conteúdo (bytes mágicos), nunca do declarado: áudio ogg/opus, mp3, m4a/aac, wav; imagem jpeg, png,
  webp; documento pdf ou application/octet-stream (com o nome original limpo). Áudio/imagem que não casa = recusado.
- Arquivo em <pasta de dados>/midia/<conversa>/<nome aleatório> (pastas 0700, arquivo 0600, escrita atômica),
  nunca dentro do projeto. A rota só acha o arquivo pelo id inteiro da linha.
- Retenção: arquivo com mais de `midia_dias` (30) dias sai na subida e uma vez por dia; teto total `midia_teto_bytes`
  (2 GB): o mais antigo sai primeiro. A linha fica, com estado expirada.
- Falha não volta sozinha: só o dono pede de novo (POST /midia/<id>/baixar-de-novo). Pendente na subida = interrompida.
  Webhook sem segredo: nenhuma chave guardada e nada a pedir de novo. A mesma ação limpa `falha_ia` de uma pronta (a IA
  tenta de novo). Na subida, `.tmp` e arquivo sem linha em `midias` saem da pasta.
- O trabalhador sobrevive a erro (banco ocupado inclusive) e só avisa o tipo; morto, enfileirar o sobe de novo.
Nenhum nome de arquivo, telefone ou conteúdo vai para log."""
import datetime
import hashlib
import json
import math
import os
import queue
import re
import secrets
import shutil
import subprocess
import sys
import threading
import time

from servico import banco
from servico.conectores import base

PASTA = "midia"
MB = 1024 * 1024
LIMITES = {"audio": 16 * MB, "imagem": 10 * MB, "documento": 20 * MB}
DIAS_PADRAO = 30
TETO_PADRAO = 2 * 1024 * MB
FILA_MAX = 64
DIA_S = 24 * 3600
NOME_MAX = 100
ARQUIVO = re.compile(r"^(\d{1,12})/([0-9a-f]{32})$")
UTC = datetime.timezone.utc

_baixador = None


def detectar(tipo, dados):
    """Mimetype pelo conteúdo, dentro da lista do tipo; None = recusado."""
    cabeca = bytes(dados[:16])
    if tipo == "audio":
        if cabeca.startswith(b"OggS"):
            return "audio/ogg"
        if cabeca.startswith(b"ID3"):
            return "audio/mpeg"
        if cabeca[4:8] == b"ftyp":
            return "audio/mp4"
        if cabeca[:4] == b"RIFF" and cabeca[8:12] == b"WAVE":
            return "audio/wav"
        if len(cabeca) > 1 and cabeca[0] == 0xFF:
            if cabeca[1] & 0xF6 == 0xF0:   # ADTS: sincronismo de 12 bits e camada 00
                return "audio/aac"
            if cabeca[1] & 0xE0 == 0xE0 and cabeca[1] & 0x06:   # quadro MPEG de áudio, camada I a III
                return "audio/mpeg"
        return None
    if tipo == "imagem":
        if cabeca.startswith(b"\xff\xd8\xff"):
            return "image/jpeg"
        if cabeca.startswith(b"\x89PNG\r\n\x1a\n"):
            return "image/png"
        if cabeca[:4] == b"RIFF" and cabeca[8:12] == b"WEBP":
            return "image/webp"
        return None
    if tipo == "documento":
        return "application/pdf" if cabeca.startswith(b"%PDF-") else "application/octet-stream"
    return None


def nome_seguro(nome):
    """Só o nome (sem pasta), sem caracteres de controle nem separadores, até NOME_MAX; vazio = "documento"."""
    if not isinstance(nome, str):
        return "documento"
    nome = re.split(r"[\\/]", nome)[-1]
    limpo = "".join(c for c in nome if c.isprintable() and c not in '<>:"|?*').strip(" .")
    return limpo[-NOME_MAX:] if limpo else "documento"


def registrar(con, mensagem_id, tipo, chave, confiavel=True):
    """Dentro da transação do recebimento. Devolve o id; só a pendente vai para a fila (depois do commit)."""
    estado, motivo = "pendente", None
    if not confiavel:
        estado, motivo = "falhou", "sem_segredo"   # webhook forjado: nem a chave fica (nada a pedir de novo)
    guardada = json.dumps(chave) if confiavel and isinstance(chave, dict) else None
    cur = con.execute("INSERT INTO midias (mensagem_id, tipo, chave, estado, motivo, criado_em) VALUES (?, ?, ?, ?, ?, ?)",
                      (mensagem_id, tipo, guardada, estado, motivo, banco.agora()))
    banco._exigir(cur)
    return cur.lastrowid


def registrar_baixador(baixador):
    global _baixador
    _baixador = baixador


def enfileirar(con, midia_id):
    """Depois do commit. Sem trabalhador, a linha fica pendente (a próxima subida marca interrompida). Trabalhador
    morto que não sobe de novo (serviço parando) = falhou (sem_baixador). Fila cheia = falhou (fila_cheia)."""
    if _baixador is None:
        return False
    if not _baixador.garantir():
        _falhar(con, midia_id, "sem_baixador")
        return False
    try:
        _baixador.fila.put_nowait(midia_id)
        return True
    except queue.Full:
        _falhar(con, midia_id, "fila_cheia")
        return False


def _falhar(con, midia_id, motivo):
    con.execute("UPDATE midias SET estado = 'falhou', motivo = ? WHERE id = ? AND estado = 'pendente'",
                (motivo, midia_id))
    return "falhou"


def _avisar(onde, erro):
    print("vendas: mídia: %s falhou: %s" % (onde, type(erro).__name__), file=sys.stderr)


def raiz(pasta_dados):
    return os.path.join(pasta_dados, PASTA)


def _criar_pasta(caminho):
    os.makedirs(caminho, mode=0o700, exist_ok=True)
    if os.name != "nt":
        os.chmod(caminho, 0o700)


def gravar_arquivo(pasta_dados, conversa_id, dados):
    """Escrita atômica (temporário 0600 + os.replace). Devolve o relativo "<conversa>/<nome>"."""
    _criar_pasta(raiz(pasta_dados))
    pasta = os.path.join(raiz(pasta_dados), str(int(conversa_id)))
    _criar_pasta(pasta)
    nome = secrets.token_hex(16)
    final = os.path.join(pasta, nome)
    temporario = final + ".tmp"
    fd = os.open(temporario, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_BINARY", 0), 0o600)
    try:
        with os.fdopen(fd, "wb") as arquivo:
            arquivo.write(dados)
            arquivo.flush()
            os.fsync(arquivo.fileno())
        if os.name != "nt":
            os.chmod(temporario, 0o600)
        os.replace(temporario, final)
    except BaseException:
        try:
            os.remove(temporario)
        except OSError:
            pass
        raise
    return "%d/%s" % (int(conversa_id), nome)


def caminho_do_arquivo(pasta_dados, relativo):
    """Caminho absoluto do arquivo guardado na linha, ou None se o valor não tem o formato ou sai da pasta."""
    achou = ARQUIVO.match(relativo or "")
    if not achou:
        return None
    base_real = os.path.realpath(raiz(pasta_dados))
    alvo = os.path.realpath(os.path.join(base_real, achou.group(1), achou.group(2)))
    return alvo if alvo.startswith(base_real + os.sep) else None


FORMATO_FFPROBE = {"audio/ogg": "ogg", "audio/mpeg": "mp3", "audio/mp4": "mp4", "audio/wav": "wav", "audio/aac": "aac"}


def duracao(caminho, mimetype=None):
    """Segundos (uma casa) pelo ffprobe quando instalado; senão (ou erro) None. O formato detectado vai em -f: o
    ffprobe não sonda o conteúdo do lead livremente; formato fora da lista = None, sem rodar."""
    exe = shutil.which("ffprobe")
    formato = FORMATO_FFPROBE.get(mimetype)
    if not exe or not formato:
        return None
    try:
        r = subprocess.run([exe, "-v", "error", "-f", formato, "-show_entries", "format=duration", "-of",
                            "default=noprint_wrappers=1:nokey=1", caminho], stdout=subprocess.PIPE,
                           stderr=subprocess.DEVNULL, timeout=15, check=False)
        valor = float(r.stdout.decode("ascii", "replace").strip())
    except (OSError, ValueError, subprocess.SubprocessError):
        return None
    return round(valor, 1) if math.isfinite(valor) and valor >= 0 else None


def baixar(abrir, conector, pasta_dados, midia_id):
    """Baixa uma pendente. Nenhuma transação fica aberta durante a chamada ao conector. Devolve o estado final, ou
    None se a linha não estava pendente (outro já cuidou)."""
    con = abrir()
    try:
        linha = con.execute("SELECT d.tipo, d.chave, d.estado, m.conversa_id FROM midias d JOIN mensagens m "
                            "ON m.id = d.mensagem_id WHERE d.id = ?", (midia_id,)).fetchone()
        if linha is None or linha["estado"] != "pendente":
            return None
        instancia = banco.ler_config(con, "instancia")
        if conector is None or not instancia:
            return _falhar(con, midia_id, "sem_conector")
        try:
            chave = json.loads(linha["chave"]) if linha["chave"] else {}
            dados, _declarado, nome = conector.baixar_midia(instancia, chave)
        except base.ErroMidia as e:
            return _falhar(con, midia_id, e.motivo)
        except Exception as e:
            _avisar("download", e)
            return _falhar(con, midia_id, "indisponivel")
        tipo = linha["tipo"]
        if not isinstance(dados, (bytes, bytearray)) or not dados:
            return _falhar(con, midia_id, "indisponivel")
        if len(dados) > LIMITES[tipo]:
            return _falhar(con, midia_id, "grande_demais")
        mimetype = detectar(tipo, dados)
        if mimetype is None:
            return _falhar(con, midia_id, "tipo_recusado")
        try:
            relativo = gravar_arquivo(pasta_dados, linha["conversa_id"], dados)
        except OSError as e:
            _avisar("gravação", e)
            return _falhar(con, midia_id, "disco")
        caminho = caminho_do_arquivo(pasta_dados, relativo)
        try:
            cur = con.execute(
                "UPDATE midias SET estado = 'pronta', motivo = NULL, mimetype = ?, bytes = ?, sha256 = ?, "
                "nome_arquivo = ?, arquivo = ?, duracao_s = ?, baixada_em = ? WHERE id = ? AND estado = 'pendente'",
                (mimetype, len(dados), hashlib.sha256(dados).hexdigest(),
                 nome_seguro(nome) if tipo == "documento" else None, relativo,
                 duracao(caminho, mimetype) if tipo == "audio" else None, banco.agora(), midia_id))
        except BaseException:   # banco ocupado, disco: o arquivo não fica sem linha
            _remover(caminho)
            raise
        if cur.rowcount != 1:   # mudou de estado enquanto baixava: o arquivo não fica órfão
            _remover(caminho)
            return None
        purgar(con, pasta_dados, so_teto=True)
        return "pronta"
    finally:
        con.close()


def entender_de_novo(con, midia_id):
    """Ação do dono numa pronta em que a IA falhou: limpa falha_ia. Devolve (conversa, última entrada confiável dela)
    -- quem chama dá a vez à IA -- ou None se não havia falha da IA. Se já saiu mensagem depois da mídia (o dono
    respondeu), a entrada volta None: a IA não responde agora com um contexto que não viu essa resposta."""
    cur = con.execute("UPDATE midias SET falha_ia = NULL WHERE id = ? AND estado = 'pronta' AND falha_ia IS NOT NULL",
                      (midia_id,))
    if cur.rowcount != 1:
        return None
    return con.execute("SELECT m.conversa_id, CASE WHEN EXISTS (SELECT 1 FROM mensagens WHERE conversa_id = "
                       "m.conversa_id AND direcao = 'saida' AND id > m.id) THEN NULL ELSE (SELECT MAX(id) FROM "
                       "mensagens WHERE conversa_id = m.conversa_id AND direcao = 'entrada' AND confiavel = 1) END "
                       "FROM midias d JOIN mensagens m ON m.id = d.mensagem_id WHERE d.id = ?", (midia_id,)).fetchone()


def pedir_de_novo(con, midia_id):
    """Ação do dono: falhou -> pendente e fila. False se não estava em falhou (inclui o clique repetido) ou se veio
    de webhook sem segredo (sem chave guardada: nada de chamar a Evolution com o que um forjador mandou)."""
    cur = con.execute("UPDATE midias SET estado = 'pendente', motivo = NULL WHERE id = ? AND estado = 'falhou' AND "
                      "chave IS NOT NULL AND COALESCE(motivo, '') <> 'sem_segredo'", (midia_id,))
    if cur.rowcount != 1:
        return False
    if _baixador is None:
        _falhar(con, midia_id, "sem_baixador")
        return False
    return enfileirar(con, midia_id)


def interrompidas(con):
    """Subida, antes de servir: pendente que sobrou de um processo anterior vira falhou (interrompida)."""
    return con.execute("UPDATE midias SET estado = 'falhou', motivo = 'interrompida' WHERE estado = 'pendente'").rowcount


def orfaos(con, pasta_dados):
    """Subida, antes do trabalhador: apaga `.tmp` de uma queda e arquivo que nenhuma linha de `midias` aponta.
    Devolve quantos saíram. Nada fora de <pasta de dados>/midia/<conversa>/ é tocado."""
    base_real = os.path.realpath(raiz(pasta_dados))
    if not os.path.isdir(base_real):
        return 0
    usados = {r[0] for r in con.execute("SELECT arquivo FROM midias WHERE arquivo IS NOT NULL")}
    n = 0
    try:
        for conversa in os.listdir(base_real):
            pasta = os.path.join(base_real, conversa)
            if not conversa.isdigit() or os.path.islink(pasta) or not os.path.isdir(pasta):
                continue
            for nome in os.listdir(pasta):
                caminho = os.path.join(pasta, nome)
                if os.path.islink(caminho) or not os.path.isfile(caminho) or "%s/%s" % (conversa, nome) in usados:
                    continue
                n += _remover(caminho)
    except OSError as e:   # a subida não cai por causa da limpeza
        _avisar("limpeza de órfãos", e)
    return n


def _remover(caminho):
    if caminho is None:
        return True
    try:
        os.remove(caminho)
    except FileNotFoundError:
        pass
    except OSError as e:   # Windows: arquivo aberto pela rota; fica para a próxima limpeza
        _avisar("limpeza", e)
        return False
    return True


def _expirar(con, pasta_dados, linha, motivo):
    if not _remover(caminho_do_arquivo(pasta_dados, linha["arquivo"])):
        return False
    return con.execute("UPDATE midias SET estado = 'expirada', motivo = ?, arquivo = NULL WHERE id = ? "
                       "AND estado = 'pronta'", (motivo, linha["id"])).rowcount == 1


def _numero(con, chave, padrao):
    try:
        valor = int(banco.ler_config(con, chave, padrao))
    except (TypeError, ValueError):
        return padrao
    return valor if valor > 0 else padrao


def purgar(con, pasta_dados, agora=None, so_teto=False):
    """Retenção (`midia_dias`) e teto total (`midia_teto_bytes`, o mais antigo sai primeiro). Devolve quantas
    expiraram."""
    n = 0
    if not so_teto:
        agora = agora or datetime.datetime.now(UTC)
        limite = (agora - datetime.timedelta(days=_numero(con, "midia_dias", DIAS_PADRAO))).astimezone(UTC)
        for linha in con.execute("SELECT id, arquivo FROM midias WHERE estado = 'pronta' AND baixada_em < ? "
                                 "ORDER BY baixada_em, id", (limite.isoformat(timespec="seconds"),)).fetchall():
            n += _expirar(con, pasta_dados, linha, "retencao")
    teto = _numero(con, "midia_teto_bytes", TETO_PADRAO)
    total = con.execute("SELECT COALESCE(SUM(bytes), 0) FROM midias WHERE estado = 'pronta'").fetchone()[0]
    if total > teto:
        for linha in con.execute("SELECT id, arquivo, bytes FROM midias WHERE estado = 'pronta' "
                                 "ORDER BY baixada_em, id").fetchall():
            if total <= teto:
                break
            if _expirar(con, pasta_dados, linha, "espaco"):
                total -= linha["bytes"] or 0
                n += 1
    return n


class Baixador:
    """Um trabalhador e uma fila limitada. `obter_conector` devolve o conector atual (ou None)."""

    def __init__(self, abrir, obter_conector, pasta_dados, fila_max=FILA_MAX):
        self.abrir = abrir
        self.obter_conector = obter_conector
        self.pasta_dados = pasta_dados
        self.fila = queue.Queue(fila_max)
        self._fio = self._parar = None
        self._trava = threading.Lock()

    def iniciar(self, parar):
        with self._trava:
            self._parar = parar
            self._fio = threading.Thread(target=self._rodar, args=(parar,), daemon=True)
            self._fio.start()
            return self._fio

    def garantir(self):
        """O trabalhador está vivo (ou nem foi ligado: quem usa a fila sem thread)? Morto = sobe outro, salvo se o
        serviço está parando (False)."""
        with self._trava:
            if self._fio is None or self._fio.is_alive():
                return True
            if self._parar.is_set():
                return False
            _avisar("trabalhador", RuntimeError("thread morta, subindo outra"))
            self._fio = threading.Thread(target=self._rodar, args=(self._parar,), daemon=True)
            self._fio.start()
            return True

    def _limpar(self):
        try:
            con = self.abrir()   # banco ocupado aqui não derruba o trabalhador
        except Exception as e:
            _avisar("retenção", e)
            return
        try:
            purgar(con, self.pasta_dados)
        except Exception as e:
            _avisar("retenção", e)
        finally:
            con.close()

    def _rodar(self, parar):
        ultima = None
        while not parar.is_set():
            try:
                if ultima is None or time.monotonic() - ultima >= DIA_S:
                    ultima = time.monotonic()
                    self._limpar()
                self._um(parar)
            except Exception as e:   # nada derruba o laço: o tipo vai para o log
                _avisar("trabalhador", e)
                parar.wait(0.5)

    def _um(self, parar):
        try:
            midia_id = self.fila.get(timeout=0.5)
        except queue.Empty:
            return
        try:
            baixar(self.abrir, self.obter_conector(), self.pasta_dados, midia_id)
        except Exception as e:   # a linha não pode ficar pendente para sempre
            _avisar("trabalhador", e)
            try:
                con = self.abrir()
                try:
                    _falhar(con, midia_id, "erro")
                finally:
                    con.close()
            except Exception as e2:
                _avisar("trabalhador", e2)
