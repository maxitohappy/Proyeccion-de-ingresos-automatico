import time

import streamlit as st

from core import historico, maestros, tablas
from core.clasificacion import clasificar, montos_atipicos
from core.esquema import MESES, UNIDADES_DESCARTADAS_DEFECTO
from core.ingest import leer_informe
from ui.comun import aviso_privacidad, estado, excel_de_tablas, mostrar, requiere_maestros

aviso_privacidad()
st.title("Cargar informe de gestión")
st.write(
    "Sube el informe **Ingresos Operaciones por Concepto** del SAC (*Informe Gestión → ingresos Operaciones por "
    "Concepto*, todas las unidades). Sirve el libro Excel de gestión completo (se busca la hoja con los encabezados "
    "del SAC) o un export en **CSV**, que se lee mucho más rápido."
)

e = estado()
archivo = st.file_uploader("Informe del SAC", type=["xlsx", "xlsm", "csv", "txt"])

if archivo and not e["maestros_ok"]:
    st.info("No hay maestros registrados. Si el archivo es el libro *Informe de Gestión* (con las hojas "
            "PlanDeCuentas, Conceptos, asociación y matriz), puedes importarlos desde él.")
    if st.button("Importar maestros desde este libro", icon=":material/database:"):
        with st.spinner("Leyendo hojas de maestros…"):
            m, avisos = maestros.importar_desde_libro(archivo)
        if m.completos:
            maestros.guardar(m)
            st.success(" ".join(avisos))
            st.rerun()
        else:
            st.error("No se encontraron las hojas de maestros. " + " ".join(avisos))

if not requiere_maestros(e):
    st.stop()

descartadas = st.multiselect(
    "Unidades a descartar (ingresos transferidos a la Sociedad Concesionaria)",
    options=sorted(set(UNIDADES_DESCARTADAS_DEFECTO) | set(e["maestros"].unidades["unidad"].dropna().astype(int))),
    default=UNIDADES_DESCARTADAS_DEFECTO,
)

if archivo:
    clave_archivo = (archivo.name, archivo.size, tuple(descartadas))
    if st.session_state.get("carga_clave") != clave_archivo:
        barra = st.progress(0.0, text="Leyendo informe…")
        inicio = time.time()

        def progreso(n):
            barra.progress(min(n / 120_000, 0.95), text=f"Leyendo informe… {n:,} filas".replace(",", "."))

        try:
            lectura = leer_informe(archivo, archivo.name, progreso)
        except ValueError as err:
            barra.empty()
            st.error(str(err))
            st.stop()
        barra.progress(1.0, text="Clasificando…")
        resultado = clasificar(lectura.datos, e["maestros"], descartadas)
        barra.empty()
        st.session_state["carga_clave"] = clave_archivo
        st.session_state["carga"] = (lectura, resultado, time.time() - inicio)

    lectura, resultado, segundos = st.session_state["carga"]
    agg = historico.agregar(resultado.datos)
    periodos = historico.periodos_disponibles(agg)
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Filas leídas", f"{lectura.filas_leidas:,}".replace(",", "."), help=f"Hoja: {lectura.hoja}")
    c2.metric("Ingresos clasificados", f"MM$ {resultado.total / 1e6:,.0f}".replace(",", "."))
    c3.metric("Descartados (unidad 5220 u otras)", f"MM$ {resultado.descartados['MONTO'].sum() / 1e6:,.0f}".replace(",", "."))
    c4.metric("Períodos", f"{MESES[periodos[0][1] - 1][:3]} {periodos[0][0]} – {MESES[periodos[-1][1] - 1][:3]} {periodos[-1][0]}"
              if periodos else "—", help=f"Lectura en {segundos:.0f} s")
    for a in lectura.advertencias:
        st.caption(f"⚠️ {a}")

    st.subheader("Validaciones")
    alertas = dict(resultado.alertas)
    atipicos = montos_atipicos(agg, historico._reemplazar_periodos(e["ingresos"], agg))
    if not atipicos.empty:
        alertas["Variaciones atípicas del último mes vs. promedio 3 meses"] = atipicos
    hay = False
    for nombre, df in alertas.items():
        if df is None or df.empty:
            continue
        hay = True
        with st.expander(f"⚠️ {nombre}: {len(df)}"):
            mostrar(df, porcentajes=["variacion"] if "variacion" in df.columns else None)
    if not hay:
        st.success("Sin observaciones: todas las cuentas tienen clasificación y no hay montos atípicos.")
    else:
        st.download_button(
            "Descargar observaciones (Excel) para la Sección Tasas Aeronáuticas",
            excel_de_tablas({k: v for k, v in alertas.items() if v is not None and not v.empty}),
            file_name="observaciones_informe_gestion.xlsx", icon=":material/download:",
        )

    st.subheader("Vista previa")
    anios = sorted(agg["ANIO"].unique())
    anio = st.selectbox("Año", anios, index=len(anios) - 1)
    t1, t2 = st.tabs(["Por concepto", "Derecho de embarque por clase"])
    with t1:
        mostrar(tablas.por_concepto(agg, anio).reset_index(), millones=True, decimales=1)
        st.caption("Cifras en millones de pesos.")
    with t2:
        mostrar(tablas.resumen_clases_de(agg, anio), millones=True, decimales=1)

    existentes = set(historico.periodos_disponibles(e["ingresos"]))
    reemplaza = sorted(existentes & set(periodos))
    st.subheader("Guardar en la base histórica")
    if reemplaza:
        st.write(f"Se **reemplazarán** {len(reemplaza)} meses ya guardados (el informe es acumulado e incluye "
                 "regularizaciones) y se agregarán los nuevos.")
    if st.button("Guardar ingresos en la base", type="primary", icon=":material/save:"):
        historico.guardar_ingresos(agg)
        st.success(f"Guardado. Último mes cerrado: {MESES[periodos[-1][1] - 1]} {periodos[-1][0]}.")
        st.page_link("paginas/ingresos_concepto.py", label="Ver ingresos por concepto", icon=":material/table_chart:")
