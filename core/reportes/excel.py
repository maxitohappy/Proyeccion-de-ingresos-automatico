"""Excel del cuadro resumen de la proyección (instructivo, actividad 10)."""
from __future__ import annotations

import io

import pandas as pd

from ..esquema import CONCEPTOS_PROYECCION, MESES_CORTOS
from ..proyeccion import ResultadoProyeccion, origen_por_mes, resumen_anual, resumen_mensual, trafico_anual
from .texto import puntos_analisis


def _formatos(wb):
    return {
        "tit": wb.add_format({"bold": True, "font_size": 14, "font_color": "#1F3864"}),
        "sub": wb.add_format({"italic": True, "font_color": "#555555"}),
        "enc": wb.add_format({"bold": True, "bg_color": "#1F3864", "font_color": "white", "border": 1,
                              "align": "center", "valign": "vcenter", "text_wrap": True}),
        "lab": wb.add_format({"border": 1}),
        "lab_tot": wb.add_format({"border": 1, "bold": True, "bg_color": "#D9E1F2"}),
        "num": wb.add_format({"num_format": "#,##0", "border": 1}),
        "num_tot": wb.add_format({"num_format": "#,##0", "border": 1, "bold": True, "bg_color": "#D9E1F2"}),
        "mm": wb.add_format({"num_format": "#,##0.0", "border": 1}),
        "mm_tot": wb.add_format({"num_format": "#,##0.0", "border": 1, "bold": True, "bg_color": "#D9E1F2"}),
        "pct": wb.add_format({"num_format": "0.0%", "border": 1}),
        "pct_tot": wb.add_format({"num_format": "0.0%", "border": 1, "bold": True, "bg_color": "#D9E1F2"}),
        "proy": wb.add_format({"num_format": "#,##0", "border": 1, "bg_color": "#FFF2CC"}),
        "nota": wb.add_format({"font_color": "#595959", "text_wrap": True, "valign": "top"}),
    }


def _tabla(ws, f, fila: int, df: pd.DataFrame, fmt_num="num", fmt_tot="num_tot", primera_col="Concepto",
           ancho_etiqueta=38, proyectadas: set | None = None) -> int:
    ws.set_column(0, 0, ancho_etiqueta)
    ws.write(fila, 0, primera_col, f["enc"])
    for j, c in enumerate(df.columns, start=1):
        ws.write(fila, j, str(c), f["enc"])
    for i, (idx, r) in enumerate(df.iterrows(), start=1):
        total = str(idx).lower().startswith("total")
        ws.write(fila + i, 0, str(idx), f["lab_tot" if total else "lab"])
        for j, c in enumerate(df.columns, start=1):
            v = r[c]
            if pd.isna(v):
                ws.write_blank(fila + i, j, None, f["lab"])
                continue
            fmt = fmt_tot if total else ("proy" if proyectadas and c in proyectadas and fmt_num == "num" else fmt_num)
            ws.write_number(fila + i, j, float(v), f[fmt])
    return fila + len(df) + 1


def generar(res: ResultadoProyeccion, nombre: str, comparacion: pd.DataFrame | None = None,
            resumen_comparacion: pd.DataFrame | None = None, meta_anterior: dict | None = None,
            nombres_unidades: dict[int, str] | None = None, reales_anio_anterior: float | None = None) -> bytes:
    import xlsxwriter

    anio, mes = res.ultimo_cerrado
    nombres_unidades = nombres_unidades or {}
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True, "nan_inf_to_errors": True})
    f = _formatos(wb)

    # --- Resumen (MM$) ---
    ws = wb.add_worksheet("Resumen")
    ws.write(0, 0, f"Proyección de ingresos operacionales — {nombre}", f["tit"])
    ws.write(1, 0, f"Real hasta {MESES_CORTOS[mes - 1]}-{anio}; resto proyectado. Cifras en millones de pesos (MM$).", f["sub"])
    anual = resumen_anual(res) / 1e6
    columnas = [c for c in anual.columns if c >= anio]
    tabla = anual[columnas].copy()
    tabla.columns = [f"Proyectado {c}" for c in columnas]
    if len(columnas) >= 2:
        tabla[f"Var. {columnas[1]}/{columnas[0]}"] = anual[columnas[1]] / anual[columnas[0]].where(anual[columnas[0]] != 0) - 1
    ws.set_column(1, 4, 18)
    fila = _tabla(ws, f, 3, tabla.iloc[:, :len(columnas)], "mm", "mm_tot")
    if len(columnas) >= 2:
        ws.write(3, len(columnas) + 1, tabla.columns[-1], f["enc"])
        for i, v in enumerate(tabla.iloc[:, -1], start=4):
            if pd.notna(v):
                ws.write_number(i, len(columnas) + 1, float(v), f["pct_tot" if i == 3 + len(tabla) else "pct"])
    traf = trafico_anual(res)
    if not traf.empty:
        traf = traf[[c for c in traf.columns if c >= anio - 1]]
        traf.columns = [str(c) for c in traf.columns]
        ws.write(fila + 1, 0, "Tráfico (real + proyectado)", f["tit"])
        fila = _tabla(ws, f, fila + 2, traf, "num", "num", primera_col="Serie")
    puntos = puntos_analisis(res, comparacion, meta_anterior, reales_anio_anterior)
    ws.write(fila + 1, 0, "Análisis", f["tit"])
    for i, p in enumerate(puntos):
        ws.merge_range(fila + 2 + i, 0, fila + 2 + i, 5, f"• {p}", f["nota"])
        ws.set_row(fila + 2 + i, 32)

    # --- Mensual por año ---
    for a in sorted(res.ingresos["ANIO"].unique()):
        if a < anio:
            continue
        t = resumen_mensual(res, int(a))
        origen = origen_por_mes(res, int(a))
        t.columns = [f"{MESES_CORTOS[int(m) - 1]} ({'R' if origen.get(int(m)) == 'Real' else 'P'})" for m in t.columns]
        t["Total"] = t.sum(axis=1)
        ws = wb.add_worksheet(f"Mensual {a}")
        ws.write(0, 0, f"Ingresos por concepto {a} ($) — R: real, P: proyectado", f["tit"])
        ws.set_column(1, 13, 15)
        _tabla(ws, f, 2, t, proyectadas={c for c in t.columns if "(P)" in c})

    # --- Por unidad ---
    ws = wb.add_worksheet("Por unidad")
    ws.write(0, 0, "Ingresos por unidad y concepto ($)", f["tit"])
    fila = 2
    for a in sorted(res.ingresos["ANIO"].unique()):
        if a < anio:
            continue
        d = res.ingresos[res.ingresos["ANIO"] == a]
        t = d.pivot_table(index="UNIDAD", columns="CONCEPTO_PROY", values="MONTO", aggfunc="sum", fill_value=0)
        t = t.reindex(columns=[c for c in CONCEPTOS_PROYECCION if c in t.columns])
        t.columns = [CONCEPTOS_PROYECCION[c] for c in t.columns]
        t["Total"] = t.sum(axis=1)
        t = t.sort_values("Total", ascending=False)
        t.index = [f"{u} {nombres_unidades.get(int(u), '')}".strip() for u in t.index]
        t.loc["Total"] = t.sum()
        ws.write(fila, 0, f"Año {a}", f["tit"])
        ws.set_column(1, 9, 16)
        fila = _tabla(ws, f, fila + 1, t, primera_col="Unidad", ancho_etiqueta=40) + 2

    # --- Factores ---
    ws = wb.add_worksheet("Factores")
    ws.write(0, 0, "Factores económicos y tarifas utilizados", f["tit"])
    cols = ["dolar_usado", "dolar_fuente", "ipc"] + [c for c in res.factores.columns if c.startswith("tarifa_")]
    fac = res.factores[[c for c in cols if c in res.factores.columns]].copy()
    fac = fac[fac.index >= f"{anio - 1:04d}-01"]
    encabezados = ["Período", "Dólar", "Fuente dólar", "IPC mensual (%)"] + [c.replace("tarifa_", "Tarifa ") for c in fac.columns[3:]]
    for j, e in enumerate(encabezados):
        ws.write(2, j, e, f["enc"])
    ws.set_column(0, len(encabezados), 16)
    for i, (per, r) in enumerate(fac.iterrows(), start=3):
        ws.write(i, 0, per, f["lab"])
        for j, c in enumerate(fac.columns, start=1):
            v = r[c]
            if isinstance(v, str):
                ws.write(i, j, v, f["lab"])
            elif pd.notna(v):
                ws.write_number(i, j, float(v), f["mm"] if c in ("dolar_usado", "ipc") else f["num"])

    # --- Variaciones ---
    if resumen_comparacion is not None and not resumen_comparacion.empty:
        ws = wb.add_worksheet("Variación vs anterior")
        ws.write(0, 0, f"Diferencias respecto a la proyección anterior — {anio} ($)", f["tit"])
        ws.set_column(1, 9, 17)
        _tabla(ws, f, 2, resumen_comparacion)
    wb.close()
    return buf.getvalue()
