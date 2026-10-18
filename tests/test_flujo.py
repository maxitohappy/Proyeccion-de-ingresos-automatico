"""Flujo mensual completo con los datos ficticios de ejemplos/."""
import pandas as pd
import pytest

from conftest import EJEMPLOS
from core import control, historico, maestros, tablas, trafico
from core import proyeccion as pr
from core.clasificacion import clasificar
from core.ingest import leer_informe


@pytest.fixture
def base():
    m, avisos = maestros.importar_desde_libro(EJEMPLOS / "informe_gestion_2026_ejemplo.xlsx")
    maestros.guardar(m)
    for archivo in ("informe_sac_2025_ejemplo.csv", "informe_gestion_2026_ejemplo.xlsx"):
        lectura = leer_informe(EJEMPLOS / archivo)
        r = clasificar(lectura.datos, m)
        historico.guardar_ingresos(historico.agregar(r.datos))
    return m


def test_lectura_y_clasificacion():
    m, _ = maestros.importar_desde_libro(EJEMPLOS / "informe_gestion_2026_ejemplo.xlsx")
    lectura = leer_informe(EJEMPLOS / "informe_gestion_2026_ejemplo.xlsx")
    assert lectura.hoja == "2026"
    r = clasificar(lectura.datos, m)
    assert len(r.descartados) > 0 and (r.descartados["UNIDAD_PRESTACION_SERVICIO"] == 5220).all()
    assert r.datos["CATEGORIA"].notna().all()
    assert r.total == pytest.approx(lectura.datos["MONTO"].sum() - r.descartados["MONTO"].sum())
    # La unidad 9302 se asocia a 9301.
    assert set(r.datos.loc[r.datos["UNIDAD_PRESTACION_SERVICIO"] == 9302, "UNIDAD_GRUPO"]) == {9301}
    agg = historico.agregar(r.datos)
    t = tablas.por_concepto_proyeccion(agg, 2026)
    assert t.loc["Total", "Total"] == pytest.approx(r.total)


def test_csv_y_excel_dan_lo_mismo(tmp_path):
    lectura = leer_informe(EJEMPLOS / "informe_sac_2025_ejemplo.csv")
    assert lectura.filas_leidas > 0
    assert set(lectura.datos["ANIO"].unique()) == {2025}
    assert lectura.datos["FECHA_EMISION"].notna().all()


def test_trafico_y_proyeccion(base):
    hojas = trafico.leer_tabla(EJEMPLOS / "pasajeros_copae_ejemplo.csv")
    df = next(iter(hojas.values()))
    mapeo = trafico.sugerir_mapeo(df.columns, trafico.CAMPOS_PAX)
    assert mapeo["unidad"] == "Aeródromo" and mapeo["cantidad"] == "Pasajeros"
    rp = trafico.procesar(df, mapeo, base.unidades)
    assert rp.no_reconocidas.empty
    historico.guardar_pax(rp.datos)

    hojas = trafico.leer_tabla(EJEMPLOS / "operaciones_sac_ejemplo.csv")
    df = next(iter(hojas.values()))
    mapeo = trafico.sugerir_mapeo(df.columns, trafico.CAMPOS_OP)
    ro = trafico.procesar(df, mapeo, base.unidades, es_operaciones=True)
    assert "Despegues u otras operaciones" in ro.excluidas
    assert "Aeronaves de Estado / clubes aéreos" in ro.excluidas
    historico.guardar_operaciones(ro.datos)

    ingresos = historico.cargar_ingresos()
    res = pr.proyectar_ingresos(ingresos, base.unidades, historico.cargar_pax(), historico.cargar_operaciones())
    assert res.ultimo_cerrado == (2026, 9)
    proy = res.ingresos[res.ingresos["ORIGEN"] == "Proyectado"]
    assert set(proy["ANIO"]) == {2026, 2027}
    metodos = proy.loc[proy["CONCEPTO_PROY"] == "DE_NAC", "METODO"].unique()
    assert any("Pasajeros" in m for m in metodos)
    real_2025 = ingresos.loc[ingresos["ANIO"] == 2025, "MONTO"].sum()
    total_2026 = res.total_anual(2026)
    # Los datos de ejemplo crecen ~6 %: la proyección debe quedar en ese orden.
    assert 1.0 < total_2026 / real_2025 < 1.15

    # Snapshot, nuevo escenario y descomposición exacta de diferencias.
    sid = control.guardar_snapshot(res, "Base")
    anterior = control.cargar_snapshot(sid)["ingresos"]
    res2 = pr.proyectar_ingresos(ingresos, base.unidades, historico.cargar_pax(), historico.cargar_operaciones(),
                                 config={"escenario": {"pax": 0.05, "dolar": -0.1}})
    comp = control.comparar(res2.ingresos, anterior)
    suma_efectos = comp[control.EFECTOS].sum(axis=1)
    assert (suma_efectos - comp["DIFERENCIA"]).abs().max() < 1e-3
    resumen = control.resumen_efectos(comp, 2027)
    assert resumen.loc["Total", "Pasajeros"] > 0
    assert resumen.loc["Total", "Dólar"] < 0


def test_ajuste_manual(base):
    ingresos = historico.cargar_ingresos()
    ajuste = {"unidad": 9101, "concepto": "CONCESIONES", "periodo": "2026-12", "valor": 123.0, "comentario": "prueba"}
    res = pr.proyectar_ingresos(ingresos, base.unidades, config={"ajustes": [ajuste]})
    fila = res.ingresos[(res.ingresos["UNIDAD"] == 9101) & (res.ingresos["CONCEPTO_PROY"] == "CONCESIONES")
                        & (res.ingresos["ANIO"] == 2026) & (res.ingresos["MES"] == 12)]
    assert fila["MONTO"].iloc[0] == 123.0 and fila["ORIGEN"].iloc[0] == "Ajuste manual"


def test_respaldo(base):
    from core import almacenamiento as alm
    contenido = alm.exportar_respaldo()
    n_archivos = len(alm.listar())
    for rel in alm.listar():
        alm.eliminar(rel)
    assert alm.importar_respaldo(contenido) == n_archivos
    assert not historico.cargar_ingresos().empty


def test_reportes(base):
    import io

    import openpyxl
    from pptx import Presentation

    from core.reportes import excel, ppt

    ingresos = historico.cargar_ingresos()
    res = pr.proyectar_ingresos(ingresos, base.unidades)
    sid = control.guardar_snapshot(res, "Anterior")
    snap = control.cargar_snapshot(sid)
    res2 = pr.proyectar_ingresos(ingresos, base.unidades, config={"escenario": {"dolar": 0.05}})
    comp = control.comparar(res2.ingresos, snap["ingresos"])
    resumen = control.resumen_efectos(comp, 2026)
    xls = excel.generar(res2, "Prueba", comp, resumen, snap["meta"], {9101: "Norte"},
                        ingresos.loc[ingresos["ANIO"] == 2025, "MONTO"].sum())
    wb = openpyxl.load_workbook(io.BytesIO(xls))
    assert {"Resumen", "Mensual 2026", "Mensual 2027", "Por unidad", "Factores", "Variación vs anterior"} <= set(wb.sheetnames)
    serie = historico.serie_total_mensual(ingresos, historico.cargar_totales_anteriores())
    pptx = ppt.generar(res2, "Prueba", serie, None, comp, resumen, snap["meta"],
                       pd.DataFrame({"PAX 2026": ["1.000"]}, index=["Norte"]))
    prs = Presentation(io.BytesIO(pptx))
    assert len(prs.slides) >= 7
