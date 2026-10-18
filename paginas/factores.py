from datetime import date

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import factores as fac
from ui.comun import editor, COLOR_ACTUAL, COLOR_PROYECTADO, aviso_privacidad, estado, mostrar

aviso_privacidad()
st.title("Factores económicos y tarifas")

web = fac.cargar_web()
estado_fuentes = web.get("estado_fuentes", {})
c1, c2 = st.columns([2, 3])
c1.metric("Última actualización automática", (web.get("actualizado") or "—")[:16].replace("T", " "),
          help="GitHub Actions descarga los indicadores todos los días.")
with c2:
    for fuente, est in estado_fuentes.items():
        st.caption(f"{'✅' if est == 'ok' else 'ℹ️'} **{fuente}**: {est}")
st.caption("El IPC mensual se obtiene del BCCh/CMF cuando hay credenciales; si no, se calcula exactamente desde la UF "
           "diaria (IPC(m) = UF(9 de m+2) / UF(9 de m+1) − 1).")

e = estado()
hoy = date.today()
anio_base = e["ultimo_ingreso"][0] if e["ultimo_ingreso"] else hoy.year
anios = st.multiselect("Años a mostrar", list(range(anio_base - 3, anio_base + 3)), default=[anio_base - 1, anio_base, anio_base + 1])
if not anios:
    st.stop()

tab_tabla, tab_sup, tab_man, tab_tar = st.tabs(["Factores mensuales", "Supuestos de proyección", "Valores manuales", "Tarifas D° embarque"])

with tab_sup:
    st.write("Para los meses sin dato publicado se usan estos supuestos (por ejemplo, la mediana de la **Encuesta de "
             "Expectativas Económicas** del BCCh o el IPoM).")
    sup = fac.cargar_supuestos()
    filas = [{"Año": a, "Dólar proyectado ($/USD)": sup["dolar_proyectado"].get(str(a)),
              "IPC anual esperado (%)": (sup["ipc_anual_esperado"].get(str(a)) or 0) * 100 if sup["ipc_anual_esperado"].get(str(a)) is not None else None}
             for a in sorted(set(anios) | {anio_base, anio_base + 1})]
    editado = editor(pd.DataFrame(filas), "sup_editor", hide_index=True, width="stretch", disabled=["Año"])
    regla = st.selectbox("Reajuste automático de tarifas nacionales en CLP", list(fac.REGLAS_REAJUSTE),
                         index=list(fac.REGLAS_REAJUSTE).index(sup.get("regla_reajuste", "trimestral")),
                         format_func=fac.REGLAS_REAJUSTE.get)
    fuente = st.text_input("Fuente de las expectativas", sup.get("fuente_expectativas", ""))
    if st.button("Guardar supuestos", type="primary", icon=":material/save:"):
        sup["dolar_proyectado"] = {str(int(r["Año"])): float(r["Dólar proyectado ($/USD)"]) for _, r in editado.iterrows()
                                   if pd.notna(r["Dólar proyectado ($/USD)"])}
        sup["ipc_anual_esperado"] = {str(int(r["Año"])): float(r["IPC anual esperado (%)"]) / 100 for _, r in editado.iterrows()
                                     if pd.notna(r["IPC anual esperado (%)"])}
        sup["regla_reajuste"], sup["fuente_expectativas"] = regla, fuente
        fac.guardar_supuestos(sup)
        st.success("Supuestos guardados.")
        st.rerun()

with tab_tabla:
    tabla = fac.tabla_factores(anios, web)
    vista = pd.DataFrame({
        "Dólar ($/USD)": tabla["dolar"], "Fuente dólar": tabla["dolar_fuente"],
        "IPC mensual (%)": tabla["ipc"], "Fuente IPC": tabla["ipc_fuente"],
        "UF ($)": tabla["uf"], "IMACEC (%)": tabla["imacec"],
    })
    st.dataframe(vista.style.format({
        "Dólar ($/USD)": lambda v: "" if pd.isna(v) else f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        "IPC mensual (%)": lambda v: "" if pd.isna(v) else f"{v:,.2f}".replace(".", ","),
        "UF ($)": lambda v: "" if pd.isna(v) else f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", "."),
        "IMACEC (%)": lambda v: "" if pd.isna(v) else f"{v:,.1f}".replace(".", ","),
    }), width="stretch", height=480)
    resumen = []
    for a in anios:
        t = tabla[tabla.index.str.startswith(str(a))]
        resumen.append({"Año": a, "Dólar promedio": t["dolar"].mean(),
                        "IPC acumulado (%)": ((1 + t["ipc"].fillna(0) / 100).prod() - 1) * 100})
    mostrar(pd.DataFrame(resumen).set_index("Año"), 2)

    real = tabla["dolar_fuente"].fillna("").str.contains("mindicador|BCCh|CMF|Manual")
    fig = go.Figure()
    fig.add_bar(x=tabla.index[real], y=tabla["dolar"][real], name="Observado", marker_color=COLOR_ACTUAL)
    fig.add_bar(x=tabla.index[~real], y=tabla["dolar"][~real], name="Supuesto", marker_color=COLOR_PROYECTADO)
    fig.update_layout(title="Dólar promedio mensual ($/USD)", height=340, margin=dict(l=10, r=10, t=80, b=10),
                      legend=dict(orientation="h", y=1.0, yanchor="bottom"), bargap=0.25, separators=",.")
    fig.update_yaxes(range=[tabla["dolar"].min() * 0.9, tabla["dolar"].max() * 1.05], gridcolor="rgba(128,128,128,0.2)")
    st.plotly_chart(fig, width="stretch")

with tab_man:
    st.write("Registra un valor manual cuando quieras reemplazar el dato publicado (queda registrado con comentario).")
    c1, c2, c3 = st.columns(3)
    indicador = c1.selectbox("Indicador", list(fac.INDICADORES), format_func=fac.INDICADORES.get)
    anio_m = c2.selectbox("Año", list(range(anio_base - 3, anio_base + 3)), index=3)
    mes_m = c3.selectbox("Mes", list(range(1, 13)), index=hoy.month - 1)
    valor = st.number_input("Valor", value=None, format="%.4f")
    comentario = st.text_input("Comentario / fuente")
    if st.button("Registrar valor", icon=":material/edit:") and valor is not None:
        fac.guardar_manual(fac.periodo(anio_m, mes_m), indicador, valor, comentario)
        st.success("Registrado.")
        st.rerun()
    man = fac.cargar_manuales()
    if not man.empty:
        st.dataframe(man, hide_index=True, width="stretch")
        borrar = st.selectbox("Eliminar valor manual", [""] + [f"{r.indicador} {r.periodo}" for r in man.itertuples()])
        if borrar and st.button("Eliminar", icon=":material/delete:"):
            ind, per = borrar.split(" ")
            fac.guardar_manual(per, ind, None)
            st.rerun()

with tab_tar:
    st.write("Registra las tarifas vigentes y sus cambios (por ejemplo, rebajas). En los meses de reajuste sin tarifa "
             "registrada, las tarifas en CLP se reajustan automáticamente por el IPC acumulado.")
    tarifas = fac.cargar_tarifas()
    if tarifas.empty:
        tarifas = pd.DataFrame([{"vigente_desde": f"{anio_base}-01", "clase": c, "valor": None, "comentario": ""}
                                for c in fac.CLASES_TARIFA])
    ed = st.data_editor(
        tarifas, num_rows="dynamic", hide_index=True, width="stretch", key="tarifas_editor",
        column_config={
            "vigente_desde": st.column_config.TextColumn("Vigente desde (AAAA-MM)", validate=r"^\d{4}-\d{2}$"),
            "clase": st.column_config.SelectboxColumn("Clase", options=list(fac.CLASES_TARIFA)),
            "valor": st.column_config.NumberColumn("Valor (CLP o USD)", format="%.2f"),
            "comentario": st.column_config.TextColumn("Comentario"),
        },
    )
    st.caption(" · ".join(f"**{k}**: {v[0]} ({v[1]})" for k, v in fac.CLASES_TARIFA.items()))
    if st.button("Guardar tarifas", type="primary", icon=":material/save:"):
        fac.guardar_tarifas(ed.dropna(subset=["vigente_desde", "clase", "valor"]))
        st.success("Tarifas guardadas.")
        st.rerun()
    mens = fac.tarifas_mensuales(fac.periodo(min(anios), 1), fac.periodo(max(anios), 12))
    mens.columns = [fac.CLASES_TARIFA[c][0] for c in mens.columns]
    mostrar(mens.dropna(how="all", axis=1), 0)
