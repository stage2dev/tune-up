"""Agendador de campanha: uma thread do serviço pega o próximo contato vencido e envia SÓ pelo portão, origem
'campanha' fixa. Janela, tetos (8/min, 200/h, aquecimento de NOVOS por dia), opt-out e dedupe são do portão, dentro
da reserva; aqui ficam o jitter entre envios e as esperas. Nenhuma transação de escrita fica aberta durante a chamada
ao conector (o portão grava 'pendente', chama, fecha). Reiniciar no meio não duplica: a chave campanha+contato+passo
já ocupada volta 'duplicado' e o contato fica com o estado do envio. 'incerto' nunca é reenviado daqui; 'falhou'
(prova de que não saiu) volta depois de ESPERA_FALHA_S pelo portao.reenviar, que reconfere as regras na reserva,
até campanha.TENTATIVAS_FALHOU vezes; número inexistente (numero_invalido) nunca volta."""
import datetime
import random
import sys
import threading

from servico import banco, campanha, modelo, portao, telefone

UTC = datetime.timezone.utc
JITTER = (1.2, 4.0, 12.0)            # mínimo, média, máximo em segundos
OCIOSO_S = 5.0                       # nada vencido: olha de novo
SEM_CONECTOR_S = 30.0
ERRO_S = 30.0
ESPERA_FALHA_S = 60.0                # 'falhou': o contato volta à fila depois disso
ESPERA_TETO = {"teto_minuto": 20.0, "teto_hora": 300.0, "fuso_invalido": 600.0}   # tetos do número todo


def jitter(aleatorio):
    """Espera aleatória entre envios: exponencial deslocada (média ~4 s), presa entre 1,2 s e 12 s."""
    minimo, media, maximo = JITTER
    return min(maximo, minimo + aleatorio.expovariate(1.0 / (media - minimo)))


def _iso(momento):
    return momento.astimezone(UTC).isoformat(timespec="seconds")


def proxima_janela(con, agora):
    """Próximas 09:00 no fuso do projeto (hoje, se ainda não deu; senão amanhã)."""
    tz = portao.fuso(con)
    if tz is None:
        return agora + datetime.timedelta(seconds=ESPERA_TETO["fuso_invalido"])
    local = agora.astimezone(tz)
    abre = local.replace(hour=portao.JANELA[0], minute=0, second=0, microsecond=0)
    if local >= abre:
        abre += datetime.timedelta(days=1)
    return abre


class Agendador:
    """`abrir()` devolve conexão nova do banco; `obter_conector()` o conector atual (ou None). `relogio` e
    `aleatorio` são injetáveis para os testes. `passo()` faz uma volta e devolve quantos segundos esperar."""

    def __init__(self, abrir, obter_conector, relogio=None, aleatorio=None, permitidos=None):
        self.abrir = abrir
        self.obter_conector = obter_conector
        self.permitidos = permitidos or (lambda: [])   # URLs do links.json do projeto
        self.relogio = relogio or (lambda: datetime.datetime.now(UTC))
        self.aleatorio = aleatorio or random.Random()
        self.esperar_ate = None     # teto do número todo (minuto, hora, janela): ninguém sai antes disso
        self.novos_ate = None       # acabou o teto de NOVOS do dia: até lá, só quem já recebeu algo
        self.thread = None

    def _espera(self, agora):
        return max(0.0, (self.esperar_ate - agora).total_seconds()) if self.esperar_ate else 0.0

    def passo(self):
        agora = self.relogio()
        if self.esperar_ate and agora < self.esperar_ate:
            return self._espera(agora)
        self.esperar_ate = None
        con = self.abrir()
        try:
            return self._passo(con, agora)
        finally:
            con.close()

    def _passo(self, con, agora):
        conector, instancia = self.obter_conector(), banco.ler_config(con, "instancia")
        if conector is None or not instancia:
            return SEM_CONECTOR_S
        campanha.concluir_prontas(con)
        linha = campanha.proximo(con, _iso(agora), so_conhecidos=bool(self.novos_ate and agora < self.novos_ate),
                                 instancia=instancia)
        if linha is None:
            return OCIOSO_S
        if banco.ler_config(con, "numero_descartavel") != "1" and campanha.fria(con, linha["contato_id"]):
            campanha.pausar_por(con, linha["campanha_id"], "sem_numero_descartavel")   # a trava vale também no envio
            return OCIOSO_S
        try:
            r = self._enviar(con, conector, instancia, linha, agora)
        except telefone.TelefoneInvalido:
            r = {"estado": "negado", "envio_id": None, "motivo": "numero_invalido"}
        except Exception as e:   # banco ou portão: conta como falha e tenta depois (a chave segura o duplicado)
            print("vendas: agendador: envio de campanha falhou: %s" % type(e).__name__, file=sys.stderr)
            campanha.contar_falha(con, linha["campanha_id"], "erro_inesperado:%s" % type(e).__name__)
            return ERRO_S
        return self._depois(con, agora, linha, r)

    def _enviar(self, con, conector, instancia, linha, agora):
        """Contato com envio 'falhou' tenta de novo a MESMA linha (sem chave nova); senão, envio novo de campanha."""
        anterior = linha["envio_id"] and con.execute("SELECT estado FROM envios WHERE id = ?",
                                                     (linha["envio_id"],)).fetchone()
        if not anterior or anterior["estado"] != "falhou":
            texto, motivo = modelo.renderizar(linha["modelo"], linha["nome"], linha["origem"],
                                              banco.ler_config(con, "empresa"), self.permitidos())
            if texto is None:
                return {"estado": "pulado", "envio_id": None, "motivo": motivo}
            return portao.enviar_campanha(con, conector, instancia, linha["telefone"], texto,
                                          linha["campanha_id"], linha["passo"], agora=agora)
        r = portao.reenviar(con, conector, instancia, linha["envio_id"], agora=agora)
        if r["motivo"] == "nao_reenviavel":   # a linha mudou no meio: vale o que ela diz agora
            r = dict(r, estado="duplicado")
        return r

    def _depois(self, con, agora, linha, r):
        """Grava o resultado e decide a espera. Teto do número todo = espera global sem marcar o contato."""
        if r["estado"] == "pulado" and r["motivo"] in modelo.DA_CAMPANHA:   # modelo, empresa ou links.json
            campanha.pausar_por(con, linha["campanha_id"], r["motivo"])
            print("vendas: agendador: campanha pausada: %s" % r["motivo"], file=sys.stderr)
            return OCIOSO_S
        if r["estado"] == "pulado":   # só o valor deste contato (sem nome/origem, chave ou link no valor, longo)
            campanha.pular(con, linha, r["motivo"])
            return 0.0
        motivo = r.get("motivo") if r["estado"] == "negado" else None
        tentar = _iso(agora + datetime.timedelta(seconds=ESPERA_FALHA_S)) if r["estado"] == "falhou" else None
        if motivo == "fora_da_janela":
            self.esperar_ate = proxima_janela(con, agora)
        elif motivo in ESPERA_TETO:
            self.esperar_ate = agora + datetime.timedelta(seconds=ESPERA_TETO[motivo])
        elif motivo and motivo not in campanha.PERMANENTES:
            # teto de NOVOS, pausa humana: este contato só na próxima abertura da janela (dentro dela = amanhã)
            amanha = proxima_janela(con, agora)
            tentar = _iso(amanha)
            if motivo == "teto_contatos_novos_dia":
                self.novos_ate = amanha
        campanha.registrar(con, linha, r, tentar)
        if r["estado"] in ("enviado", "incerto", "falhou"):
            return jitter(self.aleatorio)   # o conector foi chamado: espera aleatória antes do próximo
        return self._espera(agora)

    def rodar(self, parar):
        """Laço da thread: uma volta, espera (acorda na hora se `parar` for ligado) e repete até parar."""
        while not parar.is_set():
            try:
                espera = self.passo()
            except Exception as e:   # nunca derruba a thread; o banco pode voltar
                print("vendas: agendador: volta falhou: %s" % type(e).__name__, file=sys.stderr)
                espera = ERRO_S
            parar.wait(espera)

    def iniciar(self, parar):
        self.thread = threading.Thread(target=self.rodar, args=(parar,), name="agendador", daemon=True)
        self.thread.start()
        return self.thread
