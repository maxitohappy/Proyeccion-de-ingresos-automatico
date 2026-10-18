"""Busca códigos de series en la API BDE del Banco Central.

Uso:  BCCH_USER=... BCCH_PASS=... python scripts/buscar_series_bcch.py "expectativas inflación" [MONTHLY|QUARTERLY|DAILY|ANNUAL]
Copia el código encontrado en datos/config_series_bcch.json.
"""
import os
import sys
import unicodedata

import requests


def _norm(t: str) -> str:
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode().lower()


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 1
    terminos = _norm(sys.argv[1]).split()
    frecuencias = [sys.argv[2]] if len(sys.argv) > 2 else ["MONTHLY", "QUARTERLY", "DAILY", "ANNUAL"]
    for frecuencia in frecuencias:
        r = requests.get(
            "https://si3.bcentral.cl/SieteRestWS/SieteRestWS.ashx",
            params={"user": os.environ["BCCH_USER"], "pass": os.environ["BCCH_PASS"],
                    "function": "SearchSeries", "frequency": frecuencia},
            timeout=60,
        )
        r.raise_for_status()
        for s in r.json().get("SeriesInfos", []):
            titulo = s.get("spanishTitle", "")
            if all(t in _norm(titulo) for t in terminos):
                print(f"{frecuencia:9} {s['seriesId']:45} {titulo}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
