"""Carga los datos ficticios de ejemplos/ para probar la app sin datos reales."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

from . import factores, historico, maestros, trafico
from .clasificacion import clasificar
from .ingest import leer_informe

EJEMPLOS = Path(__file__).resolve().parent.parent / "ejemplos"


def disponible() -> bool:
    return (EJEMPLOS / "informe_gestion_2026_ejemplo.xlsx").exists()


def cargar() -> list[str]:
    pasos = []
    libro = EJEMPLOS / "informe_gestion_2026_ejemplo.xlsx"
    m, _ = maestros.importar_desde_libro(libro)
    maestros.guardar(m)
    pasos.append(f"Maestros: {len(m.unidades)} unidades, {len(m.plan)} cuentas.")
    for archivo in ("informe_sac_2025_ejemplo.csv", "informe_gestion_2026_ejemplo.xlsx"):
        lectura = leer_informe(EJEMPLOS / archivo)
        r = clasificar(lectura.datos, m)
        historico.guardar_ingresos(historico.agregar(r.datos))
        pasos.append(f"Ingresos {archivo}: {len(r.datos)} líneas.")
    for archivo, campos, guardar, es_op in (
        ("pasajeros_copae_ejemplo.csv", trafico.CAMPOS_PAX, historico.guardar_pax, False),
        ("operaciones_sac_ejemplo.csv", trafico.CAMPOS_OP, historico.guardar_operaciones, True),
    ):
        df = next(iter(trafico.leer_tabla(EJEMPLOS / archivo).values()))
        mapeo = trafico.sugerir_mapeo(df.columns, campos)
        res = trafico.procesar(df, mapeo, m.unidades, es_operaciones=es_op)
        guardar(res.datos)
        trafico.guardar_mapeo(df.columns, mapeo)
        pasos.append(f"{archivo}: {len(res.datos)} registros mensuales.")
    totales = pd.read_csv(EJEMPLOS / "totales_anteriores_ejemplo.csv", sep=";")
    historico.guardar_totales_anteriores(totales)
    if factores.cargar_tarifas().empty:
        factores.guardar_tarifas(pd.DataFrame([
            {"vigente_desde": "2025-01", "clase": "NAC_1C", "valor": 7100, "comentario": "Ejemplo"},
            {"vigente_desde": "2025-01", "clase": "NAC_2C", "valor": 5000, "comentario": "Ejemplo"},
            {"vigente_desde": "2025-01", "clase": "NAC_270", "valor": 2600, "comentario": "Ejemplo"},
            {"vigente_desde": "2025-01", "clase": "INT_MAS500", "valor": 25, "comentario": "Ejemplo"},
            {"vigente_desde": "2025-01", "clase": "INT_MENOS500", "valor": 7100, "comentario": "Ejemplo"},
        ]))
    sup = factores.cargar_supuestos()
    if not sup.get("ipc_anual_esperado"):
        sup["ipc_anual_esperado"] = {"2026": 0.035, "2027": 0.03}
        factores.guardar_supuestos(sup)
    pasos.append("Tarifas y supuestos de ejemplo registrados.")
    return pasos
