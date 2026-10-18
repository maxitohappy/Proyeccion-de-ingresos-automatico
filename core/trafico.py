"""Pasajeros embarcados (COPAE) y operaciones (SAC): lectura con mapeo de columnas y filtros.

Como los formatos de exportación pueden cambiar, el usuario indica una vez qué columna
corresponde a cada campo y el mapeo queda guardado para los meses siguientes.
"""
from __future__ import annotations

import hashlib
import io
import re
import unicodedata
from dataclasses import dataclass, field

import pandas as pd

from . import almacenamiento as alm
from .ingest import _a_bytes

ARCHIVO_MAPEOS = "config/mapeos_trafico.json"
ARCHIVO_FILTROS_OP = "config/filtros_operaciones.json"

# Campos lógicos que el usuario mapea a columnas del archivo.
CAMPOS_PAX = {
    "unidad": "Aeródromo / unidad (código o nombre)",
    "fecha": "Fecha (o usar Año + Mes)",
    "anio": "Año",
    "mes": "Mes",
    "tipo": "Tipo de vuelo (nacional / internacional)",
    "cantidad": "Cantidad de pasajeros",
    "pax_nacional": "Pasajeros nacionales (si vienen en columna aparte)",
    "pax_internacional": "Pasajeros internacionales (si vienen en columna aparte)",
}
CAMPOS_OP = {
    "unidad": "Aeródromo / unidad (código o nombre)",
    "fecha": "Fecha de la operación (o usar Año + Mes)",
    "anio": "Año",
    "mes": "Mes",
    "tipo": "Tipo de vuelo (nacional / internacional)",
    "cantidad": "Cantidad de operaciones (vacío = 1 por fila)",
    "tipo_operacion": "Tipo de operación (aterrizaje / despegue)",
    "operador": "Operador / cliente",
    "tipo_aeronave": "Tipo de aeronave o clase de usuario",
    "pmd": "PMD (toneladas)",
}

FILTROS_OP_DEFECTO = {
    "solo_aterrizajes": True,
    "texto_aterrizaje": "ATERR",
    "pmd_maximo_excluido": 5.7,
    "excluir_textos": ["FUERZA AEREA", "FACH", "EJERCITO", "ARMADA", "CARABINEROS", "POLICIA", "PDI",
                       "AERONAVE DE ESTADO", "CLUB AEREO", "CLUB AÉREO"],
    "categorias_validas": [1, 2, 3],
}


def _norm(texto) -> str:
    t = unicodedata.normalize("NFKD", str(texto or "")).encode("ascii", "ignore").decode().upper()
    return re.sub(r"[^A-Z0-9 ]+", " ", t).strip()


def leer_tabla(origen, nombre: str = "") -> dict[str, pd.DataFrame]:
    """Lee todas las hojas de un Excel (o un CSV) como texto, detectando la fila de encabezados."""
    contenido = _a_bytes(origen)
    nombre = (nombre or getattr(origen, "name", "")).lower()
    if nombre.endswith((".csv", ".txt")) or contenido[:2] != b"PK":
        texto = contenido.decode("utf-8-sig", errors="replace")
        sep = ";" if texto[:2000].count(";") > texto[:2000].count(",") else ","
        return {"CSV": pd.read_csv(io.StringIO(texto), sep=sep, dtype=str)}
    hojas = pd.read_excel(io.BytesIO(contenido), sheet_name=None, header=None, dtype=object)
    resultado = {}
    for hoja, df in hojas.items():
        df = df.dropna(how="all").dropna(axis=1, how="all")
        if df.empty:
            continue
        # Encabezado = primera fila (de las 15 primeras) con más celdas de texto.
        candidatas = df.head(15)
        fila_enc = max(candidatas.index, key=lambda i: sum(isinstance(v, str) for v in candidatas.loc[i]))
        enc = [str(v).strip() if pd.notna(v) else f"col_{j}" for j, v in enumerate(df.loc[fila_enc])]
        cuerpo = df.loc[df.index > fila_enc].copy()
        cuerpo.columns = _unicos(enc)
        resultado[hoja] = cuerpo.reset_index(drop=True)
    return resultado


def _unicos(nombres):
    vistos, salida = {}, []
    for n in nombres:
        vistos[n] = vistos.get(n, 0) + 1
        salida.append(n if vistos[n] == 1 else f"{n}_{vistos[n]}")
    return salida


def firma_columnas(columnas) -> str:
    return hashlib.md5("|".join(sorted(map(str, columnas))).encode()).hexdigest()[:12]


def sugerir_mapeo(columnas, campos: dict) -> dict:
    """Mapeo inicial por similitud de nombres (o el guardado para estas mismas columnas)."""
    guardados = alm.leer_json(ARCHIVO_MAPEOS, {})
    firma = firma_columnas(columnas)
    if firma in guardados:
        return guardados[firma]
    pistas = {
        "unidad": ["AERODROMO", "AEROPUERTO", "UNIDAD", "ESTACION", "AD", "AP"],
        "fecha": ["FECHA"],
        "anio": ["ANO", "ANIO", "YEAR", "PERIODO ANO"],
        "mes": ["MES", "MONTH"],
        "tipo": ["TIPO VUELO", "NACIONAL INTERNACIONAL", "TIPO TRAFICO", "CLASE VUELO", "TIPO"],
        "cantidad": ["PASAJEROS", "PAX", "CANTIDAD", "TOTAL", "OPERACIONES"],
        "pax_nacional": ["NACIONAL", "NAC"],
        "pax_internacional": ["INTERNACIONAL", "INT"],
        "tipo_operacion": ["TIPO OPERACION", "OPERACION", "MOVIMIENTO"],
        "operador": ["OPERADOR", "CLIENTE", "EMPRESA", "RAZON SOCIAL"],
        "tipo_aeronave": ["TIPO AERONAVE", "CLASE", "USUARIO"],
        "pmd": ["PMD", "PESO"],
    }
    norm = {c: _norm(c) for c in columnas}
    mapeo = {}
    for campo in campos:
        for pista in pistas.get(campo, []):
            exactas = [c for c, n in norm.items() if n == pista and c not in mapeo.values()]
            parciales = [c for c, n in norm.items() if pista in n.split() or n.startswith(pista)]
            elegidas = exactas or [c for c in parciales if c not in mapeo.values()]
            if elegidas:
                mapeo[campo] = elegidas[0]
                break
    return mapeo


def guardar_mapeo(columnas, mapeo: dict) -> None:
    guardados = alm.leer_json(ARCHIVO_MAPEOS, {})
    guardados[firma_columnas(columnas)] = {k: v for k, v in mapeo.items() if v}
    alm.escribir_json(ARCHIVO_MAPEOS, guardados)


def cargar_filtros_op() -> dict:
    f = dict(FILTROS_OP_DEFECTO)
    f.update(alm.leer_json(ARCHIVO_FILTROS_OP, {}))
    return f


def guardar_filtros_op(f: dict) -> None:
    alm.escribir_json(ARCHIVO_FILTROS_OP, f)


# --- Resolución de unidades ----------------------------------------------------------

def resolver_unidades(valores: pd.Series, unidades: pd.DataFrame) -> pd.Series:
    """Convierte códigos o nombres de aeródromo al código de unidad del maestro."""
    codigos = set(unidades["unidad"].dropna().astype(int)) if not unidades.empty else set()
    por_nombre = {}
    for r in unidades.itertuples():
        n = _norm(r.nombre)
        n_sin = re.sub(r"^(AP|AD|AEROPUERTO|AERODROMO)\s+", "", n)
        por_nombre[n] = por_nombre[n_sin] = int(r.unidad)

    def resolver(v):
        if pd.isna(v):
            return None
        texto = str(v).strip()
        m = re.match(r"^(\d{4})(\.0)?\b", texto)
        if m and (not codigos or int(m.group(1)) in codigos):
            return int(m.group(1))
        n = _norm(texto)
        n_sin = re.sub(r"^(AP|AD|AEROPUERTO|AERODROMO)\s+", "", n)
        if n in por_nombre:
            return por_nombre[n]
        if n_sin in por_nombre:
            return por_nombre[n_sin]
        candidatos = [u for k, u in por_nombre.items() if n_sin and (n_sin in k or k in n_sin) and len(k) > 3]
        return candidatos[0] if len(set(candidatos)) == 1 else None

    return valores.map(resolver)


def _tipo(v) -> str | None:
    n = _norm(v)
    if not n:
        return None
    if n.startswith("INT") or n in ("I", "INTL"):
        return "Internacional"
    if n.startswith("NAC") or n in ("N", "DOM", "DOMESTICO"):
        return "Nacional"
    return None


@dataclass
class ResultadoTrafico:
    datos: pd.DataFrame                     # ANIO, MES, UNIDAD, TIPO, VALOR
    no_reconocidas: pd.DataFrame            # valores de unidad sin match
    excluidas: dict[str, int] = field(default_factory=dict)
    advertencias: list[str] = field(default_factory=list)


def _periodo(df: pd.DataFrame, mapeo: dict) -> tuple[pd.Series, pd.Series]:
    if mapeo.get("anio") and mapeo.get("mes"):
        anio = pd.to_numeric(df[mapeo["anio"]], errors="coerce")
        mes = pd.to_numeric(df[mapeo["mes"]], errors="coerce")
        if mes.isna().all():
            meses = {_norm(m)[:3]: i for i, m in enumerate(
                ["ENE", "FEB", "MAR", "ABR", "MAY", "JUN", "JUL", "AGO", "SEP", "OCT", "NOV", "DIC"], 1)}
            mes = df[mapeo["mes"]].map(lambda v: meses.get(_norm(v)[:3]))
        return anio, mes
    if mapeo.get("fecha"):
        f = df[mapeo["fecha"]]
        fechas = pd.to_datetime(f, errors="coerce", dayfirst=True)
        numericas = pd.to_numeric(f, errors="coerce")
        serial = pd.to_datetime(numericas, unit="D", origin="1899-12-30", errors="coerce")
        fechas = fechas.fillna(serial.where(numericas.between(20000, 80000)))
        return fechas.dt.year, fechas.dt.month
    raise ValueError("Debe indicar la columna de fecha o las columnas de año y mes.")


def procesar(df: pd.DataFrame, mapeo: dict, unidades: pd.DataFrame, es_operaciones: bool = False,
             filtros: dict | None = None) -> ResultadoTrafico:
    if not mapeo.get("unidad"):
        raise ValueError("Debe indicar la columna de unidad / aeródromo.")
    d = df.copy()
    excluidas, advertencias = {}, []

    if es_operaciones:
        filtros = filtros or cargar_filtros_op()
        d, excluidas = _filtrar_operaciones(d, mapeo, unidades, filtros)

    anio, mes = _periodo(d, mapeo)
    unidad = resolver_unidades(d[mapeo["unidad"]], unidades)
    base = pd.DataFrame({"ANIO": anio, "MES": mes, "UNIDAD": unidad})

    if mapeo.get("pax_nacional") or mapeo.get("pax_internacional"):
        partes = []
        for campo, tipo in (("pax_nacional", "Nacional"), ("pax_internacional", "Internacional")):
            if mapeo.get(campo):
                partes.append(base.assign(TIPO=tipo, VALOR=pd.to_numeric(d[mapeo[campo]], errors="coerce").fillna(0)))
        largo = pd.concat(partes, ignore_index=True)
    else:
        if not mapeo.get("tipo"):
            raise ValueError("Indique la columna de tipo (nacional/internacional) o columnas separadas.")
        if mapeo.get("cantidad"):
            valor = pd.to_numeric(d[mapeo["cantidad"]], errors="coerce").fillna(0)
        elif es_operaciones:
            valor = pd.Series(1, index=d.index)
        else:
            raise ValueError("Indique la columna con la cantidad de pasajeros.")
        largo = base.assign(TIPO=d[mapeo["tipo"]].map(_tipo), VALOR=valor)
        sin_tipo = int(largo["TIPO"].isna().sum())
        if sin_tipo:
            advertencias.append(f"{sin_tipo} filas sin tipo nacional/internacional reconocible fueron omitidas.")

    no_reconocidas = (
        d.loc[unidad.isna(), mapeo["unidad"]].astype(str).value_counts()
        .rename_axis("valor").reset_index(name="filas")
    )
    sin_periodo = int((largo["ANIO"].isna() | largo["MES"].isna()).sum())
    if sin_periodo:
        advertencias.append(f"{sin_periodo} filas sin año/mes válido fueron omitidas.")
    largo = largo.dropna(subset=["ANIO", "MES", "UNIDAD", "TIPO"])
    agg = largo.groupby(["ANIO", "MES", "UNIDAD", "TIPO"])["VALOR"].sum().reset_index()
    for c in ("ANIO", "MES", "UNIDAD"):
        agg[c] = agg[c].astype(int)
    return ResultadoTrafico(datos=agg, no_reconocidas=no_reconocidas, excluidas=excluidas, advertencias=advertencias)


def _filtrar_operaciones(d: pd.DataFrame, mapeo: dict, unidades: pd.DataFrame, filtros: dict):
    """Filtros del instructivo (actividad 5)."""
    excluidas = {}

    def aplicar(mascara_excluir: pd.Series, motivo: str):
        nonlocal d
        n = int(mascara_excluir.sum())
        if n:
            excluidas[motivo] = n
            d = d[~mascara_excluir]

    if filtros.get("solo_aterrizajes") and mapeo.get("tipo_operacion"):
        texto = _norm(filtros.get("texto_aterrizaje", "ATERR"))
        aplicar(~d[mapeo["tipo_operacion"]].map(_norm).str.contains(texto, regex=False), "Despegues u otras operaciones")
    textos = [_norm(t) for t in filtros.get("excluir_textos", []) if t]
    if textos:
        columnas = [mapeo[c] for c in ("operador", "tipo_aeronave") if mapeo.get(c)]
        if columnas:
            combinado = d[columnas].astype(str).agg(" ".join, axis=1).map(_norm)
            patron = "|".join(re.escape(t) for t in textos)
            aplicar(combinado.str.contains(patron, regex=True), "Aeronaves de Estado / clubes aéreos")
    if mapeo.get("pmd") and filtros.get("pmd_maximo_excluido") is not None:
        pmd = pd.to_numeric(d[mapeo["pmd"]].astype(str).str.replace(",", ".", regex=False), errors="coerce")
        aplicar(pmd <= float(filtros["pmd_maximo_excluido"]), f"PMD ≤ {filtros['pmd_maximo_excluido']} t")
    validas = set(filtros.get("categorias_validas", [1, 2, 3]))
    if validas and not unidades.empty:
        cat = dict(zip(unidades["unidad"].astype(int), unidades["categoria"]))
        u = resolver_unidades(d[mapeo["unidad"]], unidades)
        fuera = u.map(lambda x: pd.notna(x) and pd.notna(cat.get(int(x))) and int(cat[int(x)]) not in validas)
        aplicar(fuera.astype(bool), "Aeródromo fuera de 1ª, 2ª o 3ª categoría")
    return d, excluidas
