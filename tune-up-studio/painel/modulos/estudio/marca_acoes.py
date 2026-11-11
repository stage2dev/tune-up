"""Comandos da aba Marca do estúdio: o que a tela muda no <raiz>/.tune-up/estudio/marca/marca.json.

Toda mudança grava o campo com fonte "dono" e travado (a redescoberta não mexe nele) e derruba a aprovação:
o sha256 do marca.json muda (dono.faltando confere) e, quando o comando vem da tela, grava {"aprovado": False}.
Logo e fotos chegam pela rota de envio do painel (INFO["envios"], base tune-up) em marca/assets e marca/fotos;
o servidor chama `recebido` depois de gravar. A sessão do estúdio só lê essas pastas (sandbox: escreve só no
trabalho). Python 3.9, só biblioteca padrão.
"""
import json
import os
import re
import sys

REL_MARCA = ".tune-up/estudio/marca/marca.json"
SCRIPTS = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.realpath(__file__))))), "scripts")
RE_ENVIADO = re.compile(r"^[0-9a-f]{16}\.(png|jpg|webp)$")  # nome dado pela rota de envio
PASTA = {"logo": "assets", "fotos": "fotos"}
MAX_FOTOS = 8
# (chave, rótulo, para que serve); a cor que falta aparece com a paleta neutra de descobrir_marca
CORES = [("cores.primary", "Cor principal", "Blocos grandes e títulos"),
         ("cores.accent", "Cor de destaque", "Botões e números"),
         ("cores.bg", "Fundo", "Atrás de tudo"),
         ("cores.surface", "Fundo secundário", "Faixas e cartões"),
         ("cores.text", "Texto", "Frases e legendas")]
NEUTRA = {"cores.bg": "#ffffff", "cores.surface": "#f4f4f5", "cores.primary": "#18181b",
          "cores.text": "#18181b", "cores.accent": "#52525b"}  # = descobrir_marca.PALETA_NEUTRA
PARES = {"classica": ("Clássica", 'Georgia, "Times New Roman", serif', "Inter, system-ui, sans-serif"),
         "moderna": ("Moderna", "Inter, system-ui, sans-serif", "Inter, system-ui, sans-serif"),
         "forte": ("Forte", '"Arial Black", "Helvetica Neue", Arial, sans-serif', 'Arial, "Helvetica Neue", sans-serif')}
TONS = [("acolhedor", "Acolhedor"), ("direto", "Direto"), ("divertido", "Divertido"), ("formal", "Formal"),
        ("tecnico", "Técnico")]
ROTULOS = dict([(k, r) for k, r, _ in CORES], nome="Nome", descricao="O que vocês fazem",
               **{"fontes.heading": "Letra dos títulos", "fontes.body": "Letra do texto", "logo": "Logo"})
CORES_DA_LOGO = (".png", ".svg")  # JPEG e WebP não têm leitor na biblioteca padrão


def scripts():
    """(cores, descobrir_marca, marca_leitores, cores_da_logo) do plugin."""
    sys.path.insert(0, SCRIPTS)
    try:
        import cores
        import cores_da_logo
        import descobrir_marca
        import marca_leitores
    finally:  # descobrir_marca e cores_da_logo também se põem no sys.path: tira todas as entradas
        while SCRIPTS in sys.path:
            sys.path.remove(SCRIPTS)
    return cores, descobrir_marca, marca_leitores, cores_da_logo


def ler(ctx):
    """(caminho, bytes, objeto) do marca.json, ou None."""
    if not ctx.get("raiz"):
        return None
    caminho = os.path.join(ctx["raiz"], *REL_MARCA.split("/"))
    try:
        if os.path.islink(caminho):
            return None
        with open(caminho, "rb") as f:
            bruto = f.read()
        obj = json.loads(bruto.decode("utf-8"))
    except (OSError, ValueError):
        return None
    return (caminho, bruto, obj) if isinstance(obj, dict) and isinstance(obj.get("campos"), dict) else None


def _dono(valor):
    return {"valor": valor, "fonte": "dono", "confianca": "alta", "travado": True}


def _sem_marca():
    return {"feito": False, "mensagem": "Ainda não há marca. Use Procurar de novo no meu projeto."}


def _salvar(ctx, caminho, obj, mensagem):
    scripts()[1]._gravar(caminho, json.dumps(obj, ensure_ascii=False, indent=2) + "\n")  # O_EXCL|O_NOFOLLOW
    if callable(ctx.get("gravar_dono")):
        ctx["gravar_dono"]("marca", {"aprovado": False})
    return {"feito": True, "mensagem": mensagem + " Confira a prévia e clique em Está certo, usar esta marca."}


def editar(ctx, dados):
    cores, dm, ml, _ = scripts()
    campo, valor = dados.get("campo"), (dados.get("valor") or "").strip()
    if campo not in ml.CAMPOS or not valor or len(valor) > 200 or "\n" in valor:
        return {"feito": False, "mensagem": "Campo ou valor inválido."}
    if campo.startswith("cores."):
        valor = cores.para_hex(valor)
        if valor is None:
            return {"feito": False, "mensagem": "Não entendi essa cor. Use um valor como #1A2B3C."}
    m = ler(ctx)
    if m is None:
        return _sem_marca()
    caminho, _, obj = m
    obj["campos"][campo] = _dono(valor)
    if campo == "logo":  # a cópia antiga não é mais o logo do dono: some, e entra a nova se o arquivo existe
        _limpar_logo(os.path.dirname(caminho), None)
        obj["logo_copia"] = dm.copiar_logo(ctx["raiz"], os.path.dirname(caminho), obj["campos"]["logo"])
    return _salvar(ctx, caminho, obj, "%s salvo." % ROTULOS.get(campo, campo))


def _limpar_logo(base, manter):
    """Apaga as cópias (logo.*) e os envios antigos de assets/, menos `manter`."""
    assets = os.path.join(base, "assets")
    for n in os.listdir(assets) if os.path.isdir(assets) and not os.path.islink(assets) else []:
        p = os.path.join(assets, n)
        if n != manter and (n.lower().startswith("logo.") or RE_ENVIADO.match(n)) and not os.path.islink(p) \
                and os.path.isfile(p):
            os.remove(p)


def fotos(obj, base):
    """Lista {arquivo, principal} conferida com o disco: some a que saiu, entra a que chegou (por ordem)."""
    pasta = os.path.join(base, "fotos")
    no_disco = []
    if os.path.isdir(pasta) and not os.path.islink(pasta):
        for n in os.listdir(pasta):
            p = os.path.join(pasta, n)
            if RE_ENVIADO.match(n) and not os.path.islink(p) and os.path.isfile(p):
                no_disco.append((os.path.getmtime(p), n))
    nomes = [n for _, n in sorted(no_disco)]
    antes = [f.get("arquivo") for f in obj.get("fotos") or [] if isinstance(f, dict)]
    ordem = [a for a in antes if isinstance(a, str) and a[len("fotos/"):] in nomes and a.startswith("fotos/")]
    ordem += ["fotos/" + n for n in nomes if "fotos/" + n not in ordem]
    return [{"arquivo": a, "principal": i == 0} for i, a in enumerate(ordem[:MAX_FOTOS])]


def recebido(ctx, dados):
    """Gancho da rota de envio: {destino, caminho} de um arquivo que o servidor acabou de gravar."""
    destino, caminho = dados.get("destino"), dados.get("caminho")
    partes = caminho.split("/") if isinstance(caminho, str) else []
    if destino not in PASTA or partes[:-1] != ["estudio", "marca", PASTA[destino]] \
            or not RE_ENVIADO.match(partes[-1]):
        return {"feito": False, "mensagem": "Arquivo fora do lugar da marca."}
    m = ler(ctx)
    if m is None:
        return _sem_marca()
    arq, _, obj = m
    base = os.path.dirname(arq)
    if destino == "fotos":
        obj["fotos"] = fotos(obj, base)
        return _salvar(ctx, arq, obj, "Foto guardada.")
    _limpar_logo(base, partes[-1])
    obj["campos"]["logo"] = _dono("/".join([".tune-up", "estudio", "marca", "assets", partes[-1]]))
    obj["logo_copia"] = scripts()[1].copiar_logo(ctx["raiz"], base, obj["campos"]["logo"])
    return _salvar(ctx, arq, obj, "Logo guardada.")


def sem_logo(ctx, dados):
    if dados.get("confirmar") is not True:
        return {"feito": False, "mensagem": "Confirme que o negócio não tem logo."}
    m = ler(ctx)
    if m is None:
        return _sem_marca()
    arq, _, obj = m
    _limpar_logo(os.path.dirname(arq), None)
    obj["campos"]["logo"], obj["logo_copia"] = _dono(None), None
    return _salvar(ctx, arq, obj, "Combinado: as peças saem sem logo, com o nome do negócio.")


def remover_foto(ctx, dados):
    arquivo = dados.get("arquivo")
    partes = arquivo.split("/") if isinstance(arquivo, str) else []
    if dados.get("destino") != "fotos" or partes[:-1] != ["estudio", "marca", "fotos"] \
            or not RE_ENVIADO.match(partes[-1]):
        return {"feito": False, "mensagem": "Essa foto não é da marca."}
    m = ler(ctx)
    if m is None:
        return _sem_marca()
    arq, _, obj = m
    p = os.path.join(os.path.dirname(arq), "fotos", partes[-1])
    if os.path.isfile(p) and not os.path.islink(p):
        os.remove(p)
    obj["fotos"] = fotos(obj, os.path.dirname(arq))
    return _salvar(ctx, arq, obj, "Foto removida.")


def cores_da_logo(ctx, dados):
    m = ler(ctx)
    if m is None:
        return _sem_marca()
    arq, _, obj = m
    copia = obj.get("logo_copia")
    if not isinstance(copia, str) or not re.match(r"^assets/[\w.-]+$", copia) \
            or not copia.lower().endswith(CORES_DA_LOGO):
        return {"feito": False, "mensagem": "Só consigo ler as cores de uma logo em PNG ou SVG."}
    cl = scripts()[3]
    try:
        achado = cl.ler(os.path.join(os.path.dirname(arq), *copia.split("/")))
    except (cl.Ilegivel, OSError) as e:
        return {"feito": False, "mensagem": "Não consegui pegar as cores da logo: %s." % e}
    papeis = achado["papeis"]
    for papel, h in papeis.items():
        obj["campos"]["cores." + papel] = _dono(h)
    nomes = [ROTULOS["cores." + p] for p in ("primary", "accent", "bg", "surface", "text") if p in papeis]
    return _salvar(ctx, arq, obj, "Peguei da logo: %s. As outras cores ficaram como estavam." % ", ".join(nomes))


def par_do_projeto(obj):
    """(titulo, texto) das letras achadas no projeto, ou None."""
    salvo = obj.get("letras_do_projeto")
    if isinstance(salvo, dict) and isinstance(salvo.get("titulo"), str):
        return salvo["titulo"], salvo.get("texto") if isinstance(salvo.get("texto"), str) else salvo["titulo"]
    c = obj["campos"]
    h, b = (c.get(k) if isinstance(c.get(k), dict) else {} for k in ("fontes.heading", "fontes.body"))
    if h.get("fonte") == "dono" or b.get("fonte") == "dono" or not (h.get("valor") or b.get("valor")):
        return None
    return str(h.get("valor") or b.get("valor")), str(b.get("valor") or h.get("valor"))


def letras(ctx, dados):
    m = ler(ctx)
    if m is None:
        return _sem_marca()
    arq, _, obj = m
    valor, projeto = dados.get("valor"), par_do_projeto(obj)
    if dados.get("campo") != "letras" or (valor not in PARES and not (valor == "projeto" and projeto)):
        return {"feito": False, "mensagem": "Escolha uma das letras mostradas."}
    if projeto and "letras_do_projeto" not in obj:  # guarda o par achado antes de trocar
        obj["letras_do_projeto"] = {"titulo": projeto[0], "texto": projeto[1]}
    titulo, texto = projeto if valor == "projeto" else PARES[valor][1:]
    obj["campos"]["fontes.heading"], obj["campos"]["fontes.body"] = _dono(titulo), _dono(texto)
    return _salvar(ctx, arq, obj, "Letras trocadas.")


def tom(ctx, dados):
    nomes = [k for k, _ in TONS]
    if dados.get("campo") != "tom" or dados.get("valor") not in nomes or not isinstance(dados.get("ligado"), bool):
        return {"feito": False, "mensagem": "Escolha um dos jeitos de falar mostrados."}
    m = ler(ctx)
    if m is None:
        return _sem_marca()
    arq, _, obj = m
    antes = obj.get("tom", {}).get("valor") if isinstance(obj.get("tom"), dict) else None
    ligados = set(v for v in antes or [] if v in nomes)
    if dados["ligado"]:
        ligados.add(dados["valor"])
    else:
        ligados.discard(dados["valor"])
    obj["tom"] = {"valor": [k for k in nomes if k in ligados], "fonte": "dono", "travado": True}
    return _salvar(ctx, arq, obj, "Jeito de falar salvo.")
