import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from core import control, modelos
from core import proyeccion as pr
from core.esquema import CONCEPTOS_PROYECCION, MESES, MESES_CORTOS
from ui.comun import (COLOR_ACTUAL, COLOR_ANTERIOR, COLOR_PROYECTADO, aviso_privacidad, estado, mostrar,
                      nombres_unidades, numero, porcentaje, requiere_ingresos, requiere_maestros)
from ui.estado_proyeccion import calcular, cargar_config, guardar_config

aviso_privacidad()
st.title("Proyección de ingresos")
e = estado()
if not (requiere_maestros(e) and requiere_ingresos(e)):
    st.stop()

config = cargar_config()
ing = e["ingresos"]
anio, mes = e["ultimo_ingreso"]
nombres = nombres_unidades(e)
hay_trafico = not (e["pax"].empty and e["ops"].empty)
st.caption(f"Real hasta **{MESES[mes - 1]} {anio}**; se proyecta hasta diciembre de {anio + 1}. "
           + ("Con datos de tráfico: DE y tasas = PAX/operaciones × ingreso unitario calibrado."
              if hay_trafico else "Sin datos de tráfico: proyección directa sobre las series de ingresos."))

# ------------------------------------------------------------------ Configuración
with st.expander("1 · Métodos de proyección", expanded=False):
    st.write("Error de cada método al proyectar los últimos 3 meses cerrados con los datos previos "
             "(WAPE: menor es mejor), calculado sobre el total nacional de cada concepto.")
    filas = []
    for c, nombre in CONCEPTOS_PROYECCION.items():
        serie = modelos.a_serie(ing[ing["CONCEPTO_PROY"] == c], "MONTO")
        ev = modelos.evaluar_metodos(serie)
        fila = {"Concepto": nombre}
        for r in ev.itertuples():
            fila[r.metodo] = r.error
        filas.append(fila)
    ev_tabla = pd.DataFrame(filas).set_index("Concepto")
    ev_tabla.columns = [modelos.METODOS[c].split(" (")[0] for c in ev_tabla.columns]
    mostrar(ev_tabla, porcentajes=list(ev_tabla.columns))
    cols = st.columns(4)
    for i, (c, nombre) in enumerate(CONCEPTOS_PROYECCION.items()):
        opciones = list(modelos.METODOS)
        config["metodos"][c] = cols[i % 4].selectbox(
            nombre, opciones, index=opciones.index(config["metodos"].get(c, "interanual_acum")),
            format_func=lambda m: modelos.METODOS[m].split(" (")[0], key=f"met_{c}")
    if hay_trafico:
        config["usar_trafico"] = st.toggle("Usar pasajeros y operaciones para DE y tasas", config.get("usar_trafico", True))
        opciones = [m for m in modelos.METODOS if m != "manual"]
        actual = config.get("metodo_trafico", "interanual_acum")
        config["metodo_trafico"] = st.selectbox("Método para proyectar PAX y operaciones", opciones,
                                                index=opciones.index(actual) if actual in opciones else 0,
                                                format_func=modelos.METODOS.get)
    config["ventana_calibracion"] = st.slider("Meses para calibrar el ingreso unitario", 1, 12,
                                              int(config.get("ventana_calibracion", 3)))

with st.expander("2 · Crecimientos (año siguiente y método manual)", expanded=False):
    st.write(f"Por defecto, {anio + 1} repite el crecimiento interanual observado. Puedes fijar un crecimiento "
             f"distinto (por ejemplo, la expectativa de la industria: IATA, ACI, OACI, ALTA). En los conceptos con "
             "método *manual* se usa el crecimiento de cada año.")
    filas = []
    for c, nombre in CONCEPTOS_PROYECCION.items():
        p = config["parametros"].get(c, {})
        g = p.get("g_por_anio", {})
        filas.append({"Concepto": nombre, "clave": c,
                      f"Crecimiento {anio + 1} (%)": None if p.get("g_siguiente") is None else p["g_siguiente"] * 100,
                      f"Manual {anio} (%)": None if g.get(str(anio)) is None else g[str(anio)] * 100,
                      f"Manual {anio + 1} (%)": None if g.get(str(anio + 1)) is None else g[str(anio + 1)] * 100})
    ed = st.data_editor(pd.DataFrame(filas), hide_index=True, width="stretch", disabled=["Concepto", "clave"],
                        column_config={"clave": None}, key="ed_crec")
    for r in ed.to_dict("records"):
        p = {}
        if pd.notna(r[f"Crecimiento {anio + 1} (%)"]):
            p["g_siguiente"] = r[f"Crecimiento {anio + 1} (%)"] / 100
        g = {str(a): r[f"Manual {a} (%)"] / 100 for a in (anio, anio + 1) if pd.notna(r[f"Manual {a} (%)"])}
        if g:
            p["g_por_anio"] = g
        config["parametros"][r["clave"]] = p
    if hay_trafico:
        g_traf = config.get("parametros_trafico", {})
        c1, c2 = st.columns(2)
        for col, s in ((c1, "PAX"), (c2, "OP")):
            v = g_traf.get(f"{s}_NAC", {}).get("g_siguiente")
            nuevo = col.number_input(f"Crecimiento {anio + 1} de {'pasajeros' if s == 'PAX' else 'operaciones'} (%) — vacío = observado",
                                     value=None if v is None else v * 100, format="%.1f", key=f"gt_{s}")
            for t in ("NAC", "INT"):
                g_traf[f"{s}_{t}"] = {} if nuevo is None else {"g_siguiente": nuevo / 100}
        config["parametros_trafico"] = g_traf

with st.expander("3 · Escenario y sensibilidades", expanded=False):
    esc = config["escenario"]
    c1, c2, c3 = st.columns(3)
    esc["pax"] = c1.slider("Pasajeros (% sobre la proyección)", -30, 30, int(round((esc.get("pax") or 0) * 100))) / 100
    esc["op"] = c2.slider("Operaciones (% sobre la proyección)", -30, 30, int(round((esc.get("op") or 0) * 100))) / 100
    esc["dolar"] = c3.slider("Dólar (% sobre el supuesto)", -30, 30, int(round((esc.get("dolar") or 0) * 100))) / 100
    c1, c2 = st.columns(2)
    esc["tarifa_de_nac"] = c1.slider("Cambio de tarifa D° embarque nacional (%) — ej. rebaja", -50, 50,
                                     int(round((esc.get("tarifa_de_nac") or 0) * 100))) / 100
    meses_fut = [f"{a:04d}-{m:02d}" for a in (anio, anio + 1) for m in range(1, 13) if (a, m) > (anio, mes)]
    actual = esc.get("tarifa_desde") or meses_fut[0]
    esc["tarifa_desde"] = c2.selectbox("Desde", meses_fut, index=meses_fut.index(actual) if actual in meses_fut else 0)
    st.caption("Para escenarios optimista/pesimista, ajusta los porcentajes y guarda cada uno con un nombre distinto.")

with st.expander(f"4 · Ajustes manuales ({len(config.get('ajustes', []))})", expanded=False):
    st.write("Reemplaza el valor proyectado de una unidad, concepto y mes (por ejemplo, un ingreso extraordinario "
             "conocido). El comentario es obligatorio y queda en la proyección guardada.")
    opciones_u = sorted(int(u) for u in ing["UNIDAD_GRUPO"].unique())
    aj = pd.DataFrame(config.get("ajustes", []), columns=["unidad", "concepto", "periodo", "valor", "comentario"])
    aj_ed = st.data_editor(aj, num_rows="dynamic", hide_index=True, width="stretch", key="ed_ajustes", column_config={
        "unidad": st.column_config.SelectboxColumn("Unidad", options=opciones_u, required=True),
        "concepto": st.column_config.SelectboxColumn("Concepto", options=list(CONCEPTOS_PROYECCION), required=True),
        "periodo": st.column_config.SelectboxColumn("Mes", options=meses_fut, required=True),
        "valor": st.column_config.NumberColumn("Valor ($)", required=True, format="%.0f"),
        "comentario": st.column_config.TextColumn("Comentario", required=True),
    })
    config["ajustes"] = [r for r in aj_ed.to_dict("records") if all(pd.notna(r[k]) and r[k] != "" for k in aj_ed.columns)]

c1, c2 = st.columns([1, 3])
if c1.button("Calcular proyección", type="primary", icon=":material/calculate:"):
    guardar_config(config)
with st.spinner("Proyectando…"):
    try:
        res = calcular(e, config)
    except ValueError as err:
        st.error(str(err))
        st.stop()
if config != cargar_config():
    c2.info("Hay cambios de configuración sin guardar: presiona **Calcular proyección** para guardarlos. "
            "Los resultados de abajo ya los incluyen.")
for a in res.avisos:
    st.warning(a)

# ------------------------------------------------------------------ Resultados
real_prev = ing.loc[ing["ANIO"] == anio - 1, "MONTO"].sum()
total, total_sig = res.total_anual(anio), res.total_anual(anio + 1)
k1, k2, k3, k4 = st.columns(4)
k1.metric(f"Proyección {anio}", f"MM$ {numero(total / 1e6)}",
          delta=porcentaje(total / real_prev - 1) + f" vs {anio - 1}" if real_prev else None)
k2.metric(f"Real acumulado a {MESES_CORTOS[mes - 1].lower()}", f"MM$ {numero(ing.loc[ing['ANIO'] == anio, 'MONTO'].sum() / 1e6)}")
k3.metric(f"Proyección {anio + 1}", f"MM$ {numero(total_sig / 1e6)}", delta=porcentaje(total_sig / total - 1) + f" vs {anio}")
snaps = control.listar_snapshots()
if snaps:
    ant = float(snaps[0]["totales"].get(str(anio), 0) or 0)
    k4.metric(f"vs. «{snaps[0]['nombre']}»", f"MM$ {numero((total - ant) / 1e6)}",
              delta=porcentaje(total / ant - 1) if ant else None)

mensual = res.ingresos[res.ingresos["ANIO"] == anio].groupby(["MES", "ORIGEN"])["MONTO"].sum().unstack(fill_value=0)
previo = ing[ing["ANIO"] == anio - 1].groupby("MES")["MONTO"].sum()
fig = go.Figure()
if not previo.empty:
    fig.add_bar(x=[MESES_CORTOS[m - 1] for m in previo.index], y=previo.values / 1e6, name=f"{anio - 1} real",
                marker_color=COLOR_ANTERIOR, hovertemplate="%{x}: MM$ %{y:,.0f}<extra></extra>")
real_m = mensual.get("Real", pd.Series(dtype=float))
proy_m = mensual.drop(columns=["Real"], errors="ignore").sum(axis=1)
fig.add_bar(x=[MESES_CORTOS[m - 1] for m in real_m.index if real_m[m]], y=[v / 1e6 for v in real_m if v],
            name=f"{anio} real", marker_color=COLOR_ACTUAL, hovertemplate="%{x}: MM$ %{y:,.0f}<extra></extra>")
fig.add_bar(x=[MESES_CORTOS[m - 1] for m in proy_m.index if proy_m[m]], y=[v / 1e6 for v in proy_m if v],
            name=f"{anio} proyectado", marker_color=COLOR_PROYECTADO, hovertemplate="%{x}: MM$ %{y:,.0f}<extra></extra>")
fig.update_layout(title=f"Ingresos mensuales {anio} (MM$)", barmode="group", bargap=0.25, bargroupgap=0.08, height=380,
                  margin=dict(l=10, r=10, t=60, b=10), legend=dict(orientation="h", y=1.13), separators=",.",
                  xaxis=dict(categoryorder="array", categoryarray=MESES_CORTOS))
fig.update_yaxes(gridcolor="rgba(128,128,128,0.2)", tickformat=",.0f")
st.plotly_chart(fig, width="stretch")

t1, t2, t3, t4 = st.tabs(["Resumen anual", f"Mensual {anio}", "Por unidad", "Tráfico"])
with t1:
    r = pr.resumen_anual(res)
    if real_prev:
        prev_c = ing[ing["ANIO"] == anio - 1].groupby("CONCEPTO_PROY")["MONTO"].sum()
        prev_c = prev_c.reindex(list(CONCEPTOS_PROYECCION)).fillna(0)
        prev_c.index = [CONCEPTOS_PROYECCION[c] for c in prev_c.index]
        prev_c.loc["Total"] = prev_c.sum()
        r.insert(0, f"{anio - 1} real", prev_c)
    r.columns = [str(c) for c in r.columns]
    r[f"Var. {anio}/{anio - 1}"] = r[str(anio)] / r[f"{anio - 1} real"].where(r[f"{anio - 1} real"] != 0) - 1 if real_prev else None
    r[f"Var. {anio + 1}/{anio}"] = r[str(anio + 1)] / r[str(anio)].where(r[str(anio)] != 0) - 1
    mostrar(r, 1, millones=True, porcentajes=[c for c in r.columns if c.startswith("Var.")])
    st.caption("Millones de pesos.")
with t2:
    m = pr.resumen_mensual(res, anio)
    origen = pr.origen_por_mes(res, anio)
    m.columns = [f"{MESES_CORTOS[c - 1]}{' (P)' if origen.get(c) != 'Real' else ''}" for c in m.columns]
    m["Total"] = m.sum(axis=1)
    mostrar(m, 1, millones=True)
    st.caption("(P) = mes proyectado. Millones de pesos.")
with t3:
    anio_u = st.radio("Año", [anio, anio + 1], horizontal=True, key="anio_unidad")
    d = res.ingresos[res.ingresos["ANIO"] == anio_u]
    tu = d.pivot_table(index="UNIDAD", columns="CONCEPTO_PROY", values="MONTO", aggfunc="sum", fill_value=0)
    tu = tu.reindex(columns=[c for c in CONCEPTOS_PROYECCION if c in tu.columns])
    tu.columns = [CONCEPTOS_PROYECCION[c] for c in tu.columns]
    tu["Total"] = tu.sum(axis=1)
    tu = tu.sort_values("Total", ascending=False)
    tu.insert(0, "Unidad", [nombres.get(int(u), str(u)) for u in tu.index])
    mostrar(tu, 1, millones=True, altura=480)
    unidad = st.selectbox("Detalle mensual de la unidad", list(tu.index), format_func=lambda u: f"{u} {nombres.get(int(u), '')}")
    du = res.ingresos[(res.ingresos["UNIDAD"] == unidad) & (res.ingresos["ANIO"] >= anio)]
    det = du.pivot_table(index="CONCEPTO_PROY", columns=["ANIO", "MES"], values="MONTO", aggfunc="sum", fill_value=0)
    det.columns = [f"{MESES_CORTOS[m_ - 1]}-{str(a)[2:]}" for a, m_ in det.columns]
    det.index = [CONCEPTOS_PROYECCION.get(c, c) for c in det.index]
    mostrar(det, 0)
    metodos = du[du["ORIGEN"] != "Real"].groupby("CONCEPTO_PROY")["METODO"].first()
    st.caption("Método por concepto: " + " · ".join(f"{CONCEPTOS_PROYECCION.get(c, c)}: {modelos.METODOS.get(mm_, mm_)}"
                                                    for c, mm_ in metodos.items()))
with t4:
    if res.trafico.empty:
        st.info("Sin datos de pasajeros u operaciones.")
    else:
        mostrar(pr.trafico_anual(res), 0)

st.divider()
st.subheader("Guardar esta proyección")
st.write("Guarda la proyección para compararla el próximo mes (actividad 8: revisar estado de la proyección anterior).")
c1, c2, c3 = st.columns([2, 3, 1], vertical_alignment="bottom")
nombre = c1.text_input("Nombre", f"Proyección {MESES[mes % 12] if mes < 12 else MESES[0]} {anio if mes < 12 else anio + 1}")
comentario = c2.text_input("Comentario (supuestos principales)")
if c3.button("Guardar", type="primary", icon=":material/bookmark_add:"):
    guardar_config(config)
    sid = control.guardar_snapshot(res, nombre, comentario)
    st.success(f"Proyección guardada como «{nombre}».")
