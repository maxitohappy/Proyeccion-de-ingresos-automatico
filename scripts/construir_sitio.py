"""Construye el sitio estático para GitHub Pages en _site/.

Copia el código de la app y genera index.html, que carga stlite (Streamlit en el navegador
vía WebAssembly) y monta cada archivo. Los archivos subidos por el usuario se procesan en
su navegador; nada se envía a un servidor.

Prueba local:  python scripts/construir_sitio.py && python -m http.server -d _site 8000
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
SITIO = RAIZ / "_site"
STLITE = "1.9.2"
CARPETAS = ["core", "paginas", "ui", "datos", "ejemplos"]
ARCHIVOS = ["app.py"]
EXTENSIONES = {".py", ".json", ".csv", ".xlsx", ".toml"}
REQUISITOS = ["openpyxl", "xlsxwriter", "python-pptx", "statsmodels", "plotly"]

PLANTILLA = """<!doctype html>
<html lang="es">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1, shrink-to-fit=no" />
  <title>Proyección de Ingresos</title>
  <link rel="stylesheet" href="https://cdn.jsdelivr.net/npm/@stlite/browser@__STLITE__/build/stlite.css" />
  <style>
    body { margin: 0; font-family: system-ui, sans-serif; background: #fff; }
    #cargando { max-width: 560px; margin: 18vh auto; padding: 0 16px; color: #1f3864; text-align: center; }
    #cargando p { color: #52514e; line-height: 1.5; }
  </style>
</head>
<body>
  <div id="cargando">
    <h2>Proyección de Ingresos</h2>
    <p>Cargando la aplicación en tu navegador (la primera vez puede tardar 30–60 segundos).<br />
       Tus archivos se procesan solo en este equipo: no se envían a ningún servidor.</p>
  </div>
  <div id="root"></div>
  <script type="module">
    import { mount } from "https://cdn.jsdelivr.net/npm/@stlite/browser@__STLITE__/build/stlite.js";
    const archivos = __ARCHIVOS__;
    const files = Object.fromEntries(archivos.map((ruta) => [ruta, { url: "./" + ruta }]));
    mount(
      {
        requirements: __REQUISITOS__,
        entrypoint: "app.py",
        files,
        idbfsMountpoints: ["/mnt"],
        env: { PROYECCION_DATA_DIR: "/mnt/datos", PROYECCION_EN_NAVEGADOR: "1" },
        streamlitConfig: { "client.toolbarMode": "viewer", "theme.primaryColor": "#2a78d6" },
      },
      document.getElementById("root"),
    );
    const observador = new MutationObserver(() => {
      if (document.getElementById("root").childElementCount) {
        document.getElementById("cargando").remove();
        observador.disconnect();
      }
    });
    observador.observe(document.getElementById("root"), { childList: true });
  </script>
</body>
</html>
"""


def construir() -> list[str]:
    if SITIO.exists():
        shutil.rmtree(SITIO)
    SITIO.mkdir()
    rutas = list(ARCHIVOS)
    for carpeta in CARPETAS:
        for p in sorted((RAIZ / carpeta).rglob("*")):
            if p.is_file() and p.suffix in EXTENSIONES and "__pycache__" not in p.parts:
                rutas.append(p.relative_to(RAIZ).as_posix())
    for r in rutas:
        destino = SITIO / r
        destino.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(RAIZ / r, destino)
    html = (PLANTILLA.replace("__STLITE__", STLITE)
            .replace("__ARCHIVOS__", json.dumps(rutas, ensure_ascii=False))
            .replace("__REQUISITOS__", json.dumps(REQUISITOS)))
    (SITIO / "index.html").write_text(html, encoding="utf-8")
    (SITIO / ".nojekyll").write_text("", encoding="utf-8")
    print(f"Sitio construido en {SITIO} ({len(rutas)} archivos)")
    return rutas


if __name__ == "__main__":
    construir()
