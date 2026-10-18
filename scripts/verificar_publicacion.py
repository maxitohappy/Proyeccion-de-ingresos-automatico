"""Revisa los archivos que se publicarán en el repositorio y bloquea datos sensibles.

Comprueba:
* que no haya planillas, PDF, Word ni presentaciones fuera de ejemplos/;
* que no haya RUT con formato (con guion y dígito verificador) en archivos de texto;
* que no aparezca ningún término de la lista local tests/datos_locales/palabras_bloqueadas.txt
  (nombres y RUT de clientes reales; esa lista nunca se publica).
Uso: python scripts/verificar_publicacion.py   (código de salida 1 si encuentra problemas)
"""
from __future__ import annotations

import re
import subprocess
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
BINARIOS = {".xlsx", ".xls", ".xlsm", ".pdf", ".docx", ".doc", ".pptx", ".ppt", ".zip", ".parquet", ".duckdb"}
RUT = re.compile(r"\b\d{1,2}\.?\d{3}\.?\d{3}-[\dkK]\b")
LISTA_LOCAL = RAIZ / "tests" / "datos_locales" / "palabras_bloqueadas.txt"


def archivos_a_publicar() -> list[str]:
    salida = subprocess.run(["git", "ls-files", "--cached", "--others", "--exclude-standard"],
                            cwd=RAIZ, capture_output=True, text=True, check=True).stdout
    return [l for l in salida.splitlines() if l.strip()]


def main() -> int:
    bloqueadas = []
    if LISTA_LOCAL.exists():
        bloqueadas = [l.strip().upper() for l in LISTA_LOCAL.read_text(encoding="utf-8").splitlines()
                      if len(l.strip()) >= 5 and not l.startswith("#")]
    numeros_bloqueados = {b for b in bloqueadas if b.isdigit()}
    nombres_bloqueados = [b for b in bloqueadas if not b.isdigit()]
    problemas = []
    for rel in archivos_a_publicar():
        p = RAIZ / rel
        if not p.exists():
            continue
        if p.suffix.lower() in BINARIOS:
            if not rel.startswith("ejemplos/"):
                problemas.append(f"{rel}: archivo binario de oficina fuera de ejemplos/")
            continue
        if rel.startswith("tests/datos_locales/"):
            problemas.append(f"{rel}: datos locales no deben publicarse")
            continue
        try:
            texto = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        if RUT.search(texto):
            problemas.append(f"{rel}: contiene un RUT con formato ({RUT.search(texto).group(0)})")
        mayus = texto.upper()
        # Los números (RUT sin formato) deben coincidir completos, no dentro de otro número.
        numeros = set(re.findall(r"(?<![\d.,])\d{5,}(?![\d.,])", mayus))
        if numeros & numeros_bloqueados or any(n in mayus for n in nombres_bloqueados):
            problemas.append(f"{rel}: contiene un término de la lista de datos reales")
    if problemas:
        print("PUBLICACIÓN BLOQUEADA:")
        for pr in problemas:
            print(" -", pr)
        return 1
    aviso = "" if bloqueadas else " (sin lista local de términos bloqueados)"
    print(f"OK: no se detectaron datos sensibles en los archivos a publicar{aviso}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
