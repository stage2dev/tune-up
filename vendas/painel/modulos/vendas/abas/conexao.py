"""Blocos da aba Conexão ligados ao WhatsApp: estado da Evolution, formulário de instância, QR e estado da
conexão. Só fala com o serviço por cliente.chamar (porta, batimento e marca conferidos). O QR vem do serviço a cada
montar (leitura fresca, sem cache aqui) e vai só para o bloco imagem. Nada de token ou chave sai daqui."""
import os
import re

ESTADOS = {"desconectado": "Desconectado", "aguardando_qr": "Aguardando QR", "conectado": "Conectado"}
NOME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
PADRAO = "vendas"
AVISO = ("O QR conecta por uma via NÃO oficial do WhatsApp. O número pode ser banido a qualquer momento. "
         "Primeiro contato frio (sem o cliente ter falado antes) viola a Política do WhatsApp Business. "
         "Use só um número descartável, nunca o seu número principal.")
PNG = "data:image/png;base64,"


def evolution_preparada(raiz, cliente, base=None):
    """True se o preparar já gravou compose.yml e .env (só confere se existem; nunca lê o .env)."""
    pasta = os.path.join(cliente.pasta.caminho_da_pasta(raiz, base), "evolution")
    return all(os.path.isfile(os.path.join(pasta, n)) for n in ("compose.yml", ".env"))


def bloco_evolution(ctx, cliente, comando_preparar, base=None):
    raiz = ctx.get("raiz") or ""
    if raiz and evolution_preparada(raiz, cliente, base):
        compose = os.path.join(cliente.pasta.caminho_da_pasta(raiz, base), "evolution", "compose.yml")
        return {"tipo": "texto", "titulo": "Evolution preparada",
                "texto": "Os arquivos da Evolution local existem. Para ligar (num terminal, não pelo Claude): "
                         "docker compose -f %s up -d" % cliente.citar(compose)}
    return {"tipo": "texto", "titulo": "Evolution não preparada",
            "texto": "Prepare os arquivos da Evolution local (Docker) com: %s . Depois suba com o comando "
                     "docker compose que ele mostrar no fim." % comando_preparar}


def ler_instancia(ctx, cliente, base=None):
    """(dados do serviço, aviso). Serviço sem resposta ou recusa vira aviso, nunca exceção."""
    try:
        codigo, r = cliente.chamar(ctx, "GET", "/instancia", base=base)
    except cliente.Recusa as e:
        return None, str(e)
    if codigo != 200 or not isinstance(r, dict):
        return None, str((r if isinstance(r, dict) else {}).get("erro") or "O serviço recusou (%d)." % codigo)
    return r, None


def blocos_instancia(dados, aviso):
    r = dados or {}
    estado = r.get("estado") if r.get("estado") in ESTADOS else "desconectado"
    blocos = [{"tipo": "texto", "titulo": "Atenção: conexão por QR", "texto": AVISO},
              {"tipo": "formulario", "id": "instancia", "titulo": "Criar ou conectar o WhatsApp",
               "descricao": "Dá um nome à instância e confirma que o número é descartável. Depois leia o QR no "
                            "aparelho (WhatsApp > Aparelhos conectados).",
               "acao": "conectar_instancia", "botao": "Criar e mostrar QR", "campos": [
                   {"id": "instancia", "rotulo": "Nome da instância", "tipo": "texto",
                    "valor": r.get("instancia") or PADRAO, "obrigatorio": True,
                    "ajuda": "Letras, números, _ e -, até 64."},
                   {"id": "numero_descartavel", "rotulo": "Este é um número descartável (posso perdê-lo)",
                    "tipo": "escolha", "valor": "nao", "obrigatorio": True,
                    "opcoes": [{"valor": "nao", "rotulo": "Não"}, {"valor": "sim", "rotulo": "Sim, é descartável"}],
                    "ajuda": "Sem confirmar, a conexão funciona mas campanhas a frio continuam desligadas."}]}]
    if aviso:
        blocos.append({"tipo": "texto", "titulo": "Conexão indisponível", "texto": aviso})
        return blocos
    itens = [{"rotulo": "Conexão", "valor": ESTADOS[estado], "tom": "bom" if estado == "conectado" else "atencao"},
             {"rotulo": "Instância", "valor": r.get("instancia") or "nenhuma"},
             {"rotulo": "Número descartável", "valor": "sim" if r.get("numero_descartavel") else "não"}]
    blocos.append({"tipo": "kpis", "titulo": "WhatsApp", "itens": itens})
    if r.get("aviso"):
        blocos.append({"tipo": "texto", "titulo": "Aviso", "texto": str(r["aviso"])})
    qr = r.get("qr")
    if estado != "conectado" and isinstance(qr, str) and qr.startswith(PNG):
        blocos.append({"tipo": "imagem", "titulo": "QR para conectar", "data_uri": qr,
                       "alt": "QR code para conectar o WhatsApp", "legenda": "Expira em instantes; a tela atualiza "
                       "ao agir. Se sumir, use o botão de novo."})
    return blocos


def agir_conectar(ctx, cliente, dados, base=None):
    """conectar_instancia: nome válido; numero_descartavel só vale true com "sim". Nunca desloga nem apaga."""
    nome = str((dados or {}).get("instancia") or "").strip()
    if not NOME.match(nome):
        return {"ok": False, "mensagem": "Nome inválido: use letras, números, _ e -, até 64."}
    descartavel = (dados or {}).get("numero_descartavel") in ("sim", True)
    try:
        codigo, r = cliente.chamar(ctx, "POST", "/instancia", {"instancia": nome, "numero_descartavel": descartavel},
                                   base=base)
    except cliente.Recusa as e:
        return {"ok": False, "mensagem": str(e)}
    if codigo != 200:
        return {"ok": False, "mensagem": str((r if isinstance(r, dict) else {}).get("erro")
                                             or "O serviço recusou (%d)." % codigo)}
    return {"ok": True, "mensagem": "Instância pronta. Leia o QR no aparelho."
            if (r or {}).get("estado") != "conectado" else "Instância conectada."}
