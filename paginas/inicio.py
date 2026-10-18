import streamlit as st

from core import demo, factores
from ui.comun import EN_NAVEGADOR, aviso_privacidad, estado, texto_periodo

aviso_privacidad()
st.title("Proyección de Ingresos Operacionales")
st.write(
    "Automatiza el proceso mensual de proyección de ingresos: depuración del informe de gestión del SAC, "
    "factores económicos, pasajeros y operaciones, modelos de proyección, control frente a la proyección "
    "anterior, simulaciones por unidad y generación del cuadro resumen y la presentación."
)
if EN_NAVEGADOR:
    st.info("🔒 Esta aplicación se ejecuta completamente en tu navegador. Los archivos que subas **no se envían "
            "a ningún servidor**; los datos quedan guardados en este navegador.", icon=":material/lock:")

e = estado()
web = factores.cargar_web()

st.subheader("Estado del proceso del mes")
pasos = [
    ("Maestros (plan de cuentas y unidades)", e["maestros_ok"],
     f"{len(e['maestros'].unidades)} unidades · {e['maestros'].plan['cuenta_gestion'].nunique() if e['maestros_ok'] else 0} cuentas",
     "paginas/maestros.py"),
    ("Informe de gestión (ingresos reales)", not e["ingresos"].empty,
     f"Último mes cerrado: {texto_periodo(e['ultimo_ingreso'])} · años: {', '.join(map(str, e['anios_ingresos'])) or '—'}",
     "paginas/carga_informe.py"),
    ("Factores económicos", bool(web.get("registros")),
     f"Actualizados automáticamente: {(web.get('actualizado') or '—')[:10]}", "paginas/factores.py"),
    ("Pasajeros (COPAE)", not e["pax"].empty, f"Hasta: {texto_periodo(e['ultimo_pax'])}", "paginas/pasajeros.py"),
    ("Operaciones (SAC)", not e["ops"].empty, f"Hasta: {texto_periodo(e['ultimo_ops'])}", "paginas/operaciones.py"),
]
for nombre, ok, detalle, pagina in pasos:
    c1, c2, c3 = st.columns([0.06, 0.5, 0.44], vertical_alignment="center")
    c1.markdown("✅" if ok else "⬜")
    c2.markdown(f"**{nombre}**  \n{detalle}")
    c3.page_link(pagina, label="Abrir", icon=":material/arrow_forward:")

st.caption("Pasajeros y operaciones son opcionales: sin ellos, la proyección se hace directamente sobre las series de "
           "ingresos (en USD para los conceptos internacionales y a tarifa/IPC constante para los nacionales).")

st.subheader("Flujo mensual sugerido")
st.markdown(
    """
1. **Cargar informe de gestión**: sube el export del SAC *Ingresos Operaciones por Concepto* (acumulado del año).
2. **Factores económicos**: revisa el dólar y el IPC descargados automáticamente; define los supuestos y tarifas.
3. **Pasajeros / Operaciones**: sube los reportes de COPAE y del SAC (opcional, mejora la proyección).
4. **Proyección de ingresos**: elige métodos y escenarios, revisa y **guarda la proyección**.
5. **Control vs anterior**: compara con la proyección del mes pasado y explica las diferencias.
6. **Reportes**: descarga el cuadro resumen (Excel) y la presentación (PPT).
"""
)

if demo.disponible():
    with st.expander("¿Primera vez? Probar con datos de ejemplo (ficticios)"):
        st.write("Carga unidades, cuentas, ingresos 2025–2026, pasajeros y operaciones **inventados** para "
                 "recorrer todas las funciones. Puedes borrarlos después en *Maestros y respaldo*.")
        if st.button("Cargar datos de ejemplo", icon=":material/play_arrow:"):
            with st.spinner("Cargando ejemplos…"):
                for p in demo.cargar():
                    st.write("•", p)
            st.success("Datos de ejemplo cargados.")
            st.rerun()
