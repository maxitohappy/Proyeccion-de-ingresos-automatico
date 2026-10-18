import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import control
from core.esquema import CONCEPTOS_PROYECCION, MESES
from ui.comun import (COLOR_ACTUAL, COLOR_NEGATIVO, aviso_privacidad, estado, excel_de_tablas, mostrar,
                      nombres_unidades, numero, requiere_ingresos, requiere_maestros)
from ui.estado_proyeccion import calcular

aviso_privacidad()
st.title("Control vs proyección anterior")
st.write("Contrasta la proyección actual con una proyección guardada (actividad 8) y descompone las diferencias en "
         "sus variables determinantes: pasajeros, operaciones, dólar, tarifa/IPC y otros (actividad 9).")
e = estado()
if not (requiere_maestros(e) and requiere_ingresos(e)):
    st.stop()
snaps = control.listar_snapshots()
if not snaps:
    st.info("Aún no hay proyecciones guardadas. Guarda una en **Proyección de ingresos**; el próximo mes podrás "
            "compararla aquí.")
    st.stop()

opciones = {s["id"]: f"{s['nombre']} · {s['creado'][:10]}" for s in snaps}
c1, c2 = st.columns(2)
sid_ant = c1.selectbox("Proyección anterior", list(opciones), format_func=opciones.get)
contra = c2.selectbox("Comparar contra", ["actual"] + [s for s in opciones if s != sid_ant],
                      format_func=lambda s: "Proyección actual (con los datos cargados hoy)" if s == "actual" else opciones[s])
anterior = control.cargar_snapshot(sid_ant)
if contra == "actual":
    with st.spinner("Calculando proyección actual…"):
        nueva = calcular(e).ingresos
else:
    nueva = control.cargar_snapshot(contra)["ingresos"]
meta = anterior["meta"]
if meta.get("comentario"):
    st.caption(f"Comentario de la proyección anterior: {meta['comentario']}")

comp = control.comparar(nueva, anterior["ingresos"])
anios = sorted(comp["ANIO"].unique())
anio = st.radio("Año", [a for a in anios if a >= e["ultimo_ingreso"][0]], horizontal=True)
nombres = nombres_unidades(e)

# Meses que se cerraron desde la proyección anterior: real vs lo que se había proyectado.
cerrados = control.meses_cerrados_desde_anterior(comp)
if cerrados:
    st.subheader("Meses cerrados desde la proyección anterior: real vs proyectado")
    d = comp[comp["ESTADO"] == "Cerrado desde la proyección anterior"]
    t = d.groupby("CONCEPTO_PROY")[["R0", "R1"]].sum()
    t = t.reindex([c for c in CONCEPTOS_PROYECCION if c in t.index])
    t.index = [CONCEPTOS_PROYECCION[c] for c in t.index]
    t.loc["Total"] = t.sum()
    t.columns = ["Proyectado", "Real"]
    t["Diferencia"] = t["Real"] - t["Proyectado"]
    t["Variación"] = t["Real"] / t["Proyectado"].where(t["Proyectado"] != 0) - 1
    st.caption("Meses: " + ", ".join(control.texto_mes(a, m) for a, m in cerrados))
    mostrar(t, 1, millones=True, porcentajes=["Variación"])

st.subheader(f"Proyección {anio}: anterior vs actual")
res = control.resumen_efectos(comp, anio)
mostrar(res, 1, millones=True)
st.caption("Millones de pesos. Los efectos suman exactamente la diferencia.")

efectos = res.loc["Total", control.EFECTOS]
efectos = efectos[efectos.abs() > 0]
if not efectos.empty:
    total_ant, total_act = res.loc["Total", "Proyección anterior"], res.loc["Total", "Proyección actual"]
    fig = go.Figure(go.Waterfall(
        x=["Proyección anterior"] + list(efectos.index) + ["Proyección actual"],
        y=[total_ant / 1e6] + list(efectos.values / 1e6) + [total_act / 1e6],
        measure=["absolute"] + ["relative"] * len(efectos) + ["total"],
        increasing=dict(marker=dict(color=COLOR_ACTUAL)), decreasing=dict(marker=dict(color=COLOR_NEGATIVO)),
        totals=dict(marker=dict(color="#52514e")), connector=dict(line=dict(color="rgba(128,128,128,0.4)", width=1)),
        text=[numero(v / 1e6) for v in [total_ant] + list(efectos.values) + [total_act]], textposition="outside",
        hovertemplate="%{x}: MM$ %{y:,.0f}<extra></extra>",
    ))
    rango = [min(total_ant, total_act) / 1e6 * 0.97, max(total_ant, total_act) / 1e6 * 1.02]
    fig.update_layout(title=f"De la proyección anterior a la actual, {anio} (MM$)", height=400, showlegend=False,
                      margin=dict(l=10, r=10, t=60, b=10), separators=",.")
    fig.update_yaxes(range=rango, gridcolor="rgba(128,128,128,0.2)", tickformat=",.0f")
    st.plotly_chart(fig, width="stretch")

st.subheader("Detalle por unidad")
d = comp[comp["ANIO"] == anio]
pu = d.groupby("UNIDAD")[["R0", "R1", "DIFERENCIA"] + control.EFECTOS].sum()
pu = pu.sort_values("DIFERENCIA", key=lambda s: s.abs(), ascending=False)
pu.insert(0, "Unidad", [nombres.get(int(u), str(u)) for u in pu.index])
pu = pu.rename(columns={"R0": "Anterior", "R1": "Actual", "DIFERENCIA": "Diferencia"})
mostrar(pu, 1, millones=True, altura=420)

st.download_button(
    "Descargar análisis de diferencias (Excel)",
    excel_de_tablas({"Resumen": res, "Por unidad": pu,
                     "Detalle": d.assign(MES=d["MES"].map(lambda m: MESES[int(m) - 1])).drop(columns=["ORIGEN0", "ORIGEN1"])}),
    file_name=f"diferencias_vs_{meta['nombre'][:20]}.xlsx".replace(" ", "_"), icon=":material/download:",
)

with st.expander("Administrar proyecciones guardadas"):
    tabla = pd.DataFrame([{"Nombre": s["nombre"], "Creada": s["creado"].replace("T", " "),
                           "Último mes cerrado": control.texto_mes(*s["ultimo_cerrado"]),
                           **{f"Total {a}": v / 1e6 for a, v in s["totales"].items()}, "id": s["id"]} for s in snaps])
    mostrar(tabla.drop(columns=["id"]), 1)
    borrar = st.selectbox("Eliminar", [""] + list(opciones), format_func=lambda s: opciones.get(s, ""))
    if borrar and st.button("Eliminar proyección", icon=":material/delete:"):
        control.eliminar_snapshot(borrar)
        st.rerun()
