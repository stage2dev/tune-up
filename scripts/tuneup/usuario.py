"""tune-up: user profile (~/.config/tune-up/user.json) with defaults."""
import json
import os
import re

from .sessao import log_erro

LANGUAGES = ("en", "pt-BR")
REPLY_STYLES = ("summary", "plain")
RE_LANG = re.compile(r"[A-Za-z]{2,3}(-[A-Za-z0-9]{2,8})*")
DEFAULT_MODELS = {
    "mapper": {"model": "haiku", "effort": "medium"},
    "checker": {"model": "haiku", "effort": "medium"},
    "persona": {"model": "haiku", "effort": "medium"},
    "skill-finder": {"model": "haiku", "effort": "medium"},
    "writer": {"model": "sonnet", "effort": "medium"},
    "researcher": {"model": "sonnet", "effort": "medium"},
    "executor-sonnet": {"model": "sonnet", "effort": "medium"},
    "executor-opus": {"model": "opus", "effort": "medium"},
    "plan-reviewer": {"model": "opus", "effort": "high"},
    "reviewer-failures": {"model": "opus", "effort": "high"},
    "reviewer-database": {"model": "opus", "effort": "high"},
    "reviewer-security": {"model": "opus", "effort": "high"},
}
DEFAULTS = {"language": "en", "owner": "", "reply_style": "plain", "forbidden_subagent_models": ["fable"],
            "names_override": {}, "protected_paths": [], "tools": {}, "plugin_source": None}
_CACHE = {}
RE_MODELO = re.compile(r"[A-Za-z0-9._:-]{1,64}")
EFFORTS = ("low", "medium", "high", "xhigh", "max")
SEM_MODELO = ("inherit", "default")


def modelo_casa(modelo, proibido):
    """Forbidden name inside the model id, case-insensitive, on token boundary (fable-5 yes, affable no).
    Same function for agent.py and info.py."""
    f = str(proibido or "").strip().casefold()
    if len(f) < 3:
        return False
    return re.search(r"(?<![a-z0-9])" + re.escape(f) + r"(?![a-z])", str(modelo or "").casefold()) is not None


def modelo_proibido(modelo, lista):
    return next((f for f in lista if modelo_casa(modelo, f)), None)


def sem_modelo(m):
    """None, empty, "inherit" or "default": the subagent inherits the session model."""
    return not isinstance(m, str) or not m.strip() or m.strip().lower() in SEM_MODELO


def caminho_user_json():
    return os.environ.get("TUNEUP_USER_JSON") or os.path.join(
        os.path.expanduser("~"), ".config", "tune-up", "user.json")


def _lista_str(v):
    return isinstance(v, list) and all(isinstance(x, str) for x in v)


def _dict_str(v):
    return isinstance(v, dict) and all(isinstance(k, str) and isinstance(x, str) for k, x in v.items())


def normalizar_idioma(v):
    """`pt-br` -> `pt-BR`; None when malformed (> 16 chars) or not in the message catalog."""
    if not isinstance(v, str) or len(v.strip()) > 16 or not RE_LANG.fullmatch(v.strip()):
        return None
    try:
        from .mensagens import CATALOG
        conhecidos = tuple(CATALOG)
    except Exception:
        conhecidos = LANGUAGES
    return {c.lower(): c for c in conhecidos}.get(v.strip().lower())


def nome_simples(v):
    return isinstance(v, str) and 0 < len(v) <= 80 and not any(
        x in v for x in ("/", "\\", "..", "\n", "\r"))


def _models(v):
    out = {k: dict(x) for k, x in DEFAULT_MODELS.items()}
    if not isinstance(v, dict):
        return out
    for papel, m in v.items():
        if not (isinstance(papel, str) and isinstance(m, dict) and _dict_str(m)):
            continue
        bom = {k: x for k, x in m.items()
               if (k == "model" and RE_MODELO.fullmatch(x)) or (k == "effort" and x in EFFORTS)}
        if len(bom) != len(m):
            log_erro("user", "user.json models[%r]: invalid entries discarded" % papel[:40])
        out[papel] = dict(out.get(papel, {}), **bom)
    return out


def ler_usuario():
    """(profile dict with defaults applied, file exists). Invalid keys fall back to the default."""
    caminho = caminho_user_json()
    if caminho in _CACHE:
        return _CACHE[caminho]
    bruto, existe, invalido = {}, os.path.isfile(caminho), False
    if existe:
        try:
            with open(caminho, encoding="utf-8") as f:
                bruto = json.load(f)
            if not isinstance(bruto, dict):
                raise ValueError("not a JSON object")
        except Exception as e:
            log_erro("user", "user.json invalid (%s): %r" % (caminho, e))
            bruto, existe, invalido = {}, False, True
    u = {k: (list(v) if isinstance(v, list) else dict(v) if isinstance(v, dict) else v)
         for k, v in DEFAULTS.items()}
    u["invalid"] = invalido
    if "language" in bruto:
        u["language"] = normalizar_idioma(bruto["language"]) or u["language"]
    dono = bruto.get("owner", bruto.get("owner_name"))
    if isinstance(dono, str):
        u["owner"] = re.sub(r"[\r\n\t]+", " ", dono).strip()[:60]
    if bruto.get("reply_style") in REPLY_STYLES:
        u["reply_style"] = bruto["reply_style"]
    elif "reply_style" in bruto:
        log_erro("user", "user.json reply_style invalid, using %s" % u["reply_style"])
    for k in ("forbidden_subagent_models", "protected_paths"):
        if _lista_str(bruto.get(k)):
            u[k] = list(bruto[k])
    curtos = [m for m in u["forbidden_subagent_models"] if len(m.strip()) < 3]
    if curtos:
        log_erro("user", "user.json forbidden_subagent_models: %d item(s) under 3 chars ignored" % len(curtos))
    u["forbidden_subagent_models"] = [m for m in u["forbidden_subagent_models"] if len(m.strip()) >= 3]
    if not u["forbidden_subagent_models"]:
        u["forbidden_subagent_models"] = list(DEFAULTS["forbidden_subagent_models"])
    if _dict_str(bruto.get("names_override")):
        u["names_override"] = {k: v for k, v in bruto["names_override"].items() if nome_simples(v)}
        if len(u["names_override"]) != len(bruto["names_override"]):
            log_erro("user", "user.json names_override: entries discarded (not a simple name)")
    if isinstance(bruto.get("tools"), dict):
        u["tools"] = {k: bool(v) for k, v in bruto["tools"].items() if isinstance(k, str)}
    if isinstance(bruto.get("plugin_source"), str) and bruto["plugin_source"].strip():
        u["plugin_source"] = bruto["plugin_source"].strip()
    u["models"] = _models(bruto.get("models"))
    _CACHE[caminho] = (u, existe)
    return _CACHE[caminho]


def idioma_efetivo(cfg=None):
    """Trusted project config > user.json > en."""
    if cfg and cfg.get("_confiado") and normalizar_idioma(cfg.get("language")):
        return normalizar_idioma(cfg["language"])
    return ler_usuario()[0]["language"] or "en"
