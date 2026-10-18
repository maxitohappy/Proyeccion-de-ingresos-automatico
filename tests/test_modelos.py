import numpy as np
import pandas as pd
import pytest

from core import modelos
from core.modelos import clave


def serie_estacional(anios=(2025, 2026), meses_ultimo=9, crecimiento=0.06):
    est = [1.2, 1.1, 1.0, 0.9, 0.8, 0.85, 1.0, 0.95, 0.9, 1.0, 1.1, 1.2]
    datos = {}
    for i, a in enumerate(anios):
        for m in range(1, 13):
            if a == anios[-1] and m > meses_ultimo:
                break
            datos[clave(a, m)] = 1000 * est[m - 1] * (1 + crecimiento) ** i
    return pd.Series(datos)


def test_interanual_reproduce_crecimiento():
    s = serie_estacional()
    assert modelos.crecimiento_interanual(s) == pytest.approx(0.06)
    p = modelos.proyectar(s, clave(2026, 12))
    assert p[clave(2026, 12)] == pytest.approx(1200 * 1.06)
    p2 = modelos.proyectar(s, clave(2027, 12), parametros={"g_siguiente": 0.0})
    assert p2[clave(2027, 6)] == pytest.approx(850 * 1.06)


def test_manual_y_promedio():
    s = serie_estacional()
    p = modelos.proyectar(s, clave(2027, 3), "manual", {"g_por_anio": {"2026": 0.1, "2027": 0.0}})
    assert p[clave(2026, 10)] == pytest.approx(1000 * 1.1)
    assert p[clave(2027, 1)] == pytest.approx(1200 * 1.06)
    pm = modelos.proyectar(s, clave(2026, 12), "promedio_movil")
    assert pm.nunique() == 1


def test_sin_anio_anterior_usa_respaldo():
    s = pd.Series({clave(2026, m): 100.0 for m in range(1, 10)})
    p = modelos.proyectar(s, clave(2026, 12))
    assert (p == 100.0).all()


def test_backtest_y_holt_winters():
    s = serie_estacional(anios=(2024, 2025, 2026))
    ev = modelos.evaluar_metodos(s)
    assert "holt_winters" in set(ev["metodo"])
    assert ev["error"].iloc[0] < 0.05
    assert modelos.recomendar(s) in modelos.METODOS
    p = modelos.proyectar(s, clave(2027, 12), "holt_winters")
    assert len(p) == 15 and np.isfinite(p).all()
