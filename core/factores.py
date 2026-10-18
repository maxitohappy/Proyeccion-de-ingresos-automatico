"""Factores económicos (dólar, IPC, UF, IMACEC, PIB) y tarifas de derecho de embarque.

Orden de prioridad de cada dato mensual:
1. Valor manual ingresado por el usuario (queda registrado con comentario).
2. Datos publicados en `datos/economicos.json` (GitHub Actions: BCCh > CMF > mindicador).
3. Supuestos de proyección (dólar e IPC anual esperado) para los meses futuros.
"""
from __future__ import annotations

import json
from datetime import date, datetime
from pathlib import Path

import pandas as pd

from . import almacenamiento as alm

ARCHIVO_WEB = Path(__file__).resolve().parent.parent / "datos" / "economicos.json"
ARCHIVO_MANUALES = "factores/manuales.csv"
ARCHIVO_SUPUESTOS = "factores/supuestos.json"
ARCHIVO_TARIFAS = "factores/tarifas.csv"

INDICADORES = {
    "dolar": "Dólar observado (promedio mensual, $)",
    "ipc": "IPC variación mensual (%)",
    "uf": "UF (promedio mensual, $)",
    "imacec": "IMACEC (variación anual, %)",
}

CLASES_TARIFA = {
    "NAC_1C": ("D° embarque nacional 1ª categoría", "CLP"),
    "NAC_2C": ("D° embarque nacional 2ª categoría", "CLP"),
    "NAC_270": ("D° embarque nacional hasta 270 km", "CLP"),
    "INT_MAS500": ("D° embarque internacional > 500 km", "USD"),
    "INT_MENOS500": ("D° embarque internacional < 500 km", "CLP"),
}

REGLAS_REAJUSTE = {
    "trimestral": "Trimestral por IPC (enero, abril, julio, octubre)",
    "semestral": "Semestral por IPC (enero y julio)",
    "anual": "Anual por IPC (enero)",
    "ninguno": "Sin reajuste automático",
}
_MESES_REAJUSTE = {"trimestral": (1, 4, 7, 10), "semestral": (1, 7), "anual": (1,), "ninguno": ()}

SUPUESTOS_DEFECTO = {
    "dolar_proyectado": {},          # {"2026": 950.0}
    "ipc_anual_esperado": {},        # {"2026": 0.035} (fracción)
    "regla_reajuste": "trimestral",
    "fuente_expectativas": "Encuesta de Expectativas Económicas (BCCh)",
}


def periodo(anio: int, mes: int) -> str:
    return f"{int(anio):04d}-{int(mes):02d}"


def _partes(p: str) -> tuple[int, int]:
    a, m = p.split("-")
    return int(a), int(m)


def _siguiente(p: str, n: int = 1) -> str:
    a, m = _partes(p)
    total = a * 12 + (m - 1) + n
    return periodo(total // 12, total % 12 + 1)


# --- Datos web ---------------------------------------------------------------------

def cargar_web(ruta: Path | None = None) -> dict:
    ruta = ruta or ARCHIVO_WEB
    if not ruta.exists():
        return {"actualizado": None, "registros": [], "estado_fuentes": {}}
    with open(ruta, encoding="utf-8") as f:
        return json.load(f)


def _df_web(web: dict) -> pd.DataFrame:
    df = pd.DataFrame(web.get("registros", []))
    if df.empty:
        return pd.DataFrame(columns=["periodo", "indicador", "valor", "fuente"])
    if "parcial" in df.columns:
        df["fuente"] = df["fuente"].where(~df["parcial"].fillna(False).astype(bool), df["fuente"] + " (parcial)")
    return df[["periodo", "indicador", "valor", "fuente"]]


# --- Manuales y supuestos ----------------------------------------------------------

def cargar_manuales() -> pd.DataFrame:
    df = alm.leer_csv(ARCHIVO_MANUALES, dtype={"periodo": str})
    return df if df is not None else pd.DataFrame(columns=["periodo", "indicador", "valor", "comentario", "registrado"])


def guardar_manual(per: str, indicador: str, valor: float | None, comentario: str = "") -> None:
    df = cargar_manuales()
    df = df[~((df["periodo"] == per) & (df["indicador"] == indicador))]
    if valor is not None:
        fila = pd.DataFrame([{
            "periodo": per, "indicador": indicador, "valor": float(valor), "comentario": comentario,
            "registrado": datetime.now().isoformat(timespec="seconds"),
        }])
        df = pd.concat([df, fila], ignore_index=True)
    alm.escribir_csv(ARCHIVO_MANUALES, df.sort_values(["indicador", "periodo"]))


def cargar_supuestos() -> dict:
    s = dict(SUPUESTOS_DEFECTO)
    s.update(alm.leer_json(ARCHIVO_SUPUESTOS, {}))
    return s


def guardar_supuestos(s: dict) -> None:
    alm.escribir_json(ARCHIVO_SUPUESTOS, s)


# --- Serie consolidada -------------------------------------------------------------

def serie(indicador: str, desde: str, hasta: str, web: dict | None = None,
          supuestos: dict | None = None, manuales: pd.DataFrame | None = None) -> pd.DataFrame:
    """Serie mensual consolidada con columnas periodo, valor, fuente, tipo (real/supuesto)."""
    web = cargar_web() if web is None else web
    supuestos = cargar_supuestos() if supuestos is None else supuestos
    manuales = cargar_manuales() if manuales is None else manuales
    w = _df_web(web)
    w = w[w["indicador"] == indicador].set_index("periodo")
    man = manuales[manuales["indicador"] == indicador].set_index("periodo")
    filas, p = [], desde
    ultimo_real = None
    while p <= hasta:
        if p in man.index:
            filas.append((p, float(man.loc[p, "valor"]), "Manual", "real"))
            ultimo_real = p
        elif p in w.index:
            filas.append((p, float(w.loc[p, "valor"]), str(w.loc[p, "fuente"]), "real"))
            ultimo_real = p
        else:
            filas.append((p, None, "", "supuesto"))
        p = _siguiente(p)
    df = pd.DataFrame(filas, columns=["periodo", "valor", "fuente", "tipo"])
    df["valor"] = pd.to_numeric(df["valor"], errors="coerce").astype(float)
    return _completar_supuestos(df, indicador, supuestos, ultimo_real)


def _completar_supuestos(df: pd.DataFrame, indicador: str, supuestos: dict, ultimo_real) -> pd.DataFrame:
    faltan = df["valor"].isna()
    if not faltan.any():
        return df
    anio = df["periodo"].str[:4]
    if indicador == "dolar":
        proy = anio.map(lambda a: supuestos.get("dolar_proyectado", {}).get(a))
        ultimo = df.loc[~faltan, "valor"].iloc[-1] if (~faltan).any() else None
        valores = pd.to_numeric(proy.where(proy.notna(), ultimo), errors="coerce").astype(float)
        df.loc[faltan, "valor"] = valores[faltan]
        df.loc[faltan, "fuente"] = proy[faltan].map(lambda v: "Supuesto anual" if pd.notna(v) else "Último valor")
    elif indicador == "ipc":
        anual = anio.map(lambda a: supuestos.get("ipc_anual_esperado", {}).get(a))
        mensual = anual.map(lambda v: ((1 + float(v)) ** (1 / 12) - 1) * 100 if pd.notna(v) else float("nan"))
        df.loc[faltan, "valor"] = mensual[faltan].astype(float)
        df.loc[faltan, "fuente"] = "IPC anual esperado"
    elif indicador == "uf":
        # La UF se mueve con el IPC: se extiende con el IPC mensual supuesto.
        ipc = serie("ipc", df["periodo"].iloc[0], df["periodo"].iloc[-1], supuestos=supuestos)
        ipc = ipc.set_index("periodo")["valor"]
        previo = None
        for i in df.index:
            if pd.notna(df.at[i, "valor"]):
                previo = df.at[i, "valor"]
            elif previo is not None:
                v = ipc.get(df.at[i, "periodo"])
                previo = previo * (1 + (v or 0) / 100)
                df.at[i, "valor"], df.at[i, "fuente"] = previo, "Extendida con IPC"
    return df


def tabla_factores(anios: list[int], web: dict | None = None) -> pd.DataFrame:
    """Tabla mes × indicador para mostrar en pantalla (como la hoja 'factores')."""
    desde, hasta = periodo(min(anios), 1), periodo(max(anios), 12)
    web = cargar_web() if web is None else web
    sup, man = cargar_supuestos(), cargar_manuales()
    partes = []
    for ind in ("dolar", "ipc", "uf", "imacec"):
        s = serie(ind, desde, hasta, web, sup, man).set_index("periodo")
        partes.append(s["valor"].rename(ind))
        partes.append(s["fuente"].rename(f"{ind}_fuente"))
    return pd.concat(partes, axis=1)


def indice_ipc(desde: str, hasta: str, **kw) -> pd.Series:
    """Índice acumulado del IPC (base 1 en `desde`)."""
    s = serie("ipc", desde, hasta, **kw).set_index("periodo")["valor"].fillna(0) / 100
    idx = (1 + s).cumprod()
    return idx / idx.iloc[0]


# --- Tarifas de derecho de embarque -------------------------------------------------

def cargar_tarifas() -> pd.DataFrame:
    df = alm.leer_csv(ARCHIVO_TARIFAS, dtype={"vigente_desde": str})
    return df if df is not None else pd.DataFrame(columns=["vigente_desde", "clase", "valor", "comentario"])


def guardar_tarifas(df: pd.DataFrame) -> None:
    alm.escribir_csv(ARCHIVO_TARIFAS, df.sort_values(["clase", "vigente_desde"]))


def tarifas_mensuales(desde: str, hasta: str, tarifas: pd.DataFrame | None = None,
                      supuestos: dict | None = None, **kw) -> pd.DataFrame:
    """Tarifa vigente por mes y clase.

    Las tarifas registradas mandan; en los meses de reajuste sin tarifa registrada las
    tarifas en CLP se reajustan por el IPC acumulado desde el reajuste anterior.
    """
    tarifas = cargar_tarifas() if tarifas is None else tarifas
    supuestos = cargar_supuestos() if supuestos is None else supuestos
    regla = supuestos.get("regla_reajuste", "trimestral")
    meses_reajuste = _MESES_REAJUSTE.get(regla, ())
    inicio = min([desde] + tarifas["vigente_desde"].dropna().tolist()) if not tarifas.empty else desde
    ipc = serie("ipc", inicio, hasta, supuestos=supuestos, **kw).set_index("periodo")["valor"].fillna(0) / 100
    periodos, p = [], inicio
    while p <= hasta:
        periodos.append(p)
        p = _siguiente(p)
    resultado = {}
    for clase, (_, moneda) in CLASES_TARIFA.items():
        reg = tarifas[tarifas["clase"] == clase].set_index("vigente_desde")["valor"].to_dict()
        valor, ipc_acum, valores = None, 1.0, []
        for p in periodos:
            _, mes = _partes(p)
            if p in reg:
                valor, ipc_acum = float(reg[p]), 1.0
            elif valor is not None and moneda == "CLP" and mes in meses_reajuste:
                valor, ipc_acum = valor * ipc_acum, 1.0
            valores.append(valor)
            ipc_acum *= 1 + ipc.get(p, 0)
        resultado[clase] = valores
    df = pd.DataFrame(resultado, index=periodos)
    return df.loc[(df.index >= desde) & (df.index <= hasta)]


def hoy_periodo() -> str:
    d = date.today()
    return periodo(d.year, d.month)
