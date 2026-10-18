"""Página compartida de carga de pasajeros (COPAE) y operaciones (SAC)."""
from __future__ import annotations

import pandas as pd
import streamlit as st

from core import historico, trafico
from core.esquema import MESES_CORTOS
from ui.comun import aviso_privacidad, estado, mostrar, nombres_unidades, requiere_maestros


def pagina(es_operaciones: bool):
    aviso_privacidad()
    nombre = "Operaciones" if es_operaciones else "Pasajeros embarcados (PAX)"
    st.title(nombre)
    if es_operaciones:
        st.write("Sube el listado de **operaciones de aterrizaje/despegue** del SAC (*Operaciones Aeronáuticas → "
                 "Informes → Operaciones*). Se aplican los filtros del instructivo: solo aterrizajes; sin aeronaves de "
                 "Estado ni clubes aéreos; sin PMD ≤ 5,7 t; solo aeródromos de 1ª, 2ª o 3ª categoría.")
    else:
        st.write("Sube el reporte **pasajeros por tasa** de COPAE (con ajuste, horario UTC) o la plantilla con columnas "
                 "Año, Mes, Aeródromo, Tipo (nacional/internacional) y Pasajeros.")
    e = estado()
    if not requiere_maestros(e):
        st.stop()
    campos = trafico.CAMPOS_OP if es_operaciones else trafico.CAMPOS_PAX
    datos_hist = e["ops"] if es_operaciones else e["pax"]

    tab_carga, tab_base = st.tabs(["Cargar archivo", "Base histórica"])
    with tab_carga:
        _cargar(e, es_operaciones, campos)

    with tab_base:
        if datos_hist.empty:
            st.info("Sin datos guardados.")
        else:
            anios = sorted(datos_hist["ANIO"].unique())
            anio = st.selectbox("Año", anios, index=len(anios) - 1, key=f"anio_hist_{es_operaciones}")
            tipo = st.radio("Tipo", ["Total", "Nacional", "Internacional"], horizontal=True, key=f"tipo_{es_operaciones}")
            d = datos_hist if tipo == "Total" else datos_hist[datos_hist["TIPO"] == tipo]
            nombres = nombres_unidades(e)
            mostrar(_pivote(d[d["ANIO"] == anio], nombres), altura=460)
            previo = d[d["ANIO"] == anio - 1]
            if not previo.empty:
                actual = d[d["ANIO"] == anio]
                meses = sorted(actual["MES"].unique())
                comp = pd.DataFrame({
                    f"{anio}": actual.groupby("UNIDAD")["VALOR"].sum(),
                    f"{anio - 1} (mismos meses)": previo[previo["MES"].isin(meses)].groupby("UNIDAD")["VALOR"].sum(),
                }).fillna(0)
                comp["Variación"] = comp.iloc[:, 0] / comp.iloc[:, 1].where(comp.iloc[:, 1] > 0) - 1
                comp.index = [nombres.get(int(u), str(u)) for u in comp.index]
                st.subheader(f"Variación {anio} vs {anio - 1} (acumulado a igual mes)")
                mostrar(comp.sort_values(comp.columns[0], ascending=False), porcentajes=["Variación"])


def _cargar(e, es_operaciones: bool, campos: dict):
    if es_operaciones:
        with st.expander("Filtros de operaciones"):
            f = trafico.cargar_filtros_op()
            f["solo_aterrizajes"] = st.checkbox("Considerar solo aterrizajes", f["solo_aterrizajes"])
            f["texto_aterrizaje"] = st.text_input("Texto que identifica un aterrizaje", f["texto_aterrizaje"])
            f["pmd_maximo_excluido"] = st.number_input("Excluir PMD menor o igual a (t)", value=float(f["pmd_maximo_excluido"]))
            textos = st.text_area("Excluir operadores / tipos que contengan (uno por línea)",
                                  "\n".join(f["excluir_textos"]), height=150)
            f["excluir_textos"] = [t.strip() for t in textos.splitlines() if t.strip()]
            f["categorias_validas"] = st.multiselect("Categorías de aeródromo válidas", [1, 2, 3, 4], f["categorias_validas"])
            if st.button("Guardar filtros", icon=":material/save:"):
                trafico.guardar_filtros_op(f)
                st.success("Filtros guardados.")
    archivo = st.file_uploader("Archivo", type=["xlsx", "xls", "csv", "txt"], key=f"traf_{es_operaciones}")
    if not archivo:
        return
    hojas = trafico.leer_tabla(archivo, archivo.name)
    if not hojas:
        st.error("El archivo no tiene datos.")
        return
    hoja = st.selectbox("Hoja", list(hojas)) if len(hojas) > 1 else next(iter(hojas))
    df = hojas[hoja]
    st.caption(f"{len(df):,} filas · vista previa:".replace(",", "."))
    st.dataframe(df.head(8), width="stretch")

    st.subheader("Asignar columnas")
    sugerido = trafico.sugerir_mapeo(df.columns, campos)
    opciones = [""] + list(df.columns)
    mapeo = {}
    cols = st.columns(3)
    for i, (campo, etiqueta) in enumerate(campos.items()):
        valor = sugerido.get(campo, "")
        mapeo[campo] = cols[i % 3].selectbox(etiqueta, opciones, index=opciones.index(valor) if valor in opciones else 0,
                                             key=f"map_{es_operaciones}_{campo}")
    try:
        res = trafico.procesar(df, mapeo, e["maestros"].unidades, es_operaciones)
    except ValueError as err:
        st.warning(str(err))
        return
    for a in res.advertencias:
        st.caption(f"⚠️ {a}")
    if res.excluidas:
        st.write("**Filas excluidas por filtros:** " + " · ".join(f"{k}: {v:,}".replace(",", ".") for k, v in res.excluidas.items()))
    if not res.no_reconocidas.empty:
        with st.expander(f"⚠️ {len(res.no_reconocidas)} valores de aeródromo no reconocidos (se omiten)"):
            st.dataframe(res.no_reconocidas, hide_index=True)
            st.caption("Agrega el código o corrige el nombre en Maestros → Unidades.")
    nombres = nombres_unidades(e)
    resumen = _pivote(res.datos, nombres)
    st.subheader("Resultado")
    mostrar(resumen, altura=420)
    if st.button("Guardar en la base histórica", type="primary", icon=":material/save:"):
        trafico.guardar_mapeo(df.columns, mapeo)
        (historico.guardar_operaciones if es_operaciones else historico.guardar_pax)(res.datos)
        st.success("Guardado. El mapeo de columnas queda recordado para el próximo mes.")



def _pivote(d: pd.DataFrame, nombres: dict[int, str]) -> pd.DataFrame:
    if d.empty:
        return d
    t = d.pivot_table(index="UNIDAD", columns=["ANIO", "MES"], values="VALOR", aggfunc="sum", fill_value=0)
    multi_anio = t.columns.get_level_values(0).nunique() > 1
    t.columns = [f"{MESES_CORTOS[m - 1]}{'-' + str(a)[2:] if multi_anio else ''}" for a, m in t.columns]
    t["Total"] = t.sum(axis=1)
    t = t.sort_values("Total", ascending=False)
    t.insert(0, "Unidad", [nombres.get(int(u), str(u)) for u in t.index])
    t.loc["Total"] = ["Total"] + list(t.iloc[:, 1:].sum())
    return t
