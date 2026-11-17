"""UTF-8 output for the studio scripts: on Windows stdout is cp1252 or an OEM code page, which cannot
print every brand name, file name or ad text (a "✓", "日本" or emoji raises UnicodeEncodeError).

Every script with a main() calls utf8() first (a test checks it). Python 3.9+, standard library only.
"""
import codecs
import sys


def utf8():
    """Switch sys.stdout and sys.stderr to UTF-8. A stream already in UTF-8 (macOS, Linux) is left
    exactly as it is; one without reconfigure (StringIO in a test) too."""
    for nome, erros in (("stdout", "replace"), ("stderr", "backslashreplace")):
        stream = getattr(sys, nome)
        if not hasattr(stream, "reconfigure"):
            continue
        try:
            atual = codecs.lookup(stream.encoding or "").name
        except LookupError:
            atual = ""
        if atual != "utf-8":
            stream.reconfigure(encoding="utf-8", errors=erros)
