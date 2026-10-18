"""Configuración persistente y cálculo (con caché en la sesión) de la proyección."""
from __future__ import annotations

import hashlib
import json

import streamlit as st

from core import almacenamiento as alm
from core import factores
from core import proyeccion as pr

ARCHIVO_CONFIG = "config/proyeccion.json"


def cargar_config() -> dict:
    return pr.config_completa(alm.leer_json(ARCHIVO_CONFIG, {}))


def guardar_config(config: dict) -> None:
    alm.escribir_json(ARCHIVO_CONFIG, config)


def _firma(e: dict, config: dict) -> str:
    partes = [json.dumps(config, sort_keys=True, default=str)]
    for clave in ("ingresos", "pax", "ops"):
        df = e[clave]
        col = "MONTO" if clave == "ingresos" else "VALOR"
        partes.append(f"{len(df)}:{float(df[col].sum()) if not df.empty else 0}")
    partes.append(json.dumps(factores.cargar_supuestos(), sort_keys=True))
    partes.append(factores.cargar_tarifas().to_json())
    partes.append(factores.cargar_manuales().to_json())
    partes.append(str(factores.cargar_web().get("actualizado")))
    return hashlib.md5("|".join(partes).encode()).hexdigest()


def calcular(e: dict, config: dict | None = None, forzar: bool = False) -> pr.ResultadoProyeccion:
    config = config or cargar_config()
    firma = _firma(e, config)
    if not forzar and st.session_state.get("proy_firma") == firma:
        return st.session_state["proy_resultado"]
    res = pr.proyectar_ingresos(e["ingresos"], e["maestros"].unidades, e["pax"], e["ops"], config)
    st.session_state["proy_firma"] = firma
    st.session_state["proy_resultado"] = res
    return res
