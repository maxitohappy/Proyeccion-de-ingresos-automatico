"""Presentación de la proyección (instructivo, actividad 12) con gráficos nativos editables."""
from __future__ import annotations

import io

import pandas as pd

from ..esquema import CONCEPTOS_PROYECCION, MESES, MESES_CORTOS
from ..proyeccion import ResultadoProyeccion, resumen_anual
from .texto import mm, num, pct, puntos_analisis

AZUL_OSCURO = "1F3864"
SERIE_ACTUAL = "2A78D6"       # año en curso (real)
SERIE_PROYECTADA = "86B6EF"   # año en curso (proyectado)
SERIE_ANTERIOR = "EB6834"     # año anterior
SERIE_REFERENCIA = "1BAF7A"   # año de referencia (ej. 2019)
GRIS = "52514E"


def _rgb(h):
    from pptx.dml.color import RGBColor
    return RGBColor.from_string(h)


def _titulo(slide, texto, sub=None):
    from pptx.util import Inches, Pt
    tb = slide.shapes.add_textbox(Inches(0.5), Inches(0.3), Inches(12.3), Inches(0.8))
    p = tb.text_frame.paragraphs[0]
    p.text = texto
    p.font.size, p.font.bold, p.font.color.rgb = Pt(26), True, _rgb(AZUL_OSCURO)
    if sub:
        p2 = tb.text_frame.add_paragraph()
        p2.text = sub
        p2.font.size, p2.font.color.rgb = Pt(13), _rgb(GRIS)


def _tabla(slide, df: pd.DataFrame, x, y, ancho, alto, primera="", fmt=lambda v: num(v)):
    from pptx.util import Pt
    filas, cols = len(df) + 1, len(df.columns) + 1
    t = slide.shapes.add_table(filas, cols, x, y, ancho, alto).table
    t.cell(0, 0).text = primera
    for j, c in enumerate(df.columns, start=1):
        t.cell(0, j).text = str(c)
    for i, (idx, r) in enumerate(df.iterrows(), start=1):
        t.cell(i, 0).text = str(idx)
        for j, c in enumerate(df.columns, start=1):
            v = r[c]
            t.cell(i, j).text = "" if pd.isna(v) else (v if isinstance(v, str) else fmt(v))
    for i in range(filas):
        for j in range(cols):
            celda = t.cell(i, j)
            for p in celda.text_frame.paragraphs:
                p.font.size = Pt(11)
                p.font.bold = i == 0 or str(t.cell(i, 0).text).startswith("Total")
    return t


def _estilo_grafico(chart, leyenda=True):
    from pptx.enum.chart import XL_LEGEND_POSITION
    from pptx.util import Pt
    chart.has_legend = leyenda
    if leyenda:
        chart.legend.position = XL_LEGEND_POSITION.TOP
        chart.legend.include_in_layout = False
        chart.legend.font.size = Pt(11)
    chart.font.size = Pt(10)
    try:
        va = chart.value_axis
        va.has_major_gridlines = True
        va.major_gridlines.format.line.color.rgb = _rgb("E0E0DC")
        va.format.line.fill.background()
        va.tick_labels.font.color.rgb = _rgb(GRIS)
        chart.category_axis.tick_labels.font.color.rgb = _rgb(GRIS)
    except (AttributeError, ValueError):
        pass


def generar(res: ResultadoProyeccion, nombre: str, serie_total: pd.DataFrame,
            anio_referencia: int | None = None, comparacion: pd.DataFrame | None = None,
            resumen_comparacion: pd.DataFrame | None = None, meta_anterior: dict | None = None,
            pax_por_unidad: pd.DataFrame | None = None, reales_anio_anterior: float | None = None) -> bytes:
    """`serie_total`: ANIO, MES, MONTO con los reales de años anteriores (base + totales cargados)."""
    from pptx import Presentation
    from pptx.chart.data import CategoryChartData
    from pptx.enum.chart import XL_CHART_TYPE
    from pptx.util import Inches, Pt

    anio, mes = res.ultimo_cerrado
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    vacia = prs.slide_layouts[6]

    # 1. Portada
    s = prs.slides.add_slide(vacia)
    fondo = s.shapes.add_shape(1, 0, 0, prs.slide_width, prs.slide_height)
    fondo.fill.solid()
    fondo.fill.fore_color.rgb = _rgb(AZUL_OSCURO)
    fondo.line.fill.background()
    tb = s.shapes.add_textbox(Inches(0.8), Inches(2.6), Inches(11.5), Inches(2.5))
    p = tb.text_frame.paragraphs[0]
    p.text = "Proyección de Ingresos Operacionales"
    p.font.size, p.font.bold, p.font.color.rgb = Pt(40), True, _rgb("FFFFFF")
    for texto, tam in ((nombre, 24), (f"Real a {MESES[mes - 1].lower()} {anio} · proyección {anio}–{anio + 1}", 16)):
        q = tb.text_frame.add_paragraph()
        q.text, q.font.size, q.font.color.rgb = texto, Pt(tam), _rgb("D9E1F2")

    # 2. Resumen y análisis
    s = prs.slides.add_slide(vacia)
    _titulo(s, "Resumen de la proyección", "Millones de pesos (MM$)")
    anual = resumen_anual(res)
    cols = [c for c in anual.columns if c >= anio]
    tabla = anual[cols] / 1e6
    tabla.columns = [f"{c}" for c in cols]
    _tabla(s, tabla, Inches(0.5), Inches(1.4), Inches(6.2), Inches(3.6), "Concepto (MM$)", fmt=lambda v: num(v, 0))
    tb = s.shapes.add_textbox(Inches(7.0), Inches(1.4), Inches(5.9), Inches(5.5))
    tb.text_frame.word_wrap = True
    for i, punto in enumerate(puntos_analisis(res, comparacion, meta_anterior, reales_anio_anterior)):
        q = tb.text_frame.paragraphs[0] if i == 0 else tb.text_frame.add_paragraph()
        q.text, q.font.size, q.space_after = f"• {punto}", Pt(13), Pt(6)

    # 3. Mensual: real vs proyectado vs años anteriores
    mensual_actual = res.ingresos[res.ingresos["ANIO"] == anio].groupby("MES")["MONTO"].sum()
    anterior = serie_total[serie_total["ANIO"] == anio - 1].set_index("MES")["MONTO"]
    referencia = (serie_total[serie_total["ANIO"] == anio_referencia].set_index("MES")["MONTO"]
                  if anio_referencia else pd.Series(dtype=float))
    s = prs.slides.add_slide(vacia)
    _titulo(s, "Ingresos mensuales: real y proyectado",
            f"MM$ · total {anio}: {mm(mensual_actual.sum())} (real + proyectado)")
    cd = CategoryChartData()
    cd.categories = MESES_CORTOS
    series_colores = []
    if anio_referencia and not referencia.empty:
        cd.add_series(str(anio_referencia), [referencia.get(m, 0) / 1e6 for m in range(1, 13)])
        series_colores.append(SERIE_REFERENCIA)
    if not anterior.empty:
        cd.add_series(str(anio - 1), [anterior.get(m, 0) / 1e6 for m in range(1, 13)])
        series_colores.append(SERIE_ANTERIOR)
    cd.add_series(f"{anio} real", [mensual_actual.get(m) / 1e6 if m <= mes else None for m in range(1, 13)])
    series_colores.append(SERIE_ACTUAL)
    cd.add_series(f"{anio} proyectado", [mensual_actual.get(m) / 1e6 if m > mes else None for m in range(1, 13)])
    series_colores.append(SERIE_PROYECTADA)
    gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.5), Inches(1.4), Inches(12.3), Inches(5.7), cd)
    ch = gf.chart
    _estilo_grafico(ch)
    ch.plots[0].gap_width, ch.plots[0].overlap = 60, -10 if len(series_colores) > 2 else 0
    for serie, color in zip(ch.series, series_colores):
        serie.format.fill.solid()
        serie.format.fill.fore_color.rgb = _rgb(color)
    ch.value_axis.tick_labels.number_format = '#,##0'
    ch.value_axis.tick_labels.number_format_is_linked = False

    # 4. Acumulado
    s = prs.slides.add_slide(vacia)
    _titulo(s, "Ingresos acumulados en el año", "MM$ acumulados a cada mes")
    cd = CategoryChartData()
    cd.categories = MESES_CORTOS
    colores = []
    if anio_referencia and not referencia.empty:
        cd.add_series(str(anio_referencia), list((referencia.reindex(range(1, 13)).fillna(0).cumsum() / 1e6).values))
        colores.append(SERIE_REFERENCIA)
    if not anterior.empty:
        cd.add_series(str(anio - 1), list((anterior.reindex(range(1, 13)).fillna(0).cumsum() / 1e6).values))
        colores.append(SERIE_ANTERIOR)
    cd.add_series(f"{anio} (real + proyectado)", list((mensual_actual.reindex(range(1, 13)).fillna(0).cumsum() / 1e6).values))
    colores.append(SERIE_ACTUAL)
    gf = s.shapes.add_chart(XL_CHART_TYPE.LINE_MARKERS, Inches(0.5), Inches(1.4), Inches(12.3), Inches(5.7), cd)
    ch = gf.chart
    _estilo_grafico(ch)
    for serie, color in zip(ch.series, colores):
        serie.format.line.color.rgb = _rgb(color)
        serie.format.line.width = Pt(2.25)
        serie.smooth = False
        serie.marker.format.fill.solid()
        serie.marker.format.fill.fore_color.rgb = _rgb(color)
        serie.marker.format.line.color.rgb = _rgb("FFFFFF")
    ch.value_axis.tick_labels.number_format = '#,##0'
    ch.value_axis.tick_labels.number_format_is_linked = False

    # 5. % de recuperación respecto al año de referencia
    base_rec = referencia if (anio_referencia and not referencia.empty) else anterior
    etiqueta_ref = str(anio_referencia) if (anio_referencia and not referencia.empty) else str(anio - 1)
    if not base_rec.empty:
        s = prs.slides.add_slide(vacia)
        _titulo(s, f"Ingresos {anio} como % de {etiqueta_ref}",
                f"Total anual proyectado: {pct(mensual_actual.sum() / base_rec.sum())} de {etiqueta_ref}")
        ratios = [mensual_actual.get(m, 0) / base_rec.get(m) if base_rec.get(m) else 0 for m in range(1, 13)]
        cd = CategoryChartData()
        cd.categories = MESES_CORTOS
        cd.add_series(f"% de {etiqueta_ref}", ratios)
        gf = s.shapes.add_chart(XL_CHART_TYPE.COLUMN_CLUSTERED, Inches(0.5), Inches(1.4), Inches(12.3), Inches(5.7), cd)
        ch = gf.chart
        _estilo_grafico(ch, leyenda=False)
        ch.plots[0].gap_width = 60
        ch.plots[0].has_data_labels = True
        ch.plots[0].data_labels.number_format = '0%'
        ch.plots[0].data_labels.number_format_is_linked = False
        ch.plots[0].data_labels.font.size = Pt(10)
        serie = ch.series[0]
        for i, punto in enumerate(serie.points):
            punto.format.fill.solid()
            punto.format.fill.fore_color.rgb = _rgb(SERIE_ACTUAL if i < mes else SERIE_PROYECTADA)
        ch.value_axis.tick_labels.number_format = '0%'
        ch.value_axis.tick_labels.number_format_is_linked = False

    # 6. Mensual por concepto
    s = prs.slides.add_slide(vacia)
    _titulo(s, f"Ingresos {anio} por concepto y mes", "MM$ · columnas sombreadas = proyectado")
    d = res.ingresos[res.ingresos["ANIO"] == anio]
    t = d.pivot_table(index="CONCEPTO_PROY", columns="MES", values="MONTO", aggfunc="sum", fill_value=0) / 1e6
    t = t.reindex([c for c in CONCEPTOS_PROYECCION if c in t.index])
    t.index = [CONCEPTOS_PROYECCION[c] for c in t.index]
    t.loc["Total"] = t.sum()
    t.columns = [f"{MESES_CORTOS[m - 1]}{'*' if m > mes else ''}" for m in t.columns]
    t["Total"] = t.sum(axis=1)
    _tabla(s, t, Inches(0.3), Inches(1.4), Inches(12.7), Inches(3.8), "Concepto", fmt=lambda v: num(v, 0))

    # 7. Variación vs proyección anterior
    if resumen_comparacion is not None and not resumen_comparacion.empty and meta_anterior:
        s = prs.slides.add_slide(vacia)
        _titulo(s, "Diferencias respecto a la proyección anterior",
                f"{meta_anterior.get('nombre')} → proyección actual · año {anio} · MM$")
        efectos = resumen_comparacion.loc["Total", ["Pasajeros", "Operaciones", "Dólar", "Tarifa, IPC y otros",
                                                    "Otros conceptos"]] / 1e6
        cd = CategoryChartData()
        cd.categories = list(efectos.index)
        cd.add_series("Efecto (MM$)", list(efectos.values))
        gf = s.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, Inches(0.5), Inches(1.4), Inches(6.5), Inches(5.5), cd)
        ch = gf.chart
        _estilo_grafico(ch, leyenda=False)
        ch.plots[0].has_data_labels = True
        ch.plots[0].data_labels.number_format = '#,##0'
        ch.plots[0].data_labels.number_format_is_linked = False
        for i, punto in enumerate(ch.series[0].points):
            punto.format.fill.solid()
            punto.format.fill.fore_color.rgb = _rgb(SERIE_ACTUAL if efectos.iloc[i] >= 0 else SERIE_ANTERIOR)
        tabla = resumen_comparacion[["Proyección anterior", "Proyección actual", "Diferencia"]] / 1e6
        _tabla(s, tabla, Inches(7.3), Inches(1.4), Inches(5.6), Inches(3.6), "Concepto (MM$)", fmt=lambda v: num(v, 0))

    # 8. PAX por unidad
    if pax_por_unidad is not None and not pax_por_unidad.empty:
        s = prs.slides.add_slide(vacia)
        _titulo(s, "Pasajeros por unidad", "Comparación con el año de referencia")
        filas = min(len(pax_por_unidad), 18)
        _tabla(s, pax_por_unidad.head(filas), Inches(0.5), Inches(1.4), Inches(12.3), Inches(0.3 * (filas + 1)),
               "Unidad")  # la tabla llega con los textos ya formateados

    buf = io.BytesIO()
    prs.save(buf)
    return buf.getvalue()
