@echo off
REM Inicia la app en modo local (los datos quedan en la carpeta data\)
cd /d "%~dp0"
if not exist .venv (
  echo Creando entorno por primera vez...
  python -m venv .venv
  .venv\Scripts\python -m pip install -r requirements.txt
)
.venv\Scripts\python -m streamlit run app.py
