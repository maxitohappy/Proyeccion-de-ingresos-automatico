"""Descarga indicadores económicos públicos y los guarda en datos/economicos.json.

Lo ejecuta GitHub Actions todos los días (también se puede correr a mano).
Fuentes, en orden de prioridad para cada indicador y mes:
  1. API BDE del Banco Central (requiere BCCH_USER y BCCH_PASS, cuenta gratuita en si3.bcentral.cl)
  2. API de la CMF (requiere CMF_APIKEY, gratuita en api.cmfchile.cl)
  3. mindicador.cl (sin registro)
Las credenciales se leen de variables de entorno (GitHub Secrets); nunca se escriben en el repo.
"""
from __future__ import annotations

import json
import os
import sys
from collections import defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from statistics import mean

import requests

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "datos" / "economicos.json"
CONFIG_BCCH = RAIZ / "datos" / "config_series_bcch.json"
TIMEOUT = 40


def _num(v) -> float | None:
    if v is None:
        return None
    try:
        return float(str(v).replace(".", "").replace(",", ".")) if isinstance(v, str) and "," in v else float(v)
    except ValueError:
        return None


def _agregar(diarios: dict[str, list[float]], modo: str) -> dict[str, float]:
    """{periodo: [valores]} -> {periodo: valor} según modo (promedio/ultimo)."""
    return {p: (mean(v) if modo == "promedio" else v[-1]) for p, v in diarios.items() if v}


# --- mindicador.cl -------------------------------------------------------------------

def _ipc_desde_uf(uf_diaria: dict[str, float]) -> dict[str, float]:
    """IPC mensual implícito en la UF.

    La UF crece desde el día 10 de m+1 hasta el día 9 de m+2 según el IPC del mes m, por lo que
    IPC(m) = UF(9 de m+2) / UF(9 de m+1) - 1. Reproduce exactamente el IPC publicado (1 decimal)
    y permite tenerlo antes de que mindicador publique la serie de IPC.
    """
    def dia9(anio: int, mes: int) -> str:
        anio, mes = anio + (mes - 1) // 12, (mes - 1) % 12 + 1
        return f"{anio:04d}-{mes:02d}-09"

    resultado = {}
    anios = sorted({int(f[:4]) for f in uf_diaria})
    for a in anios:
        for m in range(1, 13):
            d1, d2 = dia9(a, m + 1), dia9(a, m + 2)
            if d1 in uf_diaria and d2 in uf_diaria:
                resultado[f"{a:04d}-{m:02d}"] = round((uf_diaria[d2] / uf_diaria[d1] - 1) * 100, 1)
    return resultado


def mindicador(anios: list[int]) -> tuple[dict, str]:
    datos, uf_diaria = {}, {}
    try:
        for ind, modo in (("dolar", "promedio"), ("uf", "promedio"), ("ipc", "ultimo"), ("imacec", "ultimo")):
            por_mes = defaultdict(list)
            for a in anios + ([anios[-1] + 1] if ind == "uf" else []):
                r = requests.get(f"https://mindicador.cl/api/{ind}/{a}", timeout=TIMEOUT)
                r.raise_for_status()
                for obs in sorted(r.json().get("serie", []), key=lambda o: o["fecha"]):
                    por_mes[obs["fecha"][:7]].append(float(obs["valor"]))
                    if ind == "uf":
                        uf_diaria[obs["fecha"][:10]] = float(obs["valor"])
            datos[ind] = _agregar(por_mes, modo)
        # Completa el IPC faltante con el implícito en la UF.
        for per, v in _ipc_desde_uf(uf_diaria).items():
            datos["ipc"].setdefault(per, v)
        return datos, "ok"
    except Exception as e:  # noqa: BLE001 - se informa en el JSON
        return datos, f"error: {e}"


# --- API CMF ---------------------------------------------------------------------------

def cmf(anios: list[int]) -> tuple[dict, str]:
    clave = os.environ.get("CMF_APIKEY", "").strip()
    if not clave:
        return {}, "sin credenciales (CMF_APIKEY)"
    recursos = {"dolar": ("dolar", "Dolares", "promedio"), "uf": ("uf", "UFs", "promedio"), "ipc": ("ipc", "IPCs", "ultimo")}
    datos = {}
    try:
        for ind, (recurso, llave, modo) in recursos.items():
            por_mes = defaultdict(list)
            for a in anios:
                url = f"https://api.cmfchile.cl/api-sbifv3/recursos_api/{recurso}/{a}?apikey={clave}&formato=json"
                r = requests.get(url, timeout=TIMEOUT)
                if r.status_code == 404:
                    continue
                r.raise_for_status()
                for obs in r.json().get(llave, []):
                    v = _num(obs.get("Valor"))
                    if v is not None:
                        por_mes[obs["Fecha"][:7]].append(v)
            datos[ind] = _agregar(por_mes, modo)
        return datos, "ok"
    except Exception as e:  # noqa: BLE001
        return datos, f"error: {type(e).__name__}"


# --- API BDE Banco Central -------------------------------------------------------------

def bcch(anios: list[int]) -> tuple[dict, str]:
    usuario, clave = os.environ.get("BCCH_USER", "").strip(), os.environ.get("BCCH_PASS", "").strip()
    if not (usuario and clave):
        return {}, "sin credenciales (BCCH_USER/BCCH_PASS)"
    config = json.loads(CONFIG_BCCH.read_text(encoding="utf-8"))
    datos, errores = {}, []
    for ind, cfg in config.items():
        if ind.startswith("_") or not cfg.get("codigo"):
            continue
        params = {
            "user": usuario, "pass": clave, "function": "GetSeries", "timeseries": cfg["codigo"],
            "firstdate": f"{min(anios)}-01-01", "lastdate": f"{max(anios) + 1}-12-31",
        }
        try:
            r = requests.get("https://si3.bcentral.cl/SieteRestWS/SieteRestWS.ashx", params=params, timeout=TIMEOUT)
            r.raise_for_status()
            j = r.json()
            if j.get("Codigo") != 0:
                errores.append(f"{ind}: {j.get('Descripcion')}")
                continue
            por_mes = defaultdict(list)
            for obs in j["Series"]["Obs"]:
                v = _num(obs.get("value"))
                if v is None or obs.get("statusCode") != "OK":
                    continue
                d, m, a = obs["indexDateString"].split("-")
                por_mes[f"{a}-{m}"].append(v)
            datos[ind] = _agregar(por_mes, cfg.get("agregacion", "promedio"))
        except Exception as e:  # noqa: BLE001
            errores.append(f"{ind}: {type(e).__name__}")
    return datos, "ok" if not errores else "parcial: " + "; ".join(errores)


def main() -> int:
    hoy = date.today()
    anios = list(range(hoy.year - 3, hoy.year + 1))
    mes_en_curso = f"{hoy.year:04d}-{hoy.month:02d}"
    fuentes = [("BCCh", bcch), ("CMF", cmf), ("mindicador", mindicador)]
    registros, estado = {}, {}
    for nombre, funcion in fuentes:
        datos, est = funcion(anios)
        estado[nombre] = est
        print(f"{nombre}: {est} ({sum(len(v) for v in datos.values())} valores)")
        for ind, serie in datos.items():
            for per, valor in serie.items():
                # La primera fuente (mayor prioridad) que entrega el dato manda.
                registros.setdefault((per, ind), {
                    "periodo": per, "indicador": ind, "valor": round(valor, 4), "fuente": nombre,
                    # Promedios del mes en curso (o futuros, como la UF) son parciales.
                    "parcial": per >= mes_en_curso and ind in ("dolar", "uf"),
                })
    if not registros:
        print("No se obtuvo ningún dato; se conserva el archivo anterior.")
        return 1
    salida = {
        "actualizado": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "estado_fuentes": estado,
        "registros": sorted(registros.values(), key=lambda r: (r["indicador"], r["periodo"])),
    }
    SALIDA.parent.mkdir(parents=True, exist_ok=True)
    SALIDA.write_text(json.dumps(salida, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"Guardados {len(registros)} registros en {SALIDA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
