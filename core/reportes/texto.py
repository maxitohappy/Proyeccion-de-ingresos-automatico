"""Textos de análisis generados a partir de la proyección (para el PPT y el correo)."""
from __future__ import annotations

import pandas as pd

from ..esquema import MESES
from ..proyeccion import ResultadoProyeccion


def mm(valor: float, decimales: int = 0) -> str:
    """Millones de pesos con formato chileno: 'MM$ 211.660'."""
    texto = f"{valor / 1e6:,.{decimales}f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"MM$ {texto}"


def num(valor: float, decimales: int = 0) -> str:
    return f"{valor:,.{decimales}f}".replace(",", "X").replace(".", ",").replace("X", ".")


def pct(valor: float, decimales: int = 1) -> str:
    return f"{valor * 100:,.{decimales}f}%".replace(".", ",")


def puntos_analisis(res: ResultadoProyeccion, comparacion: pd.DataFrame | None = None,
                    meta_anterior: dict | None = None, reales_anio_anterior: float | None = None) -> list[str]:
    anio, mes = res.ultimo_cerrado
    total = res.total_anual(anio)
    puntos = [f"Para el año {anio} se proyectan ingresos operacionales por {mm(total)} "
              f"(real a {MESES[mes - 1].lower()} + proyección del resto del año)."]
    if reales_anio_anterior:
        puntos.append(f"Esto equivale a una variación de {pct(total / reales_anio_anterior - 1)} respecto a los "
                      f"ingresos reales de {anio - 1} ({mm(reales_anio_anterior)}).")
    if anio + 1 in set(res.ingresos["ANIO"]):
        puntos.append(f"Para {anio + 1} se proyectan {mm(res.total_anual(anio + 1))} "
                      f"({pct(res.total_anual(anio + 1) / total - 1)} respecto a {anio}).")
    if comparacion is not None and meta_anterior:
        anterior = float(meta_anterior.get("totales", {}).get(str(anio), 0) or 0)
        if anterior:
            dif = total - anterior
            puntos.append(f"Respecto a la proyección anterior ({meta_anterior.get('nombre')}), el total {anio} "
                          f"{'aumenta' if dif >= 0 else 'disminuye'} {mm(abs(dif))} ({pct(dif / anterior)}).")
        cerrados = comparacion[comparacion["ESTADO"] == "Cerrado desde la proyección anterior"]
        if not cerrados.empty:
            r0, r1 = cerrados["R0"].sum(), cerrados["R1"].sum()
            meses_txt = ", ".join(sorted({MESES[int(m) - 1].lower() for m in cerrados["MES"]}))
            puntos.append(f"Los ingresos reales de {meses_txt} fueron {mm(r1)}, {mm(abs(r1 - r0))} "
                          f"{'más' if r1 >= r0 else 'menos'} de lo proyectado ({pct(r1 / r0 - 1) if r0 else '-'}).")
        efectos = comparacion[comparacion["ANIO"] == anio][
            ["Pasajeros", "Operaciones", "Dólar", "Tarifa, IPC y otros", "Otros conceptos"]].sum()
        efectos = efectos[efectos.abs() > 0.5e6].sort_values(key=lambda s: s.abs(), ascending=False)
        if not efectos.empty:
            detalle = "; ".join(f"{k.lower()}: {'+' if v >= 0 else '−'}{mm(abs(v))}" for k, v in efectos.items())
            puntos.append(f"Origen de las diferencias {anio}: {detalle}.")
    f = res.factores
    futuros = f[f.index > f"{anio:04d}-{mes:02d}"]
    if not futuros.empty and futuros["dolar_usado"].notna().any():
        puntos.append(f"Dólar utilizado para el resto de {anio}: ${num(futuros['dolar_usado'].iloc[0])} "
                      f"({futuros['dolar_fuente'].iloc[0]}).")
    if not res.trafico.empty:
        pax = res.trafico[(res.trafico["ANIO"] == anio) & res.trafico["SERIE"].str.startswith("PAX")]
        if not pax.empty:
            puntos.append(f"Pasajeros embarcados proyectados {anio}: {num(pax['VALOR'].sum())}.")
    return puntos
