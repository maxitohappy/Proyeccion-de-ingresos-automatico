"""Depuración y clasificación del informe SAC (instructivo, actividad 4).

Reemplaza los BUSCARV del libro de gestión: cuenta de gestión -> plan de cuentas ->
categoría -> concepto, descarta la unidad 5220 (Aldeasa) y genera alertas para
informar a la Sección Tasas Aeronáuticas.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

import pandas as pd

from .esquema import DE, UNIDADES_DESCARTADAS_DEFECTO, concepto_proyeccion
from .maestros import Maestros, nombres_unidades, unidad_grupo

# Clases tarifarias del derecho de embarque, detectadas desde el texto de DETALLE.
UMBRAL_REPETIDAS = 10_000_000

CLASES_DE = {
    "NAC_1C": "1ª categoría nacional",
    "NAC_2C": "2ª categoría nacional",
    "NAC_270": "Hasta 270 km nacional",
    "INT_MAS500": "Internacional > 500 km",
    "INT_MENOS500": "Internacional < 500 km",
}


def clase_de(detalle: str, tipo: str) -> str:
    t = str(detalle or "").upper()
    if str(tipo).lower().startswith("int"):
        return "INT_MENOS500" if re.search(r"MENOR\s*(QUE\s*)?500", t) else "INT_MAS500"
    if "270" in t:
        return "NAC_270"
    if re.search(r"\b2\s*C\b|2C\.|2A?\s*CAT", t):
        return "NAC_2C"
    return "NAC_1C"


@dataclass
class ResultadoClasificacion:
    datos: pd.DataFrame
    descartados: pd.DataFrame
    alertas: dict[str, pd.DataFrame] = field(default_factory=dict)

    @property
    def total(self) -> float:
        return float(self.datos["MONTO"].sum())

    def resumen_alertas(self) -> list[tuple[str, int]]:
        return [(k, len(v)) for k, v in self.alertas.items() if len(v)]


def clasificar(df: pd.DataFrame, maestros: Maestros, descartadas=None) -> ResultadoClasificacion:
    descartadas = set(UNIDADES_DESCARTADAS_DEFECTO if descartadas is None else descartadas)
    # BUSCARV devuelve la primera coincidencia: se replica con drop_duplicates(keep="first").
    plan = maestros.plan.drop_duplicates("cuenta_gestion", keep="first")
    datos = df.merge(
        plan[["cuenta_gestion", "producto", "subproducto", "denominacion", "categoria", "tipo_ingreso"]],
        left_on="CUENTA_GESTION", right_on="cuenta_gestion", how="left",
    ).drop(columns=["cuenta_gestion"])
    datos = datos.rename(columns={
        "producto": "PRODUCTO", "subproducto": "SUBPRODUCTO", "denominacion": "DESCRIPCION",
        "categoria": "CATEGORIA", "tipo_ingreso": "TIPO_INGRESO",
    })
    mapa_concepto = dict(zip(maestros.conceptos["categoria"], maestros.conceptos["concepto"]))
    datos["CONCEPTO"] = datos["CATEGORIA"].map(mapa_concepto)
    datos["CONCEPTO_PROY"] = [concepto_proyeccion(c, t) for c, t in zip(datos["CONCEPTO"], datos["TIPO_INGRESO"])]
    datos["CLASE_DE"] = [
        clase_de(d, t) if c == DE else None
        for c, d, t in zip(datos["CONCEPTO"], datos["DETALLE"], datos["TIPO_INGRESO"])
    ]
    grupos = unidad_grupo(maestros.unidades)
    datos["UNIDAD_GRUPO"] = datos["UNIDAD_PRESTACION_SERVICIO"].map(lambda u: grupos.get(int(u), int(u)))

    es_descartada = datos["UNIDAD_PRESTACION_SERVICIO"].isin(descartadas)
    descartados = datos[es_descartada].reset_index(drop=True)
    datos = datos[~es_descartada].reset_index(drop=True)

    return ResultadoClasificacion(datos=datos, descartados=descartados, alertas=_alertas(datos, maestros))


def _alertas(datos: pd.DataFrame, maestros: Maestros) -> dict[str, pd.DataFrame]:
    alertas = {}
    sin_cuenta = datos[datos["CATEGORIA"].isna()]
    alertas["Cuentas sin mapeo en el plan de cuentas"] = (
        sin_cuenta.groupby(["CUENTA_GESTION", "DETALLE"], dropna=False)["MONTO"]
        .agg(filas="count", monto="sum").reset_index()
    )
    sin_concepto = datos[datos["CATEGORIA"].notna() & datos["CONCEPTO"].isna()]
    alertas["Categorías sin concepto asociado"] = (
        sin_concepto.groupby("CATEGORIA")["MONTO"].agg(filas="count", monto="sum").reset_index()
    )
    conocidas = set(maestros.unidades["unidad"].dropna().astype(int))
    if conocidas:
        desconocidas = datos[~datos["UNIDAD_PRESTACION_SERVICIO"].isin(conocidas)]
        alertas["Unidades no registradas en el maestro"] = (
            desconocidas.groupby(["UNIDAD_PRESTACION_SERVICIO", "DESC_UNID_PRESTACION_SERVICIO"])["MONTO"]
            .agg(filas="count", monto="sum").reset_index()
        )
    # Un documento puede tener varias líneas iguales (p. ej. varias operaciones con la misma tarifa);
    # solo se informan las repeticiones de monto relevante para revisión manual.
    claves = ["UNIDAD_PRESTACION_SERVICIO", "DOCUMENTO", "TIPO", "NUMERO", "FECHA_EMISION", "DETALLE", "MONTO"]
    dup = datos[datos.duplicated(subset=claves, keep=False)]
    repetidas = dup.groupby(claves, dropna=False).size().rename("lineas").reset_index()
    repetidas["monto_repetido"] = repetidas["MONTO"] * (repetidas["lineas"] - 1)
    alertas["Líneas repetidas de monto relevante (revisar)"] = (
        repetidas[repetidas["monto_repetido"].abs() >= UMBRAL_REPETIDAS]
        .sort_values("monto_repetido", key=lambda s: s.abs(), ascending=False)
        .reset_index(drop=True)
    )
    sin_fecha = datos[datos["ANIO"].isna() | datos["MES"].isna()]
    alertas["Filas sin año o mes"] = sin_fecha[["UNIDAD_PRESTACION_SERVICIO", "NUMERO", "DETALLE", "MONTO"]]
    return alertas


def montos_atipicos(actual: pd.DataFrame, historico: pd.DataFrame, umbral: float = 0.5,
                    minimo: float = 50_000_000) -> pd.DataFrame:
    """Compara cada unidad×concepto del último mes con el promedio de los 3 meses previos.

    `actual` e `historico` están en formato agregado (ver `core.historico.agregar`).
    """
    if actual.empty or historico.empty:
        return pd.DataFrame()
    claves = ["UNIDAD_GRUPO", "CONCEPTO_PROY"]
    ult = actual.assign(periodo=actual["ANIO"] * 12 + actual["MES"])
    p_max = ult["periodo"].max()
    mes_actual = ult[ult["periodo"] == p_max].groupby(claves)["MONTO"].sum()
    h = historico.assign(periodo=historico["ANIO"] * 12 + historico["MES"])
    previos = h[(h["periodo"] < p_max) & (h["periodo"] >= p_max - 3)]
    if previos.empty:
        return pd.DataFrame()
    base = previos.groupby(claves + ["periodo"])["MONTO"].sum().groupby(claves).mean()
    comp = pd.concat([mes_actual.rename("mes_actual"), base.rename("promedio_3m")], axis=1).fillna(0).reset_index()
    comp["variacion"] = (comp["mes_actual"] / comp["promedio_3m"].where(comp["promedio_3m"] != 0)) - 1
    dif = (comp["mes_actual"] - comp["promedio_3m"]).abs()
    marcar = (comp["variacion"].abs() > umbral) & (dif > minimo)
    return comp[marcar].sort_values("variacion", key=lambda s: s.abs(), ascending=False).reset_index(drop=True)


def nombres(maestros: Maestros, datos: pd.DataFrame | None = None) -> dict[int, str]:
    """Nombre de cada unidad: maestro, o descripción del SAC si no está en el maestro."""
    n = {}
    if datos is not None and not datos.empty and "DESC_UNID_PRESTACION_SERVICIO" in datos:
        for u, d in datos.groupby("UNIDAD_PRESTACION_SERVICIO")["DESC_UNID_PRESTACION_SERVICIO"].first().items():
            n[int(u)] = " ".join(str(d).split()).title()
    n.update(nombres_unidades(maestros.unidades))
    return n
