"""Proyección de Ingresos Automático – punto de entrada (Streamlit / stlite)."""
import streamlit as st

st.set_page_config(page_title="Proyección de Ingresos", page_icon=":material/flight_takeoff:", layout="wide")

paginas = {
    "": [st.Page("paginas/inicio.py", title="Inicio", icon=":material/home:", default=True)],
    "Datos del mes": [
        st.Page("paginas/carga_informe.py", title="Cargar informe de gestión", icon=":material/upload_file:"),
        st.Page("paginas/ingresos_concepto.py", title="Ingresos por concepto", icon=":material/table_chart:"),
        st.Page("paginas/factores.py", title="Factores económicos y tarifas", icon=":material/currency_exchange:"),
        st.Page("paginas/pasajeros.py", title="Pasajeros (PAX)", icon=":material/groups:"),
        st.Page("paginas/operaciones.py", title="Operaciones", icon=":material/flight_land:"),
    ],
    "Proyección y análisis": [
        st.Page("paginas/proyeccion.py", title="Proyección de ingresos", icon=":material/trending_up:"),
        st.Page("paginas/control.py", title="Control vs proyección anterior", icon=":material/compare_arrows:"),
        st.Page("paginas/simulador.py", title="Simulador por unidad", icon=":material/science:"),
        st.Page("paginas/reportes.py", title="Reportes (Excel y PPT)", icon=":material/description:"),
    ],
    "Configuración": [
        st.Page("paginas/maestros.py", title="Maestros y respaldo", icon=":material/database:"),
    ],
}
st.navigation(paginas).run()
