"""Prueba de humo: cada página se ejecuta sin errores, con y sin datos."""
import os

import pytest
from streamlit.testing.v1 import AppTest

from conftest import RAIZ
from core import demo

PAGINAS = ["inicio", "carga_informe", "ingresos_concepto", "factores", "pasajeros", "operaciones", "proyeccion",
           "control", "simulador", "reportes", "maestros"]


@pytest.fixture
def app():
    os.chdir(RAIZ)
    return AppTest.from_file(str(RAIZ / "app.py"), default_timeout=120)


@pytest.mark.parametrize("pagina", PAGINAS)
def test_pagina_sin_datos(app, pagina):
    app.run()
    app.switch_page(f"paginas/{pagina}.py").run()
    assert not app.exception, [ex.message for ex in app.exception]


@pytest.mark.parametrize("pagina", PAGINAS)
def test_pagina_con_ejemplos(app, pagina):
    demo.cargar()
    app.run()
    app.switch_page(f"paginas/{pagina}.py").run()
    assert not app.exception, [ex.message for ex in app.exception]


def test_guardar_proyeccion_y_controlar(app):
    demo.cargar()
    app.run()
    app.switch_page("paginas/proyeccion.py").run()
    boton = next(b for b in app.button if b.label == "Guardar")
    boton.click().run()
    assert not app.exception
    app.switch_page("paginas/control.py").run()
    assert not app.exception, [ex.message for ex in app.exception]
    app.switch_page("paginas/reportes.py").run()
    for etiqueta in ("Generar cuadro resumen (Excel)", "Generar presentación (PPT)"):
        next(b for b in app.button if b.label == etiqueta).click().run()
        assert not app.exception, [ex.message for ex in app.exception]
