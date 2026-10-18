"""Utilidades de interfaz compartidas por las páginas."""
from __future__ import annotations

import io
import os

import pandas as pd
import streamlit as st

from core import historico, maestros
from core.esquema import MESES

EN_NAVEGADOR = bool(os.environ.get("PROYECCION_EN_NAVEGADOR"))

# Paleta validada (ver skill dataviz): año actual, proyectado, año anterior, referencia.
COLOR_ACTUAL = "#2a78d6"
COLOR_PROYECTADO = "#86b6ef"
COLOR_ANTERIOR = "#eb6834"
COLOR_REFERENCIA = "#1baf7a"
COLOR_NEGATIVO = "#eb6834"


def numero(v, decimales: int = 0) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return f"{v:,.{decimales}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def porcentaje(v, decimales: int = 1) -> str:
    if v is None or pd.isna(v):
        return ""
    return f"{v * 100:,.{decimales}f}%".replace(".", ",")


def mostrar(df: pd.DataFrame, decimales: int = 0, millones: bool = False, porcentajes: list[str] | None = None,
            altura: int | None = None, **kwargs):
    """Muestra un DataFrame con formato chileno (punto de miles, coma decimal)."""
    if df is None or df.empty:
        st.info("Sin datos para mostrar.")
        return
    d = df.copy()
    porcentajes = porcentajes or []
    numericas = [c for c in d.columns if pd.api.types.is_numeric_dtype(d[c]) and c not in porcentajes]
    if millones:
        d[numericas] = d[numericas] / 1e6
    formatos = {c: (lambda v, dd=decimales: numero(v, dd)) for c in numericas}
    formatos.update({c: porcentaje for c in porcentajes if c in d.columns})
    estilo = d.style.format(formatos)
    if altura:
        kwargs["height"] = altura
    st.dataframe(estilo, width="stretch", **kwargs)


def excel_de_tablas(tablas: dict[str, pd.DataFrame]) -> bytes:
    buf = io.BytesIO()
    with pd.ExcelWriter(buf, engine="xlsxwriter") as xw:
        for nombre, df in tablas.items():
            if df is not None and not df.empty:
                df.to_excel(xw, sheet_name=nombre[:31])
    return buf.getvalue()


def aviso_privacidad():
    if EN_NAVEGADOR:
        st.sidebar.caption("🔒 Tus archivos se procesan **solo en este navegador**: no se envían a ningún servidor. "
                           "Los datos guardados quedan en este equipo (respáldalos en *Maestros y respaldo*).")
    else:
        st.sidebar.caption("🔒 Modo local: los datos quedan en la carpeta `data/` de este equipo.")


def texto_periodo(p) -> str:
    return f"{MESES[p[1] - 1]} {p[0]}" if p else "—"


def estado() -> dict:
    """Estado del proceso del mes para la portada y las validaciones de cada página."""
    m = maestros.cargar()
    ing = historico.cargar_ingresos()
    pax = historico.cargar_pax()
    ops = historico.cargar_operaciones()
    return {
        "maestros": m,
        "maestros_ok": m.completos,
        "ingresos": ing,
        "ultimo_ingreso": historico.ultimo_periodo(ing),
        "anios_ingresos": sorted(ing["ANIO"].unique().tolist()) if not ing.empty else [],
        "pax": pax,
        "ultimo_pax": historico.ultimo_periodo(pax),
        "ops": ops,
        "ultimo_ops": historico.ultimo_periodo(ops),
    }


def requiere_maestros(e: dict) -> bool:
    if not e["maestros_ok"]:
        st.warning("Primero importa los maestros (plan de cuentas y unidades) en **Maestros y respaldo**, "
                   "o carga los datos de ejemplo desde la portada.")
        st.page_link("paginas/maestros.py", label="Ir a Maestros y respaldo", icon=":material/database:")
        return False
    return True


def requiere_ingresos(e: dict) -> bool:
    if e["ingresos"].empty:
        st.warning("Aún no hay ingresos reales en la base. Carga el Informe de Gestión del SAC.")
        st.page_link("paginas/carga_informe.py", label="Ir a Cargar informe de gestión", icon=":material/upload_file:")
        return False
    return True


def nombres_unidades(e: dict) -> dict[int, str]:
    return maestros.nombres_unidades(e["maestros"].unidades)


def editor(df: pd.DataFrame, clave: str, **kwargs) -> pd.DataFrame:
    """`st.data_editor` compatible con stlite.

    En stlite 1.9.2, un data_editor con `key` y filas fijas falla (NameError: arrow_table). En el
    navegador se omite `key` y se agrega una columna oculta con la clave para que cada editor tenga
    una identidad única.
    """
    if EN_NAVEGADOR and kwargs.get("num_rows", "fixed") == "fixed":
        d = df.copy()
        d["_editor"] = clave
        config = dict(kwargs.pop("column_config", None) or {})
        config["_editor"] = None
        if isinstance(kwargs.get("disabled"), list):
            kwargs["disabled"] = kwargs["disabled"] + ["_editor"]
        return st.data_editor(d, column_config=config, **kwargs).drop(columns="_editor")
    return st.data_editor(df, key=clave, **kwargs)
