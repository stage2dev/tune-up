"""Teto de tempo de uma execução, campos da ação no catálogo.

`max_minutos`: minutos desde que a sessão começou (ou desde a última resposta pelo painel).
`max_bloqueado_min`: minutos parada esperando você (estado precisa_de_voce).
Passou: o painel roda `claude stop`, marca `falha` no registro e a vaga do teto de execuções fica livre.
Quem confere é `Lancador.execucoes` (a tela, um disparo novo) e a vigia abaixo, que roda sem a tela aberta.
"""
import sys
import threading

CAMPOS = ("max_minutos", "max_bloqueado_min")
SEMPRE = ("bloqueada_ts", "falha", "parada_pelo_painel")  # gravados mesmo se o registro já tem valor
MAX = 24 * 60
PAUSA = 30  # s entre olhadas da vigia
ATIVOS = ("rodando", "precisa_de_voce")


def validar(a):
    """{max_minutos, max_bloqueado_min}: inteiro de 1 a MAX ou None. Levanta ValueError."""
    out = {}
    for campo in CAMPOS:
        v = a.get(campo)
        if v is not None and (isinstance(v, bool) or not isinstance(v, int) or not 1 <= v <= MAX):
            raise ValueError("ação %s: %s precisa ser um inteiro de 1 a %d" % (a["id"], campo, MAX))
        out[campo] = v
    return out


def tem_teto(reg):
    return any(reg.get(c) for c in CAMPOS)


def _passou(reg, estado, agora):
    if estado not in ATIVOS or reg.get("falha"):
        return None
    inicio = max(float(reg.get("iniciada_ts") or 0), float(reg.get("respondida_ts") or 0))
    if reg.get("max_minutos") and agora - inicio >= reg["max_minutos"] * 60:
        return "max_minutos"
    desde = float(reg.get("bloqueada_ts") or 0)
    if estado == "precisa_de_voce" and desde and reg.get("max_bloqueado_min") \
            and agora - desde >= reg["max_bloqueado_min"] * 60:
        return "max_bloqueado_min"
    return None


def conferir(reg, estado, agora, parar):
    """Campos a gravar no registro ({} = nada muda). `parar(id)` roda `claude stop` e diz se deu certo."""
    campos = {}
    if reg.get("max_bloqueado_min"):  # desde quando espera você; zera quando volta a andar
        if estado == "precisa_de_voce" and not reg.get("bloqueada_ts"):
            campos["bloqueada_ts"] = agora
        elif estado != "precisa_de_voce" and reg.get("bloqueada_ts"):
            campos["bloqueada_ts"] = 0
    motivo = _passou(dict(reg, **campos), estado, agora)
    if motivo and parar(reg["id"]):  # stop que falhou: fica sem marca e tenta na próxima olhada
        campos.update(falha=motivo, parada_pelo_painel=True)
    return campos


def uma_volta(lanc):
    """Só chama `claude agents` se há execução com teto que ainda pode estar ativa."""
    ultimo = lanc._ultimo
    if any(tem_teto(r) and not r.get("falha") and ultimo.get(r["id"], "rodando") in ATIVOS
           for r in lanc.registro.ler()):
        lanc.execucoes(forcar=True)


def vigiar(lanc, parar, pausa=PAUSA):
    while not parar.wait(pausa):
        try:
            uma_volta(lanc)
        except Exception as e:  # a vigia não pode morrer; o erro fica no terminal do painel
            sys.stderr.write("painel: teto de tempo: %s\n" % type(e).__name__)


def iniciar_vigia(lanc, pausa=PAUSA):
    parar = threading.Event()
    threading.Thread(target=vigiar, args=(lanc, parar, pausa), name="teto", daemon=True).start()
    return parar
