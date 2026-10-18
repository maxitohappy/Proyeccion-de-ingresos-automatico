"""Tablas resumen equivalentes a las tablas dinámicas del libro de gestión."""
from __future__ import annotations

import pandas as pd

from .clasificacion import CLASES_DE
from .esquema import CONCEPTOS_PROYECCION, MESES


def _por_mes(df: pd.DataFrame, filas, anio: int) -> pd.DataFrame:
    d = df[df["ANIO"] == anio]
    if d.empty:
        return pd.DataFrame()
    t = d.pivot_table(index=filas, columns="MES", values="MONTO", aggfunc="sum", fill_value=0)
    t.columns = [MESES[int(m) - 1] for m in t.columns]
    t["Total"] = t.sum(axis=1)
    return t


def ingreso_mensual(agg: pd.DataFrame, anio: int) -> pd.DataFrame:
    d = agg[agg["ANIO"] == anio].groupby("MES")["MONTO"].sum()
    t = pd.DataFrame({"Mes": [MESES[int(m) - 1] for m in d.index], "Total": d.values})
    return pd.concat([t, pd.DataFrame({"Mes": ["Total general"], "Total": [d.sum()]})], ignore_index=True)


def por_concepto(agg: pd.DataFrame, anio: int) -> pd.DataFrame:
    """Concepto × tipo de ingreso (como la hoja 'Ingresos Por Conceptos')."""
    t = _por_mes(agg, ["CONCEPTO", "TIPO_INGRESO"], anio)
    if t.empty:
        return t
    filas = []
    for concepto, bloque in t.groupby(level=0, sort=True):
        for (c, tipo), fila in bloque.iterrows():
            filas.append(pd.Series(fila, name=(c, tipo if len(bloque) > 1 else "")))
        if len(bloque) > 1:
            filas.append(pd.Series(bloque.sum(), name=(f"Total {concepto}", "")))
    filas.append(pd.Series(t.sum(), name=("Total general", "")))
    r = pd.DataFrame(filas)
    r.index = pd.MultiIndex.from_tuples(r.index, names=["Concepto", "Tipo"])
    return r


def por_concepto_proyeccion(agg: pd.DataFrame, anio: int) -> pd.DataFrame:
    """Los 7 conceptos de proyección × mes."""
    t = _por_mes(agg, "CONCEPTO_PROY", anio)
    if t.empty:
        return t
    t = t.reindex([k for k in CONCEPTOS_PROYECCION if k in t.index])
    t.index = [CONCEPTOS_PROYECCION[k] for k in t.index]
    t.loc["Total"] = t.sum()
    return t


def por_unidad(agg: pd.DataFrame, anio: int, nombres: dict[int, str], agrupar: bool = True,
               meses: list[int] | None = None) -> pd.DataFrame:
    """Unidad (agrupada según maestro) × 7 conceptos de proyección."""
    d = agg[agg["ANIO"] == anio]
    if meses:
        d = d[d["MES"].isin(meses)]
    if d.empty:
        return pd.DataFrame()
    col = "UNIDAD_GRUPO" if agrupar else "UNIDAD_PRESTACION_SERVICIO"
    t = d.pivot_table(index=col, columns="CONCEPTO_PROY", values="MONTO", aggfunc="sum", fill_value=0)
    t = t.reindex(columns=[k for k in CONCEPTOS_PROYECCION if k in t.columns])
    t["TOTAL"] = t.sum(axis=1)
    t = t.sort_values("TOTAL", ascending=False)
    t.insert(0, "Unidad", [nombres.get(int(u), str(u)) for u in t.index])
    t.columns = ["Unidad"] + [CONCEPTOS_PROYECCION.get(c, "Total") for c in t.columns[1:]]
    t.index.name = "Código"
    return t


def de_clasificaciones(agg: pd.DataFrame, anio: int, clase: str, nombres: dict[int, str]) -> pd.DataFrame:
    """Derecho de embarque de una clase tarifaria por unidad × mes."""
    d = agg[(agg["CLASE_DE"] == clase)]
    t = _por_mes(d, "UNIDAD_GRUPO", anio)
    if t.empty:
        return t
    t.insert(0, "Unidad", [nombres.get(int(u), str(u)) for u in t.index])
    t.index.name = "Código"
    return t


def resumen_clases_de(agg: pd.DataFrame, anio: int) -> pd.DataFrame:
    d = agg[(agg["ANIO"] == anio) & (agg["CLASE_DE"] != "")]
    t = _por_mes(d, "CLASE_DE", anio)
    if t.empty:
        return t
    t.index = [CLASES_DE.get(i, i) for i in t.index]
    return t


def por_descripcion(agg: pd.DataFrame, anio: int) -> pd.DataFrame:
    """Ranking por denominación (hoja 'Busqueda')."""
    d = agg[agg["ANIO"] == anio].groupby(["DESCRIPCION", "TIPO_INGRESO"])["MONTO"].sum()
    return d.sort_values(ascending=False).reset_index().rename(
        columns={"DESCRIPCION": "Descripción", "TIPO_INGRESO": "Tipo", "MONTO": "Total"}
    )
