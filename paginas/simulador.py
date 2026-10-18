import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import factores as fac
from core import simulador
from core.esquema import MESES
from core.maestros import unidad_grupo
from ui.comun import (editor, COLOR_ACTUAL, COLOR_ANTERIOR, aviso_privacidad, estado, mostrar, nombres_unidades,
                      requiere_ingresos, requiere_maestros)
from ui.estado_proyeccion import calcular

aviso_privacidad()
st.title("Simulador por unidad")
st.write("Simulación a varios años de pasajeros e ingresos de una unidad aeroportuaria: crecimiento del tráfico, "
         "reajuste por IPC, tarifas de derecho de embarque, tipo de cambio y escenarios de pago al concesionario "
         "por pasajero embarcado (TPE). Genera un Excel con fórmulas vivas para enviar al solicitante.")
e = estado()
if not (requiere_maestros(e) and requiere_ingresos(e)):
    st.stop()

ing = e["ingresos"]
nombres = nombres_unidades(e)
anio_base = e["ultimo_ingreso"][0]
unidades = sorted(ing["UNIDAD_GRUPO"].astype(int).unique(), key=lambda u: -ing.loc[ing["UNIDAD_GRUPO"] == u, "MONTO"].sum())
c1, c2, c3 = st.columns([3, 1, 1])
unidad = c1.selectbox("Unidad", unidades, format_func=lambda u: f"{u} · {nombres.get(int(u), '')}")
anio_final = c2.number_input("Proyectar hasta", anio_base + 1, anio_base + 10, anio_base + 5)
inicio_tpe = c3.number_input("Inicio de la concesión", anio_base, int(anio_final), anio_base + 1)
anios_proy = list(range(anio_base, int(anio_final) + 1))

# ---------------------------------------------------------------- Valores iniciales
grupos = unidad_grupo(e["maestros"].unidades)
pax = e["pax"].copy()
if not pax.empty:
    pax["GRUPO"] = pax["UNIDAD"].astype(int).map(lambda u: grupos.get(u, u))
    pax = pax[pax["GRUPO"] == unidad]
anios_pax = sorted(set(pax["ANIO"].astype(int))) if not pax.empty else []
anios_hist = sorted({a for a in anios_pax + sorted(ing["ANIO"].astype(int).unique()) if a < anio_base})


def pax_mensual(tipo):
    d = {}
    for a in anios_hist + [anio_base]:
        p = pax[(pax["ANIO"] == a) & (pax["TIPO"] == tipo)] if not pax.empty else pax
        valores = p.groupby("MES")["VALOR"].sum() if not p.empty else pd.Series(dtype=float)
        d[a] = [float(valores[m]) if m in valores.index else (0.0 if a < anio_base else None) for m in range(1, 13)]
    return d


def crec_observado(tipo):
    if pax.empty:
        return 0.03
    act = pax[(pax["ANIO"] == anio_base) & (pax["TIPO"] == tipo)]
    meses = act["MES"].unique()
    prev = pax[(pax["ANIO"] == anio_base - 1) & (pax["TIPO"] == tipo) & (pax["MES"].isin(meses))]
    return float(act["VALOR"].sum() / prev["VALOR"].sum() - 1) if prev["VALOR"].sum() > 0 else 0.03


sup_fac = fac.cargar_supuestos()
categoria = e["maestros"].unidades.set_index("unidad")["categoria"].get(unidad)
clase_nac = "NAC_2C" if pd.notna(categoria) and int(categoria) == 2 else "NAC_1C"
tarifas = fac.tarifas_mensuales(fac.periodo(anio_base, 12), fac.periodo(anio_base, 12))
tarifa_nac_ini = float(tarifas[clase_nac].iloc[-1] or 0) if not tarifas.empty and pd.notna(tarifas[clase_nac].iloc[-1]) else 0.0
tarifa_int_ini = float(tarifas["INT_MAS500"].iloc[-1]) if not tarifas.empty and pd.notna(tarifas["INT_MAS500"].iloc[-1]) else 25.0
dolar_ult = fac.serie("dolar", fac.periodo(anio_base, 1), fac.periodo(anio_base, 12))["valor"].dropna()
tc_defecto = float(dolar_ult.mean()) if not dolar_ult.empty else 900.0

with st.spinner("Obteniendo la proyección del año en curso…"):
    res = calcular(e)
proy_u = res.ingresos[(res.ingresos["UNIDAD"] == unidad)]
por_concepto = proy_u.groupby(["ANIO", "CONCEPTO_PROY"])["MONTO"].sum()


def concepto_sim(anio, c):
    if c == "TASAS":
        return por_concepto.get((anio, "TASAS_NAC"), 0.0) + por_concepto.get((anio, "TASAS_INT"), 0.0)
    return por_concepto.get((anio, c), 0.0)


# ---------------------------------------------------------------- Supuestos
st.subheader("Supuestos")
crec_n, crec_i = crec_observado("Nacional"), crec_observado("Internacional")
filas = []
for a in anios_proy:
    ipc = sup_fac["ipc_anual_esperado"].get(str(a), 0.03)
    filas.append({"Año": a,
                  "Crec. PAX nacional (%)": round(crec_n * 100, 1) if a == anio_base else 3.0,
                  "Crec. PAX internacional (%)": round(crec_i * 100, 1) if a == anio_base else 3.0,
                  "Reajuste IPC (%)": round(ipc * 100, 2),
                  "Tarifa D° emb. internacional (USD)": tarifa_int_ini,
                  "Tipo de cambio ($/USD)": float(sup_fac["dolar_proyectado"].get(str(a), tc_defecto))})
supuestos = editor(pd.DataFrame(filas), f"sim_sup_{unidad}_{anio_final}", hide_index=True, width="stretch",
                   disabled=["Año"])
st.caption(f"El crecimiento de {anio_base} completa los meses sin dato real a partir del mismo mes de {anio_base - 1} "
           f"(por defecto, el crecimiento observado de la unidad).")

c1, c2 = st.columns(2)
with c1:
    tarifa_nac = st.number_input(f"Tarifa D° embarque nacional {anio_base} ($) — {fac.CLASES_TARIFA[clase_nac][0]}",
                                 value=tarifa_nac_ini, step=1.0)
    st.write(f"**Ingresos {anio_base} (real + proyectado)** — base para el reajuste por IPC:")
    base_df = pd.DataFrame({"Concepto": [simulador.CONCEPTOS_SIM[c] for c in simulador.CONCEPTOS_REAJUSTABLES],
                            "clave": simulador.CONCEPTOS_REAJUSTABLES,
                            "Monto ($)": [round(concepto_sim(anio_base, c)) for c in simulador.CONCEPTOS_REAJUSTABLES]})
    base_ed = editor(base_df, f"sim_base_{unidad}", hide_index=True, disabled=["Concepto"],
                     column_config={"clave": None, "Monto ($)": st.column_config.NumberColumn("Monto ($)", format="localized")})
with c2:
    st.write("**Escenarios de TPE** ($ por pasajero embarcado en el primer año; luego se reajusta por IPC):")
    tpe_ed = st.data_editor(pd.DataFrame({"TPE ($/pax)": pd.Series([float("nan")] * 2, dtype=float)}), num_rows="dynamic", hide_index=True,
                            key=f"sim_tpe_{unidad}")
    notas = st.text_area("Notas para el Excel", "Crecimientos y tarifas sujetos a revisión.")

with st.expander("Pasajeros mensuales (editar si es necesario)"):
    pn, pi = pax_mensual("Nacional"), pax_mensual("Internacional")
    if pax.empty:
        st.info("No hay pasajeros cargados para esta unidad: ingrésalos aquí o carga el reporte COPAE.")
    eds = {}
    for etiqueta, datos in (("Nacional", pn), ("Internacional", pi)):
        st.write(f"**{etiqueta}** (vacío = se proyecta con el crecimiento del año)")
        df = pd.DataFrame(datos, index=MESES)
        df.columns = [str(c) for c in df.columns]
        eds[etiqueta] = editor(df, f"sim_pax_{etiqueta}_{unidad}", width="stretch")

# ---------------------------------------------------------------- Cálculo
def a_dict(df):
    return {int(c): [None if pd.isna(v) else float(v) for v in df[c].tolist()] for c in df.columns}


s = simulador.SupuestosSimulacion(
    nombre=f"{nombres.get(int(unidad), unidad)} — Simulación de ingresos",
    anio_base=anio_base, anio_final=int(anio_final),
    pax_nac=a_dict(eds["Nacional"]), pax_int=a_dict(eds["Internacional"]),
    crec_nac={int(r["Año"]): r["Crec. PAX nacional (%)"] / 100 for _, r in supuestos.iterrows()},
    crec_int={int(r["Año"]): r["Crec. PAX internacional (%)"] / 100 for _, r in supuestos.iterrows()},
    ipc={int(r["Año"]): r["Reajuste IPC (%)"] / 100 for _, r in supuestos.iterrows()},
    tarifa_nac=float(tarifa_nac),
    tarifa_int_usd={int(r["Año"]): float(r["Tarifa D° emb. internacional (USD)"]) for _, r in supuestos.iterrows()},
    tipo_cambio={int(r["Año"]): float(r["Tipo de cambio ($/USD)"]) for _, r in supuestos.iterrows()},
    ingresos_base={r["clave"]: float(r["Monto ($)"] or 0) for _, r in base_ed.iterrows()},
    ingresos_historicos={a: {c: float(concepto_sim(a, c)) for c in simulador.CONCEPTOS_SIM} for a in anios_hist},
    tpe=[float(v) for v in tpe_ed["TPE ($/pax)"].dropna().tolist()],
    anio_inicio_tpe=int(inicio_tpe),
    notas=notas,
)
r = simulador.calcular(s)

st.subheader("Resultados")
mostrar(r.pax_anual, 0)
mostrar(r.ingresos, 0)
if not r.pagos.empty:
    mostrar(r.pagos, 0)

fig = go.Figure()
anios_r = [c for c in r.ingresos.columns]
fig.add_bar(x=[str(a) for a in anios_r], y=r.ingresos.loc["Total", anios_r] / 1e6, name="Ingresos totales",
            marker_color=[COLOR_ANTERIOR if a < anio_base else COLOR_ACTUAL for a in anios_r],
            hovertemplate="%{x}: MM$ %{y:,.0f}<extra></extra>")
fig.update_layout(title="Ingresos totales por año (MM$) — naranjo: real, azul: base y proyección", height=340,
                  margin=dict(l=10, r=10, t=60, b=10), separators=",.", showlegend=False, bargap=0.35)
fig.update_yaxes(gridcolor="rgba(128,128,128,0.2)", tickformat=",.0f")
st.plotly_chart(fig, width="stretch")

st.download_button("Descargar simulación (Excel con fórmulas)", simulador.exportar_excel(s),
                   file_name=f"simulacion_{unidad}_{anio_base}-{anio_final}.xlsx", type="primary",
                   icon=":material/download:")
