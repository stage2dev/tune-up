"""Estado de uma execução do painel a partir da linha de `claude agents --json --all`."""

OCIOSO = 180        # s sem escrita na conversa (nem nos subagentes) com o CLI em "idle": parou de trabalhar
GRACA = 45          # s: sessão recém-disparada ainda pode não aparecer em `claude agents`


def mapear_estado(reg, agente, agora, ocioso_ha=None):
    """Cruza o registro com uma linha de `claude agents --json --all`.

    Medido no CLI 2.1.322: recém-disparada state=working (status some, depois busy);
    pergunta pendente state=blocked + status=waiting; terminou state=done + status=idle
    (processo vivo) ou só state=done (depois de stop); parada no meio state=stopped;
    depois de `claude rm` a linha some.
    """
    if agente is None:
        if reg.get("terminou_em"):  # já tinha terminado; depois foi apagada (`claude rm`)
            return "terminou"
        if reg.get("parada_pelo_painel"):
            return "parada"
        return "rodando" if agora - float(reg.get("iniciada_ts") or 0) < GRACA else "sumiu"
    state = str(agente.get("state") or "").lower()
    status = str(agente.get("status") or "").lower()
    if state == "blocked" or status == "waiting":
        return "precisa_de_voce"
    if status == "busy":
        return "rodando"
    if state in ("working", "running", "busy", "active"):
        # Medido no 2.1.322: o CLI deixa state=working + status=idle por minutos depois de a
        # sessão responder. Sem escrita na conversa nem nos subagentes há OCIOSO s, parou.
        if status == "idle" and ocioso_ha is not None and ocioso_ha > OCIOSO:
            return "terminou"
        return "rodando"
    if state in ("done", "completed", "finished"):
        return "terminou"
    if state in ("stopped", "killed", "failed", "error", "exited"):
        return "parada"
    return "terminou" if status == "idle" else "rodando"
