import streamlit as st

from core import tablas
from core.clasificacion import CLASES_DE
from ui.comun import aviso_privacidad, estado, excel_de_tablas, mostrar, nombres_unidades, requiere_ingresos

aviso_privacidad()
st.title("Ingresos por concepto")
st.write("Tablas equivalentes a las tablas dinámicas del libro de gestión, calculadas desde la base histórica "
         "(actividad 6 del instructivo: consolidación por concepto y unidad, agrupando unidades dependientes).")

e = estado()
if not requiere_ingresos(e):
    st.stop()

agg = e["ingresos"]
nombres = nombres_unidades(e)
c1, c2, c3 = st.columns([1, 1, 2])
anio = c1.selectbox("Año", e["anios_ingresos"], index=len(e["anios_ingresos"]) - 1)
en_mm = c2.toggle("Millones de pesos (MM$)", value=True)
agrupar = c3.toggle("Agrupar unidades dependientes (según maestro)", value=True)
dec = 1 if en_mm else 0

t_concepto = tablas.por_concepto(agg, anio).reset_index()
t_proy = tablas.por_concepto_proyeccion(agg, anio)
t_unidad = tablas.por_unidad(agg, anio, nombres, agrupar)
t_desc = tablas.por_descripcion(agg, anio)

tabs = st.tabs(["Por concepto", "7 conceptos de proyección", "Por unidad", "D° embarque por clase", "Ranking por descripción"])
with tabs[0]:
    mostrar(t_concepto, dec, en_mm)
with tabs[1]:
    mostrar(t_proy, dec, en_mm)
with tabs[2]:
    mostrar(t_unidad, dec, en_mm, altura=560)
with tabs[3]:
    clase = st.radio("Clase", list(CLASES_DE), format_func=CLASES_DE.get, horizontal=True)
    t_de = tablas.de_clasificaciones(agg, anio, clase, nombres)
    mostrar(t_de, dec, en_mm, altura=560)
with tabs[4]:
    mostrar(t_desc, dec, en_mm, altura=560)

st.download_button(
    "Descargar todas las tablas (Excel)",
    excel_de_tablas({
        "Por concepto": t_concepto.set_index(["Concepto", "Tipo"]) if not t_concepto.empty else t_concepto,
        "Conceptos proyeccion": t_proy, "Por unidad": t_unidad,
        **{f"DE {k}": tablas.de_clasificaciones(agg, anio, k, nombres) for k in CLASES_DE},
        "Ranking descripcion": t_desc,
    }),
    file_name=f"ingresos_por_concepto_{anio}.xlsx", icon=":material/download:",
)
