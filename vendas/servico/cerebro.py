"""Cérebro da IA de vendas: OpenAI Chat Completions com 4 ferramentas de lista fechada (guardar_dado_do_lead,
qualificar, enviar_link, pedir_humano). Nunca manda `reasoning_effort` (quebra junto com function tools).
Antes de cada chamada reserva o pior caso no teto diário (BEGIN IMMEDIATE); não cabe = não chama. Modelo sem preço
= não chama. Erro, tempo esgotado, teto, sem preço, sem chave, sem modelo ou exceção inesperada = texto None (nada a
enviar) e a conversa fica "precisa de você". Aqui nada envia: quem chama decide."""
import json
import os
import re
from urllib.parse import urlsplit

from servico import banco, chave, conhecimento, openai_cliente, precos

SUGESTAO_MODELO = "gpt-4o-mini"  # só sugestão na tela; o dono escolhe
RODADAS_MAX = 3
SAIDA_MAX = 2000  # max_completion_tokens de cada chamada: também é o pior caso da reserva
NIVEIS = ("frio", "morno", "quente")
CAMPO = re.compile(r"^[a-z_]{1,32}$")
VALOR_MAX = 500
SISTEMA = conhecimento.REGRAS  # saida.py compara o início para barrar vazamento das instruções


def caminho_links(raiz):
    """<raiz>/.tune-up/<pacote>/vendas/links.json (a pasta vem de conhecimento.pasta_vendas)."""
    return os.path.join(conhecimento.pasta_vendas(raiz), "links.json")


def ler_links(raiz):
    """{nome: url} do links.json do projeto. Ausente, vazio, inválido ou fora de .tune-up = {} (nenhum link)."""
    arquivo = caminho_links(raiz)
    if not os.path.realpath(arquivo).startswith(os.path.realpath(os.path.join(raiz, ".tune-up")) + os.sep):
        return {}
    try:
        with open(arquivo, encoding="utf-8") as f:
            dado = json.load(f)
    except (OSError, ValueError):
        return {}
    if not isinstance(dado, dict):
        return {}
    return {str(n): u for n, u in dado.items() if isinstance(u, str) and urlsplit(u).scheme in ("http", "https")
            and urlsplit(u).hostname}


def _funcao(nome, descricao, propriedades):
    return {"type": "function", "function": {"name": nome, "description": descricao, "parameters": {
        "type": "object", "properties": propriedades, "required": sorted(propriedades),
        "additionalProperties": False}}}


def ferramentas(links):
    lista = [
        _funcao("guardar_dado_do_lead", "Guarda um dado que o lead contou (ex.: nome, email, interesse).",
                {"campo": {"type": "string"}, "valor": {"type": "string"}}),
        _funcao("qualificar", "Qualifica o lead.", {"nivel": {"type": "string", "enum": list(NIVEIS)}}),
        _funcao("pedir_humano", "Pede que o dono assuma a conversa.", {"motivo": {"type": "string"}}),
    ]
    if links:  # sem links.json não há ferramenta de link (e uma chamada forçada é recusada)
        lista.append(_funcao("enviar_link", "Envia um link da lista do projeto.",
                             {"nome": {"type": "string", "enum": sorted(links)}}))
    return lista


def marcar_precisa_de_voce(con, conversa_id, motivo, desligar=False):
    """desligar=True: a IA também sai da conversa (modo humano) até o dono devolver na tela; o motivo fica guardado."""
    if desligar:
        cur = con.execute("UPDATE conversas SET precisa_de_voce = 1, modo = 'humano', motivo_humano = ? WHERE id = ?",
                          (motivo, conversa_id))
    else:
        cur = con.execute("UPDATE conversas SET precisa_de_voce = 1 WHERE id = ?", (conversa_id,))
    if cur.rowcount != 1:
        raise banco.EscritaSemEfeito("conversa %r não existe" % conversa_id)
    banco.registrar_evento(con, "ia_precisa_de_voce", json.dumps({"conversa_id": conversa_id, "motivo": motivo}))


class Cerebro:
    """base_url só vem da subida do serviço (argumento/ambiente), nunca de um pedido."""

    def __init__(self, pasta_dados, raiz, base_url=openai_cliente.URL_PADRAO, tempo=openai_cliente.TEMPO_S):
        self.pasta_dados, self.raiz, self.base, self.tempo = pasta_dados, raiz, base_url, tempo

    def responder(self, con, conversa_id, mensagens):
        """mensagens: [{"role": "user"|"assistant", "content": texto}]. Devolve {texto, links, precisa_de_voce,
        motivo, chamadas, custo_usd}. texto None = nada a enviar. Exceção inesperada = nada a enviar, IA fora da
        conversa e "precisa de você" (motivo erro_interno); só sobe se nem marcar der certo (quem chama registra)."""
        r = {"texto": None, "links": [], "precisa_de_voce": False, "motivo": None, "chamadas": 0, "custo_usd": 0.0}
        try:
            return self._responder(con, conversa_id, mensagens, r)
        except Exception:
            if con.in_transaction:
                con.execute("ROLLBACK")
            return self._parar(con, conversa_id, r, "erro_interno", True)

    def _responder(self, con, conversa_id, mensagens, r):
        segredo = chave.ler(self.pasta_dados)
        modelo = banco.ler_config(con, "ia_modelo")
        if not segredo or not modelo:
            return self._parar(con, conversa_id, r, "sem_chave" if not segredo else "sem_modelo")
        saber = conhecimento.ler(self.raiz)
        if not saber["oferta"]:   # sem oferta.md a IA não vende: nada de preço inventado
            return self._parar(con, conversa_id, r, "sem_oferta")
        par = precos.preco(precos.tabela(self.pasta_dados), modelo)
        if par is None:   # sem preço não há teto confiável: o dono informa o preço na aba IA
            return self._parar(con, conversa_id, r, "preco_desconhecido")
        links = ler_links(self.raiz)
        historico = [{"role": "system", "content": conhecimento.instrucoes(saber)}] + list(mensagens)
        for _ in range(RODADAS_MAX):
            corpo = {"model": modelo, "messages": historico, "tools": ferramentas(links), "tool_choice": "auto",
                     "max_completion_tokens": SAIDA_MAX}
            resposta, custo = self._chamar(con, segredo, par, corpo, r)
            if resposta is None:
                return self._parar(con, conversa_id, r, custo)
            try:
                msg = resposta["choices"][0]["message"]
                chamadas = msg.get("tool_calls") or []
            except (KeyError, IndexError, TypeError, AttributeError):
                msg = None
            if msg is None or not isinstance(chamadas, list):
                return self._parar(con, conversa_id, r, "resposta_invalida")
            if not chamadas:
                texto = msg.get("content")
                if not isinstance(texto, str) or not texto.strip():
                    return self._parar(con, conversa_id, r, "sem_texto")
                r["texto"] = texto.strip()
                return r
            historico.append({"role": "assistant", "content": msg.get("content"), "tool_calls": chamadas})
            for chamada in chamadas:
                saida = self._ferramenta(con, conversa_id, chamada, links, r)
                historico.append({"role": "tool", "tool_call_id": str((chamada or {}).get("id") or ""),
                                  "content": json.dumps(saida, ensure_ascii=False)})
            if r["motivo"] == "pedir_humano":   # a IA saiu da conversa: nada a enviar e nenhuma chamada a mais
                return r
        return self._parar(con, conversa_id, r, "rodadas", True)

    def _chamar(self, con, segredo, par, corpo, r):
        """Reserva o pior caso, chama e acerta pelo custo real. (resposta, custo) ou (None, motivo).
        Erro com resposta HTTP ou conexão recusada = não cobrado: libera a reserva. Tempo esgotado ou resposta
        cortada = talvez cobrado: a reserva fica. 200 sem `usage` = cobra o pior caso e vale como resposta_invalida."""
        pior = precos.pior_caso_usd(par, corpo, SAIDA_MAX)
        reserva = precos.reservar(con, pior)
        if reserva is None:
            return None, "teto_diario"
        try:
            r["chamadas"] += 1
            resposta = openai_cliente.pedir(self.base, segredo, "POST", "/v1/chat/completions", corpo, self.tempo)
        except openai_cliente.ErroOpenAI as e:
            if e.status is not None or e.recusada:
                precos.acertar(con, reserva, 0)
            else:
                r["custo_usd"] += pior
            return None, e.codigo
        custo = precos.custo_usd(par, resposta.get("usage") if isinstance(resposta, dict) else None)
        precos.acertar(con, reserva, pior if custo is None else custo)
        r["custo_usd"] += pior if custo is None else custo
        return (None, "resposta_invalida") if custo is None else (resposta, custo)

    def reescrever(self, con, texto, pedido):
        """UMA chamada SEM ferramentas pedindo outra versão do rascunho. Texto novo ou None (sem chave/modelo/preço,
        teto, erro, resposta inválida). Não marca nada: quem chama (servico/saida.py) decide."""
        segredo, modelo = chave.ler(self.pasta_dados), banco.ler_config(con, "ia_modelo")
        par = precos.preco(precos.tabela(self.pasta_dados), modelo) if modelo else None
        if not segredo or par is None:
            return None
        corpo = {"model": modelo, "messages": [{"role": "system", "content": conhecimento.REGRAS + " " + pedido},
                                               {"role": "user", "content": "Rascunho a reescrever:\n" + texto}],
                 "max_completion_tokens": SAIDA_MAX}
        resposta, _ = self._chamar(con, segredo, par, corpo, {"chamadas": 0, "custo_usd": 0.0})
        try:
            novo = resposta["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            return None
        return novo.strip() if isinstance(novo, str) and novo.strip() else None

    def _parar(self, con, conversa_id, r, motivo, desligar=False):
        marcar_precisa_de_voce(con, conversa_id, motivo, desligar)
        r.update({"texto": None, "links": [], "precisa_de_voce": True, "motivo": motivo})
        return r

    def _ferramenta(self, con, conversa_id, chamada, links, r):
        """Executa UMA chamada de ferramenta. Nome ou argumento fora da lista = recusado (nada acontece)."""
        try:
            nome = chamada["function"]["name"]
            args = json.loads(chamada["function"].get("arguments") or "{}")
            if not isinstance(args, dict):
                raise ValueError
        except (KeyError, TypeError, ValueError, AttributeError):
            return {"ok": False, "erro": "chamada inválida"}
        if nome == "guardar_dado_do_lead":
            campo, valor = args.get("campo"), args.get("valor")
            if not isinstance(campo, str) or not CAMPO.match(campo) or not isinstance(valor, str) \
                    or not valor.strip() or len(valor) > VALOR_MAX:
                return {"ok": False, "erro": "dado inválido"}
            if campo == "nome":
                cur = con.execute("UPDATE contatos SET nome = ? WHERE id = (SELECT contato_id FROM conversas "
                                  "WHERE id = ?)", (valor.strip(), conversa_id))
                if cur.rowcount != 1:
                    return {"ok": False, "erro": "conversa não encontrada"}
            banco.registrar_evento(con, "dado_do_lead", json.dumps(
                {"conversa_id": conversa_id, "campo": campo, "valor": valor.strip()}, ensure_ascii=False))
            return {"ok": True}
        if nome == "qualificar":
            if args.get("nivel") not in NIVEIS:
                return {"ok": False, "erro": "nível inválido"}
            cur = con.execute("UPDATE conversas SET estado = ? WHERE id = ?", (args["nivel"], conversa_id))
            return {"ok": True} if cur.rowcount == 1 else {"ok": False, "erro": "conversa não encontrada"}
        if nome == "enviar_link":
            url = links.get(args.get("nome")) if isinstance(args.get("nome"), str) else None
            if url is None:
                banco.registrar_evento(con, "ia_link_recusado", json.dumps({"conversa_id": conversa_id}))
                return {"ok": False, "erro": "link fora da lista do projeto"}
            if url not in r["links"]:
                r["links"].append(url)
            return {"ok": True, "url": url}
        if nome == "pedir_humano":
            marcar_precisa_de_voce(con, conversa_id, "pedir_humano", True)
            r["precisa_de_voce"], r["motivo"], r["texto"] = True, "pedir_humano", None
            return {"ok": True}
        return {"ok": False, "erro": "ferramenta desconhecida"}
