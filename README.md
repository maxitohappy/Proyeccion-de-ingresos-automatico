# Proyección de Ingresos Automático

Aplicación gratuita para automatizar el proceso mensual de **proyección de ingresos operacionales** de las unidades
aeroportuarias: depuración del informe de gestión, factores económicos, pasajeros y operaciones, modelos de proyección,
control frente a la proyección anterior, simulaciones por unidad y generación del cuadro resumen (Excel) y la
presentación (PPT).

**Abrir la aplicación:** https://maxitohappy.github.io/Proyeccion-de-ingresos-automatico/

> 🔒 **Privacidad.** La app corre completamente en el navegador (Streamlit + [stlite](https://github.com/whitphx/stlite),
> WebAssembly). Los archivos que subes **no se envían a ningún servidor**, y los datos guardados quedan en el
> almacenamiento de tu navegador. Este repositorio contiene **solo código y datos ficticios**: nunca subas archivos
> reales al repositorio.

## Qué automatiza

| Actividad del proceso | En la app |
|---|---|
| Recopilar información económica (dólar, IPC, UF) | **Automático**: GitHub Actions descarga los indicadores cada día (BCCh, CMF y mindicador.cl). Los meses futuros usan los supuestos que tú defines (EEE / IPoM). |
| Depurar y verificar el informe de gestión | Lee el export del SAC, clasifica con el plan de cuentas (reemplaza los BUSCARV), descarta la unidad 5220 y genera las observaciones para Tasas Aeronáuticas. |
| Ingresos por concepto | Tablas por concepto, unidad (agrupando dependencias) y clase de derecho de embarque. |
| Pasajeros y operaciones | Carga de COPAE y SAC con mapeo de columnas recordado y los filtros del instructivo. |
| Ingresar factores y proyectar ingresos | 7 conceptos por unidad y mes: PAX/operaciones × ingreso unitario calibrado × dólar × tarifa/IPC. Escenarios y ajustes manuales. |
| Revisar la proyección anterior y el origen de las diferencias | Proyecciones guardadas y descomposición exacta en efecto pasajeros, operaciones, dólar, tarifa/IPC y otros. |
| Cuadro resumen y presentación | Excel y PPT (gráficos nativos editables) con análisis automático. |
| Solicitudes de simulación por unidad | Simulador a N años con escenarios de TPE (pago al concesionario) y Excel con fórmulas vivas. |

### Modelos de proyección

- Crecimiento interanual del año (acumulado) o de los últimos 3 meses.
- Crecimiento anual manual (por ejemplo, expectativas de IATA, ACI, OACI o ALTA).
- Promedio móvil, para series sin estacionalidad.
- Holt-Winters estacional, que se habilita solo al acumular 24 meses de historia.

Para elegir, la app muestra el error de cada método al proyectar los últimos 3 meses cerrados (*backtesting*).

## Uso mensual

1. **Cargar informe de gestión**: sube el export del SAC (*Informe Gestión → ingresos Operaciones por Concepto*).
   La primera vez, importa los maestros desde el libro *Informe de Gestión* (hojas PlanDeCuentas, Conceptos,
   asociación y matriz).
2. **Factores económicos**: revisa los datos descargados y define los supuestos (dólar e IPC esperados) y las tarifas.
3. **Pasajeros / Operaciones** (opcional): sube los reportes de COPAE y del SAC.
4. **Proyección de ingresos**: ajusta métodos y escenarios y **guarda la proyección**.
5. **Control vs anterior** y **Reportes**: explica las diferencias y descarga el Excel y el PPT.
6. **Maestros y respaldo**: descarga un respaldo `.zip` cada mes. Los datos viven en tu navegador; si borras los datos
   del sitio o cambias de equipo, restaura el respaldo.

Para probar sin datos reales, usa **Cargar datos de ejemplo** en la portada.

## Indicadores económicos automáticos

El workflow `.github/workflows/pages.yml` se ejecuta todos los días y genera `datos/economicos.json`:

| Fuente | Datos | Requisito |
|---|---|---|
| [mindicador.cl](https://mindicador.cl) | Dólar, UF, IMACEC. El IPC se calcula exactamente desde la UF diaria. | Ninguno |
| [API BDE Banco Central](https://si3.bcentral.cl/siete) | Dólar, IPC, UF, PIB, PIB regional y expectativas (EEE) | Cuenta gratuita |
| [API CMF](https://api.cmfchile.cl) | Dólar, UF, IPC | API key gratuita |

Para activar el BCCh o la CMF, agrega las credenciales como *secrets* del repositorio. Nunca se escriben en el código:

```bash
gh secret set BCCH_USER    # correo de la cuenta del BCCh
gh secret set BCCH_PASS
gh secret set CMF_APIKEY
```

Los códigos de las series del BCCh están en `datos/config_series_bcch.json`. Los de PIB, PIB regional y EEE se buscan
con `python scripts/buscar_series_bcch.py "expectativas inflación"`.

## Ejecución local (opcional)

Requiere Python 3.13. En Windows, doble clic en `iniciar.bat`. También puedes ejecutarlo así:

```bash
python -m venv .venv
.venv/Scripts/pip install -r requirements.txt     # Linux/Mac: .venv/bin/pip
.venv/Scripts/streamlit run app.py
```

En modo local los datos se guardan en `data/`, que está excluida del repositorio.

## Desarrollo

```bash
python -m pytest -q                       # pruebas (incluye prueba de humo de todas las páginas)
python scripts/generar_ejemplos.py        # regenera los datos ficticios de ejemplos/
python scripts/construir_sitio.py         # construye _site/ (lo mismo que publica GitHub Pages)
python -m http.server -d _site 8000       # prueba el sitio en http://localhost:8000
python scripts/verificar_publicacion.py   # revisar antes de cada push
```

Estructura: `core/` (lógica: lectura, clasificación, factores, modelos, proyección, control, simulador, reportes),
`paginas/` (pantallas), `ui/` (componentes), `scripts/`, `tests/`, `ejemplos/` (datos ficticios) y `datos/`
(indicadores públicos).
