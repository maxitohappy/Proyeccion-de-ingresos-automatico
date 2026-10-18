"""Base histórica acumulada mes a mes (ingresos reales, PAX y operaciones).

Se guarda agregada (sin RUT ni clientes) para que crezca con cada carga mensual y
permita, con el tiempo, modelos estacionales más robustos.
"""
from __future__ import annotations

import pandas as pd

from . import almacenamiento as alm

ARCHIVO_INGRESOS = "historico/ingresos.csv"
ARCHIVO_TOTALES_ANTERIORES = "historico/totales_anteriores.csv"
ARCHIVO_PAX = "historico/pax.csv"
ARCHIVO_OPERACIONES = "historico/operaciones.csv"

CLAVES_INGRESOS = [
    "ANIO", "MES", "UNIDAD_PRESTACION_SERVICIO", "UNIDAD_GRUPO", "CONCEPTO", "TIPO_INGRESO",
    "CONCEPTO_PROY", "CATEGORIA", "DESCRIPCION", "CLASE_DE",
]
COLUMNAS_TRAFICO = ["ANIO", "MES", "UNIDAD", "TIPO", "VALOR"]


def agregar(datos: pd.DataFrame) -> pd.DataFrame:
    d = datos.copy()
    d["CLASE_DE"] = d["CLASE_DE"].fillna("")
    for c in ("CONCEPTO", "TIPO_INGRESO", "CATEGORIA", "DESCRIPCION"):
        d[c] = d[c].fillna("(sin clasificar)")
    agg = d.groupby(CLAVES_INGRESOS, dropna=False)["MONTO"].sum().reset_index()
    agg["ANIO"] = agg["ANIO"].astype(int)
    agg["MES"] = agg["MES"].astype(int)
    return agg


def _reemplazar_periodos(actual: pd.DataFrame | None, nuevo: pd.DataFrame, claves=("ANIO", "MES")) -> pd.DataFrame:
    if actual is None or actual.empty:
        return nuevo.reset_index(drop=True)
    periodos = set(map(tuple, nuevo[list(claves)].drop_duplicates().values.tolist()))
    conservar = ~actual[list(claves)].apply(tuple, axis=1).isin(periodos)
    return pd.concat([actual[conservar], nuevo], ignore_index=True).sort_values(list(claves)).reset_index(drop=True)


def cargar_ingresos() -> pd.DataFrame:
    df = alm.leer_csv(ARCHIVO_INGRESOS, dtype={"CLASE_DE": str})
    if df is None:
        return pd.DataFrame(columns=CLAVES_INGRESOS + ["MONTO"])
    df["CLASE_DE"] = df["CLASE_DE"].fillna("")
    return df


def guardar_ingresos(agg: pd.DataFrame) -> pd.DataFrame:
    """Reemplaza en la base los meses incluidos en `agg` (el informe es acumulado y trae
    regularizaciones de meses anteriores) y conserva el resto."""
    total = _reemplazar_periodos(cargar_ingresos(), agg)
    alm.escribir_csv(ARCHIVO_INGRESOS, total)
    return total


def periodos_disponibles(df: pd.DataFrame) -> list[tuple[int, int]]:
    if df.empty:
        return []
    return sorted(set(zip(df["ANIO"].astype(int), df["MES"].astype(int))))


def ultimo_periodo(df: pd.DataFrame) -> tuple[int, int] | None:
    p = periodos_disponibles(df)
    return p[-1] if p else None


# --- Totales mensuales de años anteriores (para gráficos desde 2019) -------------------

def cargar_totales_anteriores() -> pd.DataFrame:
    df = alm.leer_csv(ARCHIVO_TOTALES_ANTERIORES)
    return df if df is not None else pd.DataFrame(columns=["ANIO", "MES", "CONCEPTO_PROY", "MONTO"])


def guardar_totales_anteriores(df: pd.DataFrame) -> None:
    alm.escribir_csv(ARCHIVO_TOTALES_ANTERIORES, df)


def serie_total_mensual(ingresos: pd.DataFrame, anteriores: pd.DataFrame | None = None) -> pd.DataFrame:
    """Total mensual por año combinando la base detallada y los totales cargados a mano.
    Para un mismo año/mes manda la base detallada."""
    detalle = ingresos.groupby(["ANIO", "MES"])["MONTO"].sum().reset_index() if not ingresos.empty else None
    if anteriores is not None and not anteriores.empty:
        ant = anteriores.groupby(["ANIO", "MES"])["MONTO"].sum().reset_index()
        if detalle is not None:
            claves = set(zip(detalle["ANIO"], detalle["MES"]))
            ant = ant[~ant[["ANIO", "MES"]].apply(tuple, axis=1).isin(claves)]
            detalle = pd.concat([ant, detalle], ignore_index=True)
        else:
            detalle = ant
    if detalle is None:
        return pd.DataFrame(columns=["ANIO", "MES", "MONTO"])
    return detalle.sort_values(["ANIO", "MES"]).reset_index(drop=True)


# --- Tráfico: pasajeros y operaciones -------------------------------------------------

def _cargar_trafico(archivo: str) -> pd.DataFrame:
    df = alm.leer_csv(archivo)
    return df if df is not None else pd.DataFrame(columns=COLUMNAS_TRAFICO)


def _guardar_trafico(archivo: str, nuevo: pd.DataFrame) -> pd.DataFrame:
    total = _reemplazar_periodos(_cargar_trafico(archivo), nuevo[COLUMNAS_TRAFICO])
    alm.escribir_csv(archivo, total)
    return total


def cargar_pax() -> pd.DataFrame:
    return _cargar_trafico(ARCHIVO_PAX)


def guardar_pax(df: pd.DataFrame) -> pd.DataFrame:
    return _guardar_trafico(ARCHIVO_PAX, df)


def cargar_operaciones() -> pd.DataFrame:
    return _cargar_trafico(ARCHIVO_OPERACIONES)


def guardar_operaciones(df: pd.DataFrame) -> pd.DataFrame:
    return _guardar_trafico(ARCHIVO_OPERACIONES, df)
