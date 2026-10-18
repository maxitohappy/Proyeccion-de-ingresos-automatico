from datetime import date

import pandas as pd
import streamlit as st

from core import almacenamiento as alm
from core import historico, maestros
from ui.comun import EN_NAVEGADOR, aviso_privacidad, mostrar

aviso_privacidad()
st.title("Maestros y respaldo")

tab_imp, tab_edit, tab_hist, tab_resp = st.tabs(
    ["Importar maestros", "Editar maestros", "Totales de años anteriores", "Respaldo de datos"])

with tab_imp:
    st.write("Los maestros (plan de cuentas, conceptos y unidades) se leen desde el libro **Informe de Gestión** "
             "(hojas *PlanDeCuentas*, *Conceptos*, *asociación* y *matriz*). Quedan guardados solo en este equipo.")
    libro = st.file_uploader("Libro Informe de Gestión", type=["xlsx", "xlsm"], key="libro_maestros")
    if libro and st.button("Importar", type="primary", icon=":material/download_done:"):
        with st.spinner("Leyendo hojas de maestros…"):
            m, avisos = maestros.importar_desde_libro(libro)
        for a in avisos:
            st.write("•", a)
        if m.completos:
            maestros.guardar(m)
            st.success("Maestros guardados.")
        else:
            st.error("Faltan hojas obligatorias (PlanDeCuentas y asociación).")

m = maestros.cargar()
with tab_edit:
    if not m.completos:
        st.info("Aún no hay maestros importados.")
    else:
        st.caption("Edita directamente y presiona **Guardar cambios**. Columna *asociar_a*: código de la unidad a la que "
                   "se suman sus ingresos (vacío = unidad propia).")
        sub = st.radio("Tabla", ["Unidades", "Plan de cuentas", "Conceptos"], horizontal=True)
        if sub == "Unidades":
            editada = st.data_editor(m.unidades, num_rows="dynamic", width="stretch", height=520, key="ed_unidades")
        elif sub == "Plan de cuentas":
            editada = st.data_editor(m.plan, num_rows="dynamic", width="stretch", height=520, key="ed_plan")
        else:
            editada = st.data_editor(m.conceptos, num_rows="dynamic", width="stretch", key="ed_conceptos")
        if st.button("Guardar cambios", icon=":material/save:"):
            if sub == "Unidades":
                m.unidades = maestros._tipar_unidades(editada)
            elif sub == "Plan de cuentas":
                m.plan = editada
            else:
                m.conceptos = editada
            maestros.guardar(m)
            st.success("Cambios guardados. Vuelve a cargar el informe para reclasificar con los nuevos maestros.")

with tab_hist:
    st.write("Para los gráficos de comparación desde 2019 se pueden cargar **totales mensuales de años anteriores** "
             "(por ejemplo, desde presentaciones previas). CSV o Excel con columnas **ANIO, MES, MONTO** (pesos). "
             "Si un año/mes también está en la base detallada, manda la base detallada.")
    ant = historico.cargar_totales_anteriores()
    archivo = st.file_uploader("Totales mensuales", type=["csv", "xlsx"], key="totales_ant")
    if archivo:
        if archivo.name.lower().endswith(".csv"):
            texto = archivo.getvalue().decode("utf-8-sig", errors="replace")
            df = pd.read_csv(archivo, sep=";" if texto.count(";") > texto.count(",") else ",")
        else:
            df = pd.read_excel(archivo)
        df.columns = [str(c).strip().upper().replace("AÑO", "ANIO") for c in df.columns]
        if {"ANIO", "MES", "MONTO"} <= set(df.columns):
            df = df[["ANIO", "MES", "MONTO"]].dropna()
            st.write(f"{len(df)} filas, años {sorted(df['ANIO'].astype(int).unique())}")
            if st.button("Guardar totales", icon=":material/save:"):
                historico.guardar_totales_anteriores(df)
                st.success("Guardado.")
                st.rerun()
        else:
            st.error("El archivo debe tener columnas ANIO, MES y MONTO.")
    if not ant.empty:
        t = ant.pivot_table(index="MES", columns="ANIO", values="MONTO", aggfunc="sum")
        mostrar(t, 1, millones=True)

with tab_resp:
    if EN_NAVEGADOR:
        st.warning("Los datos se guardan en el almacenamiento de **este navegador**. Si borras los datos del sitio, "
                   "usas otro navegador o cambias de equipo, se pierden: descarga un respaldo cada mes.")
    archivos = alm.listar()
    st.write(f"Archivos guardados: **{len(archivos)}**")
    if archivos:
        st.download_button("Descargar respaldo (.zip)", alm.exportar_respaldo(),
                           file_name=f"respaldo_proyeccion_{date.today():%Y%m%d}.zip", icon=":material/download:",
                           type="primary")
    restaurar = st.file_uploader("Restaurar respaldo (.zip)", type=["zip"])
    reemplazar = st.checkbox("Borrar los datos actuales antes de restaurar")
    if restaurar and st.button("Restaurar", icon=":material/restore:"):
        n = alm.importar_respaldo(restaurar.getvalue(), reemplazar)
        st.success(f"{n} archivos restaurados.")
    with st.expander("Borrar todos los datos guardados"):
        st.write("Elimina maestros, base histórica, factores manuales, proyecciones guardadas y configuración.")
        if st.checkbox("Confirmo que quiero borrar todo") and st.button("Borrar todo", icon=":material/delete:"):
            for rel in alm.listar():
                alm.eliminar(rel)
            st.success("Datos eliminados.")
            st.rerun()
    if archivos:
        with st.expander("Ver archivos guardados"):
            st.code("\n".join(archivos))
