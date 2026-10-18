"""Motores de proyección de series mensuales (PAX, operaciones o ingresos).

Las series se representan como `pd.Series` indexadas por una clave entera de período
(año*12 + mes-1). Los métodos están pensados para poca historia (año actual y anterior);
Holt-Winters se habilita automáticamente cuando hay al menos 24 meses.
"""
from __future__ import annotations

import warnings

import numpy as np
import pandas as pd

METODOS = {
    "interanual_acum": "Crecimiento interanual del año (acumulado a la fecha)",
    "interanual_3m": "Crecimiento interanual de los últimos 3 meses",
    "manual": "Crecimiento anual definido por el usuario",
    "promedio_movil": "Promedio de los últimos 3 meses (sin estacionalidad)",
    "holt_winters": "Holt-Winters estacional (requiere ≥ 24 meses)",
}
MIN_HOLT_WINTERS = 24
_G_MIN, _G_MAX = -0.9, 3.0


def clave(anio: int, mes: int) -> int:
    return int(anio) * 12 + int(mes) - 1


def desde_clave(k: int) -> tuple[int, int]:
    return k // 12, k % 12 + 1


def a_serie(df: pd.DataFrame, valor: str = "VALOR") -> pd.Series:
    """DataFrame con ANIO, MES y una columna de valor -> serie indexada por clave."""
    if df.empty:
        return pd.Series(dtype=float)
    s = df.groupby([df["ANIO"].astype(int) * 12 + df["MES"].astype(int) - 1])[valor].sum()
    return s.sort_index().astype(float)


def _crecimiento(actual: float, anterior: float) -> float:
    if anterior is None or anterior <= 0 or actual is None:
        return 0.0
    return float(np.clip(actual / anterior - 1, _G_MIN, _G_MAX))


def crecimiento_interanual(serie: pd.Series, meses: int | None = None) -> float:
    """Crecimiento de los últimos `meses` (o del acumulado del año) vs. los mismos meses del año previo."""
    if serie.empty:
        return 0.0
    ultimo = int(serie.index.max())
    if meses is None:
        anio, _ = desde_clave(ultimo)
        claves = [k for k in serie.index if desde_clave(k)[0] == anio]
    else:
        claves = [k for k in range(ultimo - meses + 1, ultimo + 1) if k in serie.index]
    claves = [k for k in claves if (k - 12) in serie.index]
    if not claves:
        return 0.0
    return _crecimiento(serie.loc[claves].sum(), serie.loc[[k - 12 for k in claves]].sum())


def _promedio_reciente(serie: pd.Series, n: int = 3) -> float:
    return float(serie.iloc[-n:].mean()) if not serie.empty else 0.0


def proyectar(serie: pd.Series, hasta: int, metodo: str = "interanual_acum", parametros: dict | None = None) -> pd.Series:
    """Proyecta desde el mes siguiente al último dato hasta la clave `hasta` (inclusive)."""
    parametros = parametros or {}
    serie = serie.dropna().sort_index()
    if serie.empty:
        return pd.Series(dtype=float)
    ultimo = int(serie.index.max())
    futuros = list(range(ultimo + 1, hasta + 1))
    if not futuros:
        return pd.Series(dtype=float)

    if metodo == "holt_winters" and len(serie) >= MIN_HOLT_WINTERS:
        r = _holt_winters(serie, len(futuros))
        if r is not None:
            return pd.Series(r, index=futuros)
        metodo = "interanual_acum"
    elif metodo == "holt_winters":
        metodo = "interanual_acum"

    if metodo == "promedio_movil":
        return pd.Series(_promedio_reciente(serie), index=futuros)

    if metodo == "manual":
        g_anio = {int(a): float(g) for a, g in (parametros.get("g_por_anio") or {}).items()}

        def g_de(k):
            return g_anio.get(desde_clave(k)[0], 0.0)
    else:
        g = crecimiento_interanual(serie, 3 if metodo == "interanual_3m" else None)
        g_sig = parametros.get("g_siguiente")
        anio_ultimo = desde_clave(ultimo)[0]

        def g_de(k):
            # Año en curso: g observada. Años siguientes: g indicada o la misma g observada.
            return g if desde_clave(k)[0] == anio_ultimo or g_sig is None else float(g_sig)

    extendida = serie.copy()
    respaldo = _promedio_reciente(serie)
    valores = []
    for k in futuros:
        base = extendida.get(k - 12)
        v = respaldo if base is None or pd.isna(base) else base * (1 + g_de(k))
        v = max(float(v), 0.0) if serie.min() >= 0 else float(v)
        extendida.loc[k] = v
        valores.append(v)
    return pd.Series(valores, index=futuros)


def _holt_winters(serie: pd.Series, pasos: int):
    try:
        from statsmodels.tsa.holtwinters import ExponentialSmoothing
    except ImportError:
        return None
    completa = serie.reindex(range(int(serie.index.min()), int(serie.index.max()) + 1)).interpolate().bfill()
    estacional = "mul" if (completa > 0).all() else "add"
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        try:
            modelo = ExponentialSmoothing(
                completa.values, trend="add", damped_trend=True, seasonal=estacional, seasonal_periods=12,
                initialization_method="estimated",
            ).fit()
            return np.maximum(modelo.forecast(pasos), 0) if (completa >= 0).all() else modelo.forecast(pasos)
        except Exception:  # noqa: BLE001 - se usa el método por defecto
            return None


def metodos_aplicables(serie: pd.Series) -> list[str]:
    m = ["interanual_acum", "interanual_3m", "promedio_movil", "manual"]
    if len(serie.dropna()) >= MIN_HOLT_WINTERS:
        m.append("holt_winters")
    return m


def backtest(serie: pd.Series, metodo: str, parametros: dict | None = None, n: int = 3) -> float | None:
    """Error porcentual ponderado (WAPE) al proyectar los últimos `n` meses con los datos previos."""
    serie = serie.dropna().sort_index()
    if len(serie) <= n + 3:
        return None
    entrenamiento, prueba = serie.iloc[:-n], serie.iloc[-n:]
    pred = proyectar(entrenamiento, int(prueba.index.max()), metodo, parametros).reindex(prueba.index)
    if pred.isna().any() or prueba.abs().sum() == 0:
        return None
    return float((pred - prueba).abs().sum() / prueba.abs().sum())


def evaluar_metodos(serie: pd.Series, n: int = 3) -> pd.DataFrame:
    filas = []
    for m in metodos_aplicables(serie):
        if m == "manual":
            continue
        filas.append({"metodo": m, "descripcion": METODOS[m], "error": backtest(serie, m, n=n)})
    df = pd.DataFrame(filas)
    return df.sort_values("error", na_position="last").reset_index(drop=True)


def recomendar(serie: pd.Series) -> str:
    ev = evaluar_metodos(serie)
    ev = ev.dropna(subset=["error"])
    return ev.iloc[0]["metodo"] if not ev.empty else "interanual_acum"
