"""Snapshots de proyecciones y análisis de diferencias (instructivo, actividades 8 y 9)."""
from __future__ import annotations

import json
import re
from datetime import datetime

import numpy as np
import pandas as pd

from . import almacenamiento as alm
from .esquema import CONCEPTOS_PROYECCION, MESES
from .proyeccion import ResultadoProyeccion

CARPETA = "snapshots"

EFECTOS = ["Pasajeros", "Operaciones", "Dólar", "Tarifa, IPC y otros", "Otros conceptos"]


def _id(nombre: str) -> str:
    base = re.sub(r"[^a-z0-9]+", "-", nombre.lower()).strip("-")[:40] or "proyeccion"
    return f"{datetime.now():%Y%m%d-%H%M%S}-{base}"


def guardar_snapshot(res: ResultadoProyeccion, nombre: str, comentario: str = "") -> str:
    sid = _id(nombre)
    alm.escribir_csv(f"{CARPETA}/{sid}/ingresos.csv", res.ingresos)
    alm.escribir_csv(f"{CARPETA}/{sid}/trafico.csv", res.trafico)
    alm.escribir_csv(f"{CARPETA}/{sid}/factores.csv", res.factores.reset_index().rename(columns={"index": "periodo"}))
    alm.escribir_json(f"{CARPETA}/{sid}/meta.json", {
        "id": sid, "nombre": nombre, "comentario": comentario,
        "creado": datetime.now().isoformat(timespec="seconds"),
        "ultimo_cerrado": list(res.ultimo_cerrado),
        "totales": {str(a): res.total_anual(int(a)) for a in sorted(res.ingresos["ANIO"].unique())},
        "config": res.config,
    })
    return sid


def listar_snapshots() -> list[dict]:
    metas = []
    for rel in alm.listar(CARPETA):
        if rel.endswith("meta.json"):
            metas.append(alm.leer_json(rel))
    return sorted(metas, key=lambda m: m["creado"], reverse=True)


def cargar_snapshot(sid: str) -> dict:
    meta = alm.leer_json(f"{CARPETA}/{sid}/meta.json")
    ingresos = alm.leer_csv(f"{CARPETA}/{sid}/ingresos.csv")
    trafico = alm.leer_csv(f"{CARPETA}/{sid}/trafico.csv")
    factores = alm.leer_csv(f"{CARPETA}/{sid}/factores.csv")
    return {"meta": meta, "ingresos": ingresos, "trafico": trafico, "factores": factores}


def eliminar_snapshot(sid: str) -> None:
    for rel in alm.listar(f"{CARPETA}/{sid}"):
        alm.eliminar(rel)


def _etiqueta_volumen(concepto: str) -> str | None:
    if concepto.startswith("DE_"):
        return "Pasajeros"
    if concepto.startswith("TASAS_"):
        return "Operaciones"
    return None


def comparar(nueva: pd.DataFrame, anterior: pd.DataFrame) -> pd.DataFrame:
    """Diferencia por unidad × concepto × mes descompuesta en efectos (suma exacta).

    Secuencia: efecto volumen (PAX u operaciones) = R0·(Q1/Q0 − 1);
    efecto dólar = R0·(Q1/Q0)·(D1/D0 − 1); el resto es tarifa/IPC/otros.
    """
    claves = ["ANIO", "MES", "UNIDAD", "CONCEPTO_PROY"]
    a = anterior[claves + ["MONTO", "ORIGEN", "CANTIDAD", "DOLAR"]].groupby(claves).agg(
        R0=("MONTO", "sum"), ORIGEN0=("ORIGEN", "first"), Q0=("CANTIDAD", "first"), D0=("DOLAR", "first"))
    n = nueva[claves + ["MONTO", "ORIGEN", "CANTIDAD", "DOLAR"]].groupby(claves).agg(
        R1=("MONTO", "sum"), ORIGEN1=("ORIGEN", "first"), Q1=("CANTIDAD", "first"), D1=("DOLAR", "first"))
    d = a.join(n, how="outer").reset_index()
    d[["R0", "R1"]] = d[["R0", "R1"]].fillna(0.0)
    d["DIFERENCIA"] = d["R1"] - d["R0"]
    for e in EFECTOS:
        d[e] = 0.0
    q_ok = d["Q0"].gt(0) & d["Q1"].notna()
    d_ok = d["D0"].gt(0) & d["D1"].notna()
    ratio_q = np.where(q_ok, d["Q1"] / d["Q0"].where(q_ok, 1), 1.0)
    ratio_d = np.where(d_ok, d["D1"] / d["D0"].where(d_ok, 1), 1.0)
    vol = d["R0"] * (ratio_q - 1)
    dol = d["R0"] * ratio_q * (ratio_d - 1)
    etiqueta = d["CONCEPTO_PROY"].map(_etiqueta_volumen)
    for e in ("Pasajeros", "Operaciones"):
        d[e] = np.where(etiqueta == e, vol, 0.0)
    d["Dólar"] = dol
    resto = d["DIFERENCIA"] - d["Pasajeros"] - d["Operaciones"] - d["Dólar"]
    d["Tarifa, IPC y otros"] = np.where(etiqueta.notna(), resto, 0.0)
    d["Otros conceptos"] = np.where(etiqueta.isna(), resto, 0.0)
    d["ESTADO"] = np.select(
        [(d["ORIGEN0"] != "Real") & (d["ORIGEN1"] == "Real"), d["ORIGEN1"] == "Real"],
        ["Cerrado desde la proyección anterior", "Real en ambas"], "Proyectado en ambas",
    )
    return d


def resumen_efectos(comp: pd.DataFrame, anio: int, solo_estado: str | None = None) -> pd.DataFrame:
    d = comp[comp["ANIO"] == anio]
    if solo_estado:
        d = d[d["ESTADO"] == solo_estado]
    t = d.groupby("CONCEPTO_PROY")[["R0", "R1", "DIFERENCIA"] + EFECTOS].sum()
    t = t.reindex([c for c in CONCEPTOS_PROYECCION if c in t.index])
    t.index = [CONCEPTOS_PROYECCION[c] for c in t.index]
    t.loc["Total"] = t.sum()
    return t.rename(columns={"R0": "Proyección anterior", "R1": "Proyección actual", "DIFERENCIA": "Diferencia"})


def meses_cerrados_desde_anterior(comp: pd.DataFrame) -> list[tuple[int, int]]:
    d = comp[comp["ESTADO"] == "Cerrado desde la proyección anterior"]
    return sorted(set(zip(d["ANIO"].astype(int), d["MES"].astype(int))))


def texto_mes(anio: int, mes: int) -> str:
    return f"{MESES[mes - 1]} {anio}"


def exportar_meta(meta: dict) -> str:
    return json.dumps(meta, ensure_ascii=False, indent=2)
