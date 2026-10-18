"""Proyección de ingresos operacionales por unidad × concepto × mes (instructivo, actividad 7).

Para cada unidad y concepto:
* Meses cerrados: ingreso real.
* Meses abiertos, con datos de tráfico (PAX u operaciones):
      ingreso = cantidad proyectada × ingreso unitario calibrado × dólar × índice de tarifa/IPC
  donde el ingreso unitario se calibra con los últimos meses cerrados (real ÷ teórico), lo que
  captura el mix de categorías y exenciones sin conocer cada tarifa exacta.
* Meses abiertos, sin tráfico: se proyecta la serie de ingresos "deflactada" (en USD para
  conceptos internacionales, a tarifa/IPC constante para los nacionales) y se vuelve a pesos.
Luego se aplican escenarios (volumen, dólar, tarifa) y ajustes manuales.
"""
from __future__ import annotations

import copy
from dataclasses import dataclass, field

import numpy as np
import pandas as pd

from . import factores as fac
from .esquema import CONCEPTOS_PROYECCION
from .maestros import unidad_grupo
from .modelos import a_serie, clave, desde_clave, proyectar

# Concepto -> (serie de tráfico que lo explica, usa dólar, índice)
DRIVERS = {
    "DE_NAC": ("PAX_NAC", False, "tarifa_nac"),
    "DE_INT": ("PAX_INT", True, "tarifa_int"),
    "TASAS_NAC": ("OP_NAC", False, "ipc"),
    "TASAS_INT": ("OP_INT", True, None),
}
SERIES_TRAFICO = {
    "PAX_NAC": "Pasajeros nacionales", "PAX_INT": "Pasajeros internacionales",
    "OP_NAC": "Operaciones nacionales", "OP_INT": "Operaciones internacionales",
}
EFECTO_VOLUMEN = {"PAX": "pax", "OP": "op"}

CONFIG_DEFECTO = {
    "hasta": None,
    "metodo_trafico": "interanual_acum",
    "parametros_trafico": {},
    "metodos": {c: "interanual_acum" for c in CONCEPTOS_PROYECCION},
    "parametros": {},
    "usar_trafico": True,
    "ventana_calibracion": 3,
    "escenario": {"pax": 0.0, "op": 0.0, "dolar": 0.0, "tarifa_de_nac": 0.0, "tarifa_desde": None},
    "ajustes": [],
}


def config_completa(config: dict | None) -> dict:
    c = copy.deepcopy(CONFIG_DEFECTO)
    for k, v in (config or {}).items():
        if isinstance(v, dict) and isinstance(c.get(k), dict):
            c[k].update(v)
        else:
            c[k] = v
    return c


@dataclass
class ResultadoProyeccion:
    ingresos: pd.DataFrame       # ANIO, MES, UNIDAD, CONCEPTO_PROY, MONTO, ORIGEN, METODO, CANTIDAD, DOLAR
    trafico: pd.DataFrame        # ANIO, MES, UNIDAD, SERIE, VALOR, ORIGEN
    factores: pd.DataFrame       # periodo, dolar, ipc, indices de tarifa
    ultimo_cerrado: tuple[int, int]
    config: dict
    avisos: list[str] = field(default_factory=list)

    def total_anual(self, anio: int) -> float:
        return float(self.ingresos.loc[self.ingresos["ANIO"] == anio, "MONTO"].sum())


def _periodos(desde: int, hasta: int) -> list[int]:
    return list(range(desde, hasta + 1))


def _per(k: int) -> str:
    a, m = desde_clave(k)
    return fac.periodo(a, m)


def _serie_factor(df: pd.DataFrame, col: str, claves: list[int], defecto=1.0) -> pd.Series:
    s = pd.Series({clave(*map(int, p.split("-"))): v for p, v in df[col].items()}, dtype=float)
    return s.reindex(claves).ffill().bfill().fillna(defecto)


def _indice(s: pd.Series, base: int) -> pd.Series:
    b = s.get(base)
    if b is None or pd.isna(b) or b == 0:
        return pd.Series(1.0, index=s.index)
    return s / b


def preparar_factores(desde: int, hasta: int, config: dict, web=None) -> pd.DataFrame:
    """Dólar, IPC e índices de tarifa por mes, con el escenario aplicado a los meses futuros."""
    p0, p1 = _per(desde), _per(hasta)
    dolar = fac.serie("dolar", p0, p1, web=web).set_index("periodo")
    ipc = fac.serie("ipc", p0, p1, web=web).set_index("periodo")
    tarifas = fac.tarifas_mensuales(p0, p1)
    df = pd.DataFrame(index=dolar.index)
    df["dolar"] = dolar["valor"].astype(float)
    df["dolar_fuente"] = dolar["fuente"]
    df["ipc"] = ipc["valor"].astype(float)
    df["ipc_indice"] = (1 + df["ipc"].fillna(0) / 100).cumprod()
    for clase in fac.CLASES_TARIFA:
        df[f"tarifa_{clase}"] = pd.to_numeric(tarifas.get(clase), errors="coerce").reindex(df.index)
    return df


def _mapa_grupos(unidades: pd.DataFrame) -> dict[int, int]:
    return unidad_grupo(unidades) if not unidades.empty else {}


def _trafico_largo(pax: pd.DataFrame, ops: pd.DataFrame, grupos: dict[int, int]) -> pd.DataFrame:
    partes = []
    for df, prefijo in ((pax, "PAX"), (ops, "OP")):
        if df is None or df.empty:
            continue
        d = df.copy()
        d["SERIE"] = prefijo + "_" + d["TIPO"].map(lambda t: "INT" if str(t).lower().startswith("int") else "NAC")
        d["UNIDAD"] = d["UNIDAD"].astype(int).map(lambda u: grupos.get(u, u))
        partes.append(d.groupby(["ANIO", "MES", "UNIDAD", "SERIE"])["VALOR"].sum().reset_index())
    if not partes:
        return pd.DataFrame(columns=["ANIO", "MES", "UNIDAD", "SERIE", "VALOR"])
    return pd.concat(partes, ignore_index=True)


def proyectar_ingresos(ingresos: pd.DataFrame, unidades: pd.DataFrame, pax: pd.DataFrame | None = None,
                       ops: pd.DataFrame | None = None, config: dict | None = None,
                       web: dict | None = None) -> ResultadoProyeccion:
    config = config_completa(config)
    avisos: list[str] = []
    if ingresos.empty:
        raise ValueError("No hay ingresos reales cargados.")
    grupos = _mapa_grupos(unidades)
    cat_unidad = {int(r.unidad): r.categoria for r in unidades.itertuples()} if not unidades.empty else {}

    ing = ingresos.copy()
    ing["UNIDAD"] = ing["UNIDAD_GRUPO"].astype(int)
    k_ultimo = int((ing["ANIO"] * 12 + ing["MES"] - 1).max())
    anio_actual, _ = desde_clave(k_ultimo)
    k_hasta = clave(*map(int, config["hasta"].split("-"))) if config.get("hasta") else clave(anio_actual + 1, 12)
    k_desde = clave(anio_actual - 1, 1)
    k_min_datos = int((ing["ANIO"] * 12 + ing["MES"] - 1).min())
    claves = _periodos(min(k_desde, k_min_datos), k_hasta)

    factores = preparar_factores(claves[0], k_hasta, config, web)
    esc = config["escenario"]
    dolar = _serie_factor(factores, "dolar", claves)
    if esc.get("dolar"):
        dolar.loc[dolar.index > k_ultimo] *= 1 + float(esc["dolar"])
    if factores["dolar"].isna().all():
        avisos.append("No hay datos de dólar: los conceptos internacionales se proyectan sin efecto cambiario.")
    indices = {
        "ipc": _indice(_serie_factor(factores, "ipc_indice", claves), k_ultimo),
        "tarifa_int": _indice(_serie_factor(factores, "tarifa_INT_MAS500", claves), k_ultimo),
        "tarifa_nac_1": _indice(_serie_factor(factores, "tarifa_NAC_1C", claves), k_ultimo),
        "tarifa_nac_2": _indice(_serie_factor(factores, "tarifa_NAC_2C", claves), k_ultimo),
    }
    if esc.get("tarifa_de_nac"):
        desde_t = clave(*map(int, esc["tarifa_desde"].split("-"))) if esc.get("tarifa_desde") else k_ultimo + 1
        for k in ("tarifa_nac_1", "tarifa_nac_2"):
            indices[k] = indices[k].copy()
            indices[k].loc[indices[k].index >= max(desde_t, k_ultimo + 1)] *= 1 + float(esc["tarifa_de_nac"])

    # --- Tráfico: real + proyectado -------------------------------------------------
    traf = _trafico_largo(pax, ops, grupos) if config.get("usar_trafico", True) else _trafico_largo(None, None, grupos)
    series_traf: dict[tuple[int, str], pd.Series] = {}
    filas_traf = []
    for (u, s), g in traf.groupby(["UNIDAD", "SERIE"]):
        real = a_serie(g)
        params = (config.get("parametros_trafico") or {}).get(s, {})
        proy = proyectar(real, k_hasta, config.get("metodo_trafico", "interanual_acum"), params)
        mult = 1 + float(esc.get(EFECTO_VOLUMEN[s.split("_")[0]], 0) or 0)
        proy = proy * mult
        for k, v in real.items():
            filas_traf.append((*desde_clave(k), u, s, v, "Real"))
        for k, v in proy.items():
            filas_traf.append((*desde_clave(k), u, s, v, "Proyectado"))
        series_traf[(u, s)] = pd.concat([real, proy]).sort_index()
    trafico = pd.DataFrame(filas_traf, columns=["ANIO", "MES", "UNIDAD", "SERIE", "VALOR", "ORIGEN"])

    # --- Ingresos ---------------------------------------------------------------------
    filas = []
    ventana = int(config.get("ventana_calibracion", 3))
    for (u, c), g in ing.groupby(["UNIDAD", "CONCEPTO_PROY"]):
        real = a_serie(g, "MONTO").reindex(_periodos(int(a_serie(g, "MONTO").index.min()), k_ultimo)).fillna(0.0)
        driver = DRIVERS.get(c)
        usa_dolar = bool(driver and driver[1])
        indice = _indice_concepto(c, cat_unidad.get(u), indices, claves)
        deflactor = (dolar if usa_dolar else 1.0) * indice
        metodo = config["metodos"].get(c, "interanual_acum")
        params = (config.get("parametros") or {}).get(c, {})
        futuros = _periodos(k_ultimo + 1, k_hasta)
        cantidad = series_traf.get((u, driver[0])) if driver else None
        proy, metodo_usado = None, None
        if cantidad is not None and futuros:
            proy = _proyectar_con_trafico(real, cantidad, deflactor, futuros, ventana)
            if proy is not None:
                metodo_usado = f"{SERIES_TRAFICO[driver[0]]} × ingreso unitario"
        if proy is None and futuros:
            volumen = 1 + float(esc.get(EFECTO_VOLUMEN[driver[0].split("_")[0]], 0) or 0) if driver else 1.0
            base = real / deflactor.reindex(real.index)
            proy = proyectar(base, k_hasta, metodo, params) * deflactor.reindex(futuros) * volumen
            metodo_usado = metodo
        for k, v in real.items():
            q = cantidad.get(k) if cantidad is not None else np.nan
            filas.append((*desde_clave(k), u, c, v, "Real", "", q, dolar[k] if usa_dolar else np.nan))
        if proy is not None:
            for k, v in proy.items():
                q = cantidad.get(k) if cantidad is not None else np.nan
                filas.append((*desde_clave(k), u, c, float(v), "Proyectado", metodo_usado, q,
                              dolar[k] if usa_dolar else np.nan))
    res = pd.DataFrame(filas, columns=["ANIO", "MES", "UNIDAD", "CONCEPTO_PROY", "MONTO", "ORIGEN", "METODO",
                                       "CANTIDAD", "DOLAR"])
    res = _aplicar_ajustes(res, config.get("ajustes", []), avisos)
    factores_salida = factores.loc[[_per(k) for k in claves]].copy()
    factores_salida["dolar_usado"] = dolar.values
    return ResultadoProyeccion(
        ingresos=res, trafico=trafico, factores=factores_salida, ultimo_cerrado=desde_clave(k_ultimo),
        config=config, avisos=avisos,
    )


def _indice_concepto(c: str, categoria, indices: dict, claves: list[int]) -> pd.Series:
    driver = DRIVERS.get(c)
    if not driver or not driver[2]:
        return pd.Series(1.0, index=claves)
    if driver[2] == "tarifa_nac":
        return indices["tarifa_nac_2"] if pd.notna(categoria) and int(categoria) == 2 else indices["tarifa_nac_1"]
    return indices[driver[2]]


def _proyectar_con_trafico(real: pd.Series, cantidad: pd.Series, deflactor: pd.Series, futuros: list[int],
                           ventana: int) -> pd.Series | None:
    comunes = [k for k in real.index if k in cantidad.index and cantidad[k] > 0][-ventana:]
    if not comunes:
        return None
    teorico = sum(cantidad[k] * deflactor[k] for k in comunes)
    if teorico <= 0:
        return None
    unitario = real.loc[comunes].sum() / teorico
    q = cantidad.reindex(futuros)
    if q.isna().all():
        return None
    q = q.ffill().fillna(0)
    return q * unitario * deflactor.reindex(futuros)


def _aplicar_ajustes(res: pd.DataFrame, ajustes: list[dict], avisos: list[str]) -> pd.DataFrame:
    for a in ajustes or []:
        try:
            anio, mes = map(int, str(a["periodo"]).split("-"))
            m = (res["ANIO"] == anio) & (res["MES"] == mes) & (res["UNIDAD"] == int(a["unidad"])) & (
                res["CONCEPTO_PROY"] == a["concepto"])
            if (res.loc[m, "ORIGEN"] == "Real").any():
                avisos.append(f"Ajuste ignorado ({a['unidad']} {a['concepto']} {a['periodo']}): el mes ya está cerrado.")
                continue
            if m.any():
                res.loc[m, "MONTO"] = float(a["valor"])
                res.loc[m, "ORIGEN"] = "Ajuste manual"
                res.loc[m, "METODO"] = a.get("comentario", "")
            else:
                res.loc[len(res)] = [anio, mes, int(a["unidad"]), a["concepto"], float(a["valor"]), "Ajuste manual",
                                     a.get("comentario", ""), np.nan, np.nan]
        except (KeyError, ValueError) as e:
            avisos.append(f"Ajuste inválido {a}: {e}")
    return res


# --- Resúmenes ---------------------------------------------------------------------------

def resumen_anual(res: ResultadoProyeccion) -> pd.DataFrame:
    """Concepto × año (real + proyectado), como el cuadro resumen."""
    d = res.ingresos
    t = d.pivot_table(index="CONCEPTO_PROY", columns="ANIO", values="MONTO", aggfunc="sum", fill_value=0)
    t = t.reindex([c for c in CONCEPTOS_PROYECCION if c in t.index])
    t.index = [CONCEPTOS_PROYECCION[c] for c in t.index]
    t.loc["Total"] = t.sum()
    return t


def resumen_mensual(res: ResultadoProyeccion, anio: int) -> pd.DataFrame:
    d = res.ingresos[res.ingresos["ANIO"] == anio]
    t = d.pivot_table(index="CONCEPTO_PROY", columns="MES", values="MONTO", aggfunc="sum", fill_value=0)
    t = t.reindex([c for c in CONCEPTOS_PROYECCION if c in t.index])
    t.index = [CONCEPTOS_PROYECCION[c] for c in t.index]
    t.loc["Total"] = t.sum()
    return t


def origen_por_mes(res: ResultadoProyeccion, anio: int) -> dict[int, str]:
    d = res.ingresos[res.ingresos["ANIO"] == anio]
    return {int(m): ("Real" if (g["ORIGEN"] == "Real").all() else "Proyectado") for m, g in d.groupby("MES")}


def trafico_anual(res: ResultadoProyeccion) -> pd.DataFrame:
    if res.trafico.empty:
        return pd.DataFrame()
    t = res.trafico.pivot_table(index="SERIE", columns="ANIO", values="VALOR", aggfunc="sum", fill_value=0)
    t.index = [SERIES_TRAFICO.get(s, s) for s in t.index]
    return t
