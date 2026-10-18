"""Pruebas del simulador por unidad.

`test_reproduce_planilla_de_referencia` compara contra una planilla real de simulación cuyos
datos NO se publican: se lee de tests/datos_locales/ (excluido del repositorio) y se omite si
no existe. Las demás pruebas usan números ficticios.
"""
import io
import json
from pathlib import Path

import openpyxl
import pytest

from core.simulador import SupuestosSimulacion, calcular, exportar_excel

REFERENCIA = Path(__file__).parent / "datos_locales" / "referencia_simulacion.json"


def ficticio():
    return SupuestosSimulacion(
        nombre="Aeródromo ficticio",
        anio_base=2026,
        anio_final=2028,
        pax_nac={2025: [1000] * 12, 2026: [1100] * 6 + [None] * 6},
        pax_int={2025: [10] * 12, 2026: [None] * 12},
        crec_nac={2026: 0.10, 2027: 0.05, 2028: 0.0},
        crec_int={2026: 0.0, 2027: 0.0, 2028: 0.0},
        ipc={2026: 0.04, 2027: 0.03, 2028: 0.03},
        tarifa_nac=5000,
        tarifa_int_usd={2026: 25, 2027: 25, 2028: 25},
        tipo_cambio={2026: 900, 2027: 900, 2028: 900},
        ingresos_base={"CONCESIONES": 1_000_000, "TASAS": 2_000_000, "COMBUSTIBLE": 0, "OTROS": 0},
        ingresos_historicos={2025: {"DE_NAC": 1, "DE_INT": 2, "CONCESIONES": 3, "TASAS": 4, "COMBUSTIBLE": 5, "OTROS": 6}},
        tpe=[4000],
        anio_inicio_tpe=2027,
    )


def test_calculo_ficticio():
    r = calcular(ficticio())
    # 2026: 6 meses reales de 1.100 + 6 meses proyectados = 1.000 × 1,10
    assert r.pax_anual.loc["Nacional", 2026] == pytest.approx(13200)
    assert r.pax_anual.loc["Nacional", 2027] == pytest.approx(13200 * 1.05)
    assert r.pax_anual.loc["Internacional", 2026] == pytest.approx(120)
    assert r.ingresos.loc["D° Embarque Nacional", 2026] == pytest.approx(13200 * 5000)
    assert r.ingresos.loc["D° Embarque Nacional", 2027] == pytest.approx(13200 * 1.05 * 5000 * 1.03)
    assert r.ingresos.loc["D° Embarque Internacional", 2026] == pytest.approx(120 * 25 * 900)
    assert r.ingresos.loc["Tasas Aeronáuticas", 2028] == pytest.approx(2_000_000 * 1.03 * 1.03)
    assert r.ingresos.loc["Total", 2025] == pytest.approx(21)
    assert r.pagos.loc["Pago al concesionario escenario 1", 2027] == pytest.approx(4000 * (13200 * 1.05 + 120))
    assert r.pagos.loc["Pago al concesionario escenario 1", 2028] == pytest.approx(4000 * 1.03 * (13200 * 1.05 + 120))


def test_excel_exporta_formulas():
    wb = openpyxl.load_workbook(io.BytesIO(exportar_excel(ficticio())))
    ws = wb["Simulación"]
    formulas = [c.value for fila in ws.iter_rows() for c in fila if isinstance(c.value, str) and c.value.startswith("=")]
    assert len(formulas) > 30
    assert any("SUM(" in f for f in formulas)


@pytest.mark.skipif(not REFERENCIA.exists(), reason="planilla de referencia solo disponible localmente")
def test_reproduce_planilla_de_referencia():
    d = json.loads(REFERENCIA.read_text(encoding="utf-8"))
    esperado = d.pop("esperado")

    def claves_int(x):
        return {int(k): v for k, v in x.items()}

    s = SupuestosSimulacion(
        nombre="Referencia", anio_base=d["anio_base"], anio_final=d["anio_final"],
        pax_nac=claves_int(d["pax_nac"]), pax_int=claves_int(d["pax_int"]),
        crec_nac=claves_int(d["crec_nac"]), crec_int=claves_int(d["crec_int"]), ipc=claves_int(d["ipc"]),
        tarifa_nac=d["tarifa_nac"], tarifa_int_usd=claves_int(d["tarifa_int_usd"]),
        tipo_cambio=claves_int(d["tipo_cambio"]), ingresos_base=d["ingresos_base"],
        ingresos_historicos=claves_int(d["ingresos_historicos"]), tpe=d["tpe"], anio_inicio_tpe=d["anio_inicio_tpe"],
    )
    r = calcular(s)
    assert r.pax_anual.loc["Nacional", 2026] == pytest.approx(esperado["pax_nac_2026"])
    assert r.pax_anual.loc["Internacional", 2026] == pytest.approx(esperado["pax_int_2026"])
    assert r.pax_anual.loc["Nacional", 2031] == pytest.approx(esperado["pax_nac_2031"])
    assert r.ingresos.loc["Total", 2026] == pytest.approx(esperado["total_2026"])
    assert r.ingresos.loc["Total", 2027] == pytest.approx(esperado["total_2027"])
    assert r.ingresos.loc["Total", 2031] == pytest.approx(esperado["total_2031"])
    assert r.ingresos.loc["Total", 2023] == pytest.approx(esperado["total_2023"])
    assert r.pagos.loc["Pago al concesionario escenario 1", 2027] == pytest.approx(esperado["pago1_2027"])
    assert r.pagos.loc["Pago al concesionario escenario 2", 2030] == pytest.approx(esperado["pago2_2030"])
