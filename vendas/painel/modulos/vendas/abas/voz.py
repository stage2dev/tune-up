"""Aba Voz: estado da voz (ffmpeg, chave da ElevenLabs, voz escolhida, caracteres de hoje), chave (campo segredo,
trocar e apagar com confirmação), seleção da voz pela lista da conta (lista lenta ou fora do ar = voice_id digitado),
voz clonada só liga com o consentimento do dono da voz, teto diário e o botão de áudio de teste. O teste vai SÓ para o
número do dono: esta aba nunca manda número ao serviço. A tela só vê 'configurada' e os 4 últimos caracteres; nenhuma
mensagem de ação ecoa a chave."""
import datetime
import secrets

ACOES = ("voz_chave", "voz_apagar_chave", "voz_config", "voz_consentimento", "voz_teste")
TEMPO_VOZES_S = 12  # o serviço espera a ElevenLabs até 6 s, uma tentativa só
SEM_LISTA = "Lista de vozes indisponível: digite o voice_id da voz."
AVISO_CLONADA = ("Todo áudio com voz clonada começa com o aviso falado \"Mensagem de voz gerada por IA.\" e esse "
                 "aviso não tem como ser desligado: é exigência da política da ElevenLabs para vozes clonadas. "
                 "A voz de catálogo da sua conta é a padrão e não leva o aviso. Voz clonada só liga depois do "
                 "consentimento do dono da voz.")
CONSENTIMENTO = ("Eu autorizo o uso da minha voz clonada para atendimento e vendas por mensagens de voz no "
                 "WhatsApp, sabendo que cada áudio começa com o aviso de que foi gerado por IA.")
MOTIVOS = {"sem_numero_do_dono": "Informe o seu número (campo \"Seu número\") e salve a voz antes do teste.",
           "nao_e_o_dono": "O teste só vai para o número do dono.",
           "numero_invalido": "O número do dono é inválido. Corrija e salve a voz."}


def _erro(codigo, r, padrao):
    return str((r if isinstance(r, dict) else {}).get("erro") or padrao % codigo)


def ler(ctx, cliente, base=None):
    """(estado, vozes ou None, aviso). Recusa e falha viram aviso, nunca exceção."""
    try:
        codigo, r = cliente.chamar(ctx, "GET", "/voz", base=base)
        if codigo != 200 or not isinstance(r, dict):
            return None, None, _erro(codigo, r, "O serviço recusou (%d).")
        if not (r.get("chave") or {}).get("configurada"):
            return r, None, None
    except cliente.Recusa as e:
        return None, None, str(e)
    try:   # lista lenta ou fora do ar não derruba a aba: chave, apagar e o voice_id digitado continuam
        codigo, m = cliente.chamar(ctx, "GET", "/voz/vozes", base=base, tempo=TEMPO_VOZES_S)
    except cliente.Recusa:
        return r, None, SEM_LISTA
    if codigo == 200 and isinstance(m, dict) and isinstance(m.get("vozes"), list) and m["vozes"]:
        return r, [v for v in m["vozes"] if isinstance(v, dict) and v.get("voice_id")], None
    motivo = (m or {}).get("codigo") if isinstance(m, dict) else None
    return r, None, "Não consegui a lista de vozes da conta%s. Digite o voice_id da voz." % (
        " (%s)" % motivo if motivo else "")


def _campo_voz(estado, vozes):
    atual = estado.get("voz_id") or ""
    if not vozes:
        return {"id": "voz_id", "rotulo": "voice_id da voz", "tipo": "texto", "valor": atual, "obrigatorio": True,
                "ajuda": "Letras e números (8 a 64), como aparece na sua conta ElevenLabs."}
    opcoes = [{"valor": v["voice_id"], "rotulo": "%s%s" % (v.get("nome") or v["voice_id"],
                                                           " (%s)" % v["categoria"] if v.get("categoria") else "")}
              for v in vozes]
    if atual and atual not in [o["valor"] for o in opcoes]:   # salvar outro campo nunca troca a voz escondida
        opcoes.insert(0, {"valor": atual, "rotulo": "%s (fora da lista da conta)" % atual})
    return {"id": "voz_id", "rotulo": "Voz", "tipo": "escolha", "opcoes": opcoes, "obrigatorio": True,
            "valor": atual or opcoes[0]["valor"], "ajuda": "Vozes da sua conta ElevenLabs."}


def blocos(estado, vozes, aviso, hoje=None):
    if estado is None:
        return [{"tipo": "texto", "titulo": "Voz indisponível", "texto": aviso or "O serviço não respondeu."}]
    k = estado.get("chave") or {}
    cons = estado.get("consentimento")
    clonada = bool(estado.get("clonada"))
    itens = [{"rotulo": "ffmpeg", "valor": "encontrado" if estado.get("ffmpeg") else "não encontrado",
              "tom": "bom" if estado.get("ffmpeg") else "atencao"},
             {"rotulo": "Chave da ElevenLabs", "valor": "configurada (****%s)" % k.get("final") if k.get("configurada")
              else "não configurada", "tom": "bom" if k.get("configurada") else "atencao"},
             {"rotulo": "Voz", "valor": ("%s (%s)" % (estado["voz_id"], "clonada" if clonada else "catálogo"))
              if estado.get("voz_id") else "não escolhida", "tom": "neutro" if estado.get("voz_id") else "atencao"}]
    if clonada:
        itens.append({"rotulo": "Consentimento", "valor": "%s, %s" % (cons["nome"], cons["data"]) if cons
                      else "faltando: a voz clonada não liga", "tom": "bom" if cons else "atencao"})
    itens += [{"rotulo": "Caracteres hoje", "valor": "%d de %d" % (estado.get("usados_hoje") or 0,
                                                                 estado.get("teto_caracteres_dia") or 0)},
              {"rotulo": "Seu número (teste)", "valor": "configurado" if estado.get("dono_configurado")
               else "não configurado", "tom": "bom" if estado.get("dono_configurado") else "atencao"}]
    saida = [{"tipo": "kpis", "titulo": "Voz do atendimento", "itens": itens}]
    if estado.get("ligada"):
        saida.append({"tipo": "texto", "titulo": "Voz ligada", "texto": "A voz está pronta para o teste de áudio."})
    else:
        saida.append({"tipo": "texto", "titulo": "Voz desligada", "texto": "\n".join(estado.get("avisos") or [
            "A voz está desligada."])})
    saida.append({"tipo": "texto", "titulo": "Voz clonada e aviso de IA", "texto": AVISO_CLONADA})
    if aviso:
        saida.append({"tipo": "texto", "titulo": "Lista de vozes", "texto": aviso})
    saida.append({"tipo": "formulario", "id": "voz_chave", "titulo": "Trocar a chave da ElevenLabs" if k.get(
        "configurada") else "Colar a chave da ElevenLabs",
        "descricao": "A chave vai para o serviço e fica só num arquivo protegido na pasta de dados, fora do "
                     "projeto. Depois a tela mostra só os 4 últimos caracteres.",
        "acao": "voz_chave", "botao": "Trocar chave" if k.get("configurada") else "Salvar chave",
        "campos": [{"id": "chave", "rotulo": "Chave da ElevenLabs", "tipo": "segredo", "obrigatorio": True}]})
    saida.append({"tipo": "formulario", "id": "voz_config", "titulo": "Voz, número e teto diário",
                  "descricao": "A voz de catálogo é a padrão. Marque \"clonada\" só se a voz foi clonada de uma "
                               "pessoa: ela só liga com o consentimento abaixo. O teto conta os caracteres falados "
                               "por dia (inclui o aviso de IA); no teto, nada é gerado.",
                  "acao": "voz_config", "botao": "Salvar voz", "campos": [
                      _campo_voz(estado, vozes),
                      {"id": "clonada", "rotulo": "Esta voz é clonada de uma pessoa", "tipo": "escolha",
                       "valor": "sim" if clonada else "nao", "obrigatorio": True,
                       "opcoes": [{"valor": "nao", "rotulo": "Não, é voz de catálogo"},
                                  {"valor": "sim", "rotulo": "Sim, é clonada"}]},
                      {"id": "teto_caracteres_dia", "rotulo": "Teto diário (caracteres)", "tipo": "texto",
                       "obrigatorio": True, "valor": str(estado.get("teto_caracteres_dia") or 0)},
                      {"id": "numero_dono", "rotulo": "Seu número (WhatsApp do dono)", "tipo": "texto",
                       "ajuda": "Só o teste de áudio usa. DDD + número; deixe em branco para manter o salvo."}]})
    if clonada:
        saida.append({"tipo": "formulario", "id": "voz_consentimento", "titulo": "Consentimento do dono da voz",
                      "descricao": "Vale para a voz escolhida acima. Fica gravado com a data e o texto exatos.",
                      "acao": "voz_consentimento", "botao": "Gravar consentimento", "campos": [
                          {"id": "nome", "rotulo": "Nome do dono da voz", "tipo": "texto", "obrigatorio": True},
                          {"id": "data", "rotulo": "Data (AAAA-MM-DD)", "tipo": "texto", "obrigatorio": True,
                           "valor": hoje or datetime.date.today().isoformat()},
                          {"id": "texto", "rotulo": "Texto do consentimento", "tipo": "texto_longo",
                           "obrigatorio": True, "valor": CONSENTIMENTO},
                          {"id": "confirmo", "rotulo": "O dono da voz leu e concordou com o texto acima",
                           "tipo": "escolha", "valor": "nao", "obrigatorio": True,
                           "opcoes": [{"valor": "nao", "rotulo": "Não"}, {"valor": "sim", "rotulo": "Sim, concordou"}]}]})
    saida.append({"tipo": "formulario", "id": "voz_teste", "titulo": "Áudio de teste",
                  "descricao": "Gera um áudio curto e envia para o seu número (nunca para outro). Gasta caracteres "
                               "e créditos da sua conta ElevenLabs.", "acao": "voz_teste",
                  "botao": "Enviar áudio de teste para o meu número", "campos": []})
    if k.get("configurada"):
        saida.append({"tipo": "formulario", "id": "voz_apagar_chave", "titulo": "Apagar a chave",
                      "descricao": "Sem chave a voz desliga.", "acao": "voz_apagar_chave", "botao": "Apagar chave",
                      "campos": [{"id": "confirmar", "rotulo": "Apagar mesmo a chave?", "tipo": "escolha",
                                  "valor": "nao", "obrigatorio": True,
                                  "opcoes": [{"valor": "nao", "rotulo": "Não"}, {"valor": "sim", "rotulo": "Sim, apagar"}]}]})
    return saida


def _teste(codigo, r):
    r = r if isinstance(r, dict) else {}
    if codigo == 200:
        return {"ok": True, "mensagem": "Áudio de teste enviado para o seu número."}
    if r.get("estado") == "negado":
        return {"ok": False, "mensagem": MOTIVOS.get(r.get("motivo")) or "O portão de envio negou o teste (%s)." % (
            r.get("motivo") or "sem motivo")}
    if r.get("estado") == "incerto":
        return {"ok": False, "mensagem": "Não sei se o áudio chegou. Confira o WhatsApp antes de tentar de novo."}
    return {"ok": False, "mensagem": _erro(codigo, r, "O serviço recusou o teste (%d).")}


def agir(ctx, cliente, acao, dados, base=None):
    """A chave vai só no corpo do pedido ao serviço; nenhuma mensagem devolvida a contém. O teste não leva número."""
    dados = dados or {}
    if acao == "voz_chave":
        if not isinstance(dados.get("chave"), str) or not dados["chave"].strip():
            return {"ok": False, "mensagem": "Cole a chave."}
        caminho, corpo = "/voz/chave", {"chave": dados["chave"]}
    elif acao == "voz_apagar_chave":
        if dados.get("confirmar") != "sim":
            return {"ok": False, "mensagem": "Escolha \"Sim, apagar\" para apagar a chave."}
        caminho, corpo = "/voz/chave/apagar", {"confirmar": True}
    elif acao == "voz_consentimento":
        if dados.get("confirmo") != "sim":
            return {"ok": False, "mensagem": "Sem a confirmação do dono da voz o consentimento não é gravado."}
        caminho, corpo = "/voz/consentimento", {"nome": dados.get("nome"), "data": dados.get("data"),
                                                 "texto": dados.get("texto")}
    elif acao == "voz_teste":
        caminho, corpo = "/voz/teste", {"id_tela": "tela-" + secrets.token_hex(8)}
    else:
        corpo = {"voz_id": dados.get("voz_id"), "clonada": dados.get("clonada") == "sim",
                 "teto_caracteres_dia": dados.get("teto_caracteres_dia"), "numero_dono": dados.get("numero_dono")}
        caminho = "/voz/config"
    try:
        codigo, r = cliente.chamar(ctx, "POST", caminho, corpo, base=base, tempo=cliente.TEMPO_ENVIO_S
                                   if acao == "voz_teste" else None)
    except cliente.Recusa as e:
        return {"ok": False, "mensagem": str(e)}
    if acao == "voz_teste":
        return _teste(codigo, r)
    if codigo != 200 or not isinstance(r, dict):
        return {"ok": False, "mensagem": _erro(codigo, r, "O serviço recusou (%d).")}
    if acao == "voz_chave":
        return {"ok": True, "mensagem": "Chave salva (final ****%s)." % ((r.get("chave") or {}).get("final") or "")}
    if acao == "voz_apagar_chave":
        return {"ok": True, "mensagem": "Chave apagada." if r.get("apagada") else "Não havia chave."}
    if acao == "voz_consentimento":
        return {"ok": True, "mensagem": "Consentimento de %s gravado." % (r.get("consentimento") or {}).get("nome")}
    return {"ok": True, "mensagem": "Voz salva (%s)." % ("clonada" if r.get("clonada") else "catálogo")}
