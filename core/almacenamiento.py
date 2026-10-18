"""Persistencia local de la app.

En modo local los datos se guardan en la carpeta `data/` del proyecto (excluida del
repositorio). En el navegador (stlite) la variable PROYECCION_DATA_DIR apunta a una
carpeta montada en IndexedDB, por lo que nada sale del equipo del usuario.
"""
from __future__ import annotations

import io
import json
import os
import zipfile
from datetime import datetime
from pathlib import Path

import pandas as pd

_RAIZ_PROYECTO = Path(__file__).resolve().parent.parent


def directorio() -> Path:
    d = Path(os.environ.get("PROYECCION_DATA_DIR", _RAIZ_PROYECTO / "data"))
    d.mkdir(parents=True, exist_ok=True)
    return d


def ruta(relativa: str) -> Path:
    p = directorio() / relativa
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def existe(relativa: str) -> bool:
    return (directorio() / relativa).exists()


def leer_csv(relativa: str, **kwargs) -> pd.DataFrame | None:
    p = directorio() / relativa
    if not p.exists():
        return None
    return pd.read_csv(p, **kwargs)


def escribir_csv(relativa: str, df: pd.DataFrame) -> None:
    df.to_csv(ruta(relativa), index=False)


def leer_json(relativa: str, defecto=None):
    p = directorio() / relativa
    if not p.exists():
        return defecto
    with open(p, encoding="utf-8") as f:
        return json.load(f)


def escribir_json(relativa: str, obj) -> None:
    with open(ruta(relativa), "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)


def eliminar(relativa: str) -> None:
    p = directorio() / relativa
    if p.exists():
        p.unlink()


def listar(subcarpeta: str = "") -> list[str]:
    base = directorio() / subcarpeta
    if not base.exists():
        return []
    return sorted(str(p.relative_to(directorio())).replace("\\", "/") for p in base.rglob("*") if p.is_file())


def exportar_respaldo() -> bytes:
    """Empaqueta todos los datos guardados en un .zip descargable."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
        for rel in listar():
            z.write(directorio() / rel, rel)
        z.writestr("_respaldo.json", json.dumps({"creado": datetime.now().isoformat(timespec="seconds")}))
    return buf.getvalue()


def importar_respaldo(contenido: bytes, reemplazar: bool = False) -> int:
    """Restaura un respaldo .zip. Devuelve la cantidad de archivos restaurados."""
    if reemplazar:
        for rel in listar():
            eliminar(rel)
    n = 0
    with zipfile.ZipFile(io.BytesIO(contenido)) as z:
        for nombre in z.namelist():
            if nombre.endswith("/") or nombre == "_respaldo.json" or ".." in Path(nombre).parts:
                continue
            with open(ruta(nombre), "wb") as f:
                f.write(z.read(nombre))
            n += 1
    return n
