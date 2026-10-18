import pandas as pd
import streamlit as st

from core import control, historico
from core.esquema import MESES
from core.maestros import unidad_grupo
from core.reportes import excel, ppt
from core.reportes.texto import puntos_analisis
from ui.comun import aviso_privacidad, estado, nombres_unidades, numero, porcentaje, requiere_ingresos, requiere_maestros
from ui.estado_proyeccion import calcular

aviso_privacidad()
st.title("Reportes")
st.write("Genera el **cuadro resumen** (Excel) y la **presentación** (PPT, con gráficos editables) de la proyección "
         "actual (actividades 10, 12 y 15 del instructivo).")
e = estado()
if not (requiere_maestros(e) and requiere_ingresos(e)):
    st.stop()

with st.spinner("Calculando proyección…"):
    res = calcular(e)
anio, mes = res.ultimo_cerrado
ing = e["ingresos"]
nombres = nombres_unidades(e)
anteriores = historico.cargar_totales_anteriores()
serie_total = historico.serie_total_mensual(ing, anteriores)

c1, c2, c3 = st.columns(3)
mes_elab = MESES[mes % 12] + " " + str(anio if mes < 12 else anio + 1)
nombre = c1.text_input("Nombre de la proyección", f"Proyección {mes_elab}")
snaps = control.listar_snapshots()
opciones = {"": "Sin comparación"} | {s["id"]: f"{s['nombre']} · {s['creado'][:10]}" for s in snaps}
sid = c2.selectbox("Comparar con proyección anterior", list(opciones), format_func=opciones.get,
                   index=1 if len(opciones) > 1 else 0)
anios_ref = sorted(set(serie_total["ANIO"].astype(int)) - {anio})
ref_defecto = 2019 if 2019 in anios_ref else (anios_ref[0] if anios_ref else None)
anio_ref = c3.selectbox("Año de referencia para % de recuperación", [None] + anios_ref,
                        index=([None] + anios_ref).index(ref_defecto),
                        format_func=lambda a: "Año anterior" if a is None else str(a))
if not anios_ref:
    st.caption("Para comparar con 2019 u otros años, carga los totales mensuales en *Maestros y respaldo → Totales de "
               "años anteriores*.")

comparacion = resumen_comp = meta = None
if sid:
    snap = control.cargar_snapshot(sid)
    meta = snap["meta"]
    comparacion = control.comparar(res.ingresos, snap["ingresos"])
    resumen_comp = control.resumen_efectos(comparacion, anio)
real_prev = float(ing.loc[ing["ANIO"] == anio - 1, "MONTO"].sum()) or None

# PAX por unidad: año en curso (real + proyectado) vs año anterior.
pax_tabla = None
if not res.trafico.empty:
    t = res.trafico[res.trafico["SERIE"].str.startswith("PAX")]
    actual = t[t["ANIO"] == anio].groupby("UNIDAD")["VALOR"].sum()
    grupos = unidad_grupo(e["maestros"].unidades)
    pax_hist = e["pax"].assign(GRUPO=e["pax"]["UNIDAD"].astype(int).map(lambda u: grupos.get(u, u)))
    previo = pax_hist[pax_hist["ANIO"] == anio - 1].groupby("GRUPO")["VALOR"].sum()
    if not actual.empty:
        tabla = pd.DataFrame({f"PAX {anio - 1}": previo, f"PAX {anio} (proy.)": actual}).fillna(0)
        tabla = tabla.sort_values(f"PAX {anio} (proy.)", ascending=False)
        tabla["Variación"] = tabla.iloc[:, 1] / tabla.iloc[:, 0].where(tabla.iloc[:, 0] > 0) - 1
        tabla.loc["Total"] = [tabla.iloc[:, 0].sum(), tabla.iloc[:, 1].sum(), tabla.iloc[:, 1].sum() / tabla.iloc[:, 0].sum() - 1
                              if tabla.iloc[:, 0].sum() else None]
        tabla.index = [nombres.get(int(u), str(u)) if u != "Total" else "Total" for u in tabla.index]
        pax_tabla = pd.DataFrame({c: [numero(v) for v in tabla[c]] for c in tabla.columns[:2]}, index=tabla.index)
        pax_tabla["Variación"] = [porcentaje(v) for v in tabla["Variación"]]

st.subheader("Análisis automático")
for p in puntos_analisis(res, comparacion, meta, real_prev):
    st.write("•", p)

st.subheader("Descargas")
c1, c2 = st.columns(2)
with c1:
    if st.button("Generar cuadro resumen (Excel)", icon=":material/table:"):
        st.session_state["xlsx_resumen"] = excel.generar(res, nombre, comparacion, resumen_comp, meta, nombres, real_prev)
    if st.session_state.get("xlsx_resumen"):
        st.download_button("Descargar Excel", st.session_state["xlsx_resumen"], type="primary",
                           file_name=f"{nombre.replace(' ', '_')}_cuadro_resumen.xlsx", icon=":material/download:")
with c2:
    if st.button("Generar presentación (PPT)", icon=":material/slideshow:"):
        with st.spinner("Generando presentación…"):
            st.session_state["pptx"] = ppt.generar(res, nombre, serie_total, anio_ref, comparacion, resumen_comp, meta,
                                                   pax_tabla, real_prev)
    if st.session_state.get("pptx"):
        st.download_button("Descargar PPT", st.session_state["pptx"], type="primary",
                           file_name=f"{nombre.replace(' ', '_')}.pptx", icon=":material/download:")
st.caption("Los gráficos del PPT son nativos de PowerPoint: se pueden editar (colores, títulos, datos) después.")
