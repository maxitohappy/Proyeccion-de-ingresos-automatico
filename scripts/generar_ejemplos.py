"""Genera datos de ejemplo 100 % ficticios en ejemplos/ (unidades, clientes, RUT y montos inventados).

Sirven para probar la app desde el link público y para los tests, sin usar datos reales.
Uso: python scripts/generar_ejemplos.py
"""
from __future__ import annotations

import math
import random
from datetime import date
from pathlib import Path

import pandas as pd

RAIZ = Path(__file__).resolve().parent.parent
SALIDA = RAIZ / "ejemplos"
random.seed(20260101)

UNIDADES = [
    # código, nombre, categoría, región, pax nac base mensual, pax int base mensual, asociar_a
    (9101, "Ap. Ejemplo Norte", 1, 1, 60000, 1500, None),
    (9201, "Ap. Ejemplo Central", 1, 13, 900000, 520000, None),
    (9301, "Ad. Ejemplo Sur", 2, 10, 45000, 0, None),
    (9302, "Ad. Ejemplo Lago", 3, 10, 0, 0, 9301),
    (9401, "Ad. Ejemplo Austral", 2, 12, 30000, 900, None),
    (9110, "Subdepto. Ejemplo Administración", None, None, 0, 0, None),
    (5220, "Concesionario Ejemplo", None, None, 0, 0, 9201),
]
CLIENTES = [(99000001, "AEROLINEA FICTICIA UNO SPA"), (99000002, "AEROLINEA FICTICIA DOS SA"),
            (99000003, "TRANSPORTES AEREOS DEMO LTDA"), (99000004, "SERVICIOS AERONAUTICOS PRUEBA SPA"),
            (99000005, "COMERCIAL EJEMPLO LIMITADA")]
# cuenta, cta. presupuestaria, producto, subproducto, denominación, categoría, tipo, detalle(s)
PLAN = [
    (91000000000001, 11500000000001, "Servicios Aeroportuarios", "Derecho Embarque", "Derecho Embarque V.Nacionales", "Derecho Embarque", "Nacional",
     ["1C.NAC.DERECHOS EMBARQUE", "2C.NAC.DERECHOS DE EMBARQUE", "DISTA MENOR 270 KM. NAC"]),
    (91000000000002, 11500000000002, "Servicios Aeroportuarios", "Derecho Embarque", "Derecho Embarque V.Internacionales", "Derecho Embarque", "Internacional",
     ["DER. EMBARQUE V. INTERNAC.", "INT. DERECHO DE EMBARQUE MENOR QUE 500 KM"]),
    (91000000000003, 11500000000003, "Servicios Aeroportuarios", "Tasas", "Aterrizajes Vuelos Nacionales", "Tasas", "Nacional", ["ATERRIZAJE NACIONAL"]),
    (91000000000004, 11500000000004, "Servicios Aeroportuarios", "Tasas", "Aterrizajes Vuelos Internacionales", "Tasas", "Internacional", ["ATERRIZAJE INTERNACIONAL"]),
    (91000000000005, 11500000000005, "Servicios Aeroportuarios", "Tasas", "Tasas Iluminación V.Nacionales", "Tasas", "Nacional", ["ILUMINACION NACIONAL"]),
    (91000000000006, 11500000000006, "Servicios Aeroportuarios", "Tasas", "Serv.en Ruta Internacional", "Tasas", "Internacional", ["SERV.EN RUTA V.INTERNACIONAL"]),
    (91000000000007, 11500000000007, "Rentas de la Propiedad", "Combustible", "Porcentaje Vtas.Combustibles", "Combustible", "Nacional", ["PORCENTAJE VENTA COMBUSTIBLE"]),
    (91000000000008, 11500000000008, "Rentas de la Propiedad", "Concesiones No Aeronáuticas", "Locales Comerciales", "Concesiones", "Nacional", ["LOCALES COMERCIALES"]),
    (91000000000009, 11500000000009, "Otros Ingresos", "Otros Ingresos", "Intereses", "Otros Ingresos", "Nacional", ["INTERES EXENTO"]),
    (91000000000010, 11500000000010, "Servicios Aeroportuarios", "Habilitación y Licencias", "Licencias Tripulaciones", "Habilitación y Licencias", "Nacional", ["LICENCIA TRIPULANTE"]),
]
TARIFA_1C, TARIFA_2C, TARIFA_270, TARIFA_INT_USD = 7100, 5000, 2600, 25
ESTACIONALIDAD = [1.18, 1.12, 0.98, 0.88, 0.82, 0.86, 1.02, 0.95, 0.93, 0.98, 1.05, 1.17]
MESES_2026 = 9


def dolar(anio, mes):
    return 940 + 25 * math.sin((anio * 12 + mes) / 4)


def pax(base, anio, mes):
    crecimiento = 1.0 if anio == 2025 else 1.06
    return round(base * ESTACIONALIDAD[mes - 1] * crecimiento * random.uniform(0.97, 1.03))


def periodos():
    for anio, meses in ((2025, 12), (2026, MESES_2026)):
        for mes in range(1, meses + 1):
            yield anio, mes


def generar():
    SALIDA.mkdir(exist_ok=True)
    filas_sac, filas_pax, filas_op = [], [], []
    numero = 100000
    for anio, mes in periodos():
        emision = date(anio, mes, 15)
        for codigo, nombre, cat, _, base_nac, base_int, _a in UNIDADES:
            pn, pi = pax(base_nac, anio, mes), pax(base_int, anio, mes)
            on, oi = round(pn / 75) + (40 if codigo == 9302 else 0), round(pi / 160)
            if codigo not in (9110, 5220):
                filas_pax += [(anio, mes, nombre, "NACIONAL", pn), (anio, mes, nombre, "INTERNACIONAL", pi)]
                for tipo, ops in (("NACIONAL", on), ("INTERNACIONAL", oi)):
                    for _ in range(ops // 50):
                        filas_op.append((date(anio, mes, random.randint(1, 28)).isoformat(), str(codigo), tipo, "ATERRIZAJE",
                                         random.choice(CLIENTES)[1], round(random.uniform(6, 80), 1), 50))
                    filas_op.append((date(anio, mes, 3).isoformat(), str(codigo), tipo, "DESPEGUE", CLIENTES[0][1], 40.0, ops))
                filas_op.append((date(anio, mes, 5).isoformat(), str(codigo), "NACIONAL", "ATERRIZAJE", "CLUB AEREO FICTICIO", 1.2, 12))
            montos = {}
            if pn:
                tarifa = TARIFA_1C if cat == 1 else TARIFA_2C
                montos[("1C.NAC.DERECHOS EMBARQUE" if cat == 1 else "2C.NAC.DERECHOS DE EMBARQUE")] = pn * 0.93 * tarifa
                montos["DISTA MENOR 270 KM. NAC"] = pn * 0.02 * TARIFA_270
            if pi:
                montos["DER. EMBARQUE V. INTERNAC."] = pi * 0.97 * TARIFA_INT_USD * dolar(anio, mes)
                montos["INT. DERECHO DE EMBARQUE MENOR QUE 500 KM"] = pi * 0.03 * TARIFA_1C
            if on:
                montos["ATERRIZAJE NACIONAL"] = on * 95000
                montos["ILUMINACION NACIONAL"] = on * 21000
            if oi:
                montos["ATERRIZAJE INTERNACIONAL"] = oi * 310 * dolar(anio, mes)
                montos["SERV.EN RUTA V.INTERNACIONAL"] = oi * 180 * dolar(anio, mes)
            if base_nac:
                montos["PORCENTAJE VENTA COMBUSTIBLE"] = base_nac * 120 * random.uniform(0.9, 1.1)
                montos["LOCALES COMERCIALES"] = base_nac * 95 * (1.04 if anio == 2026 else 1)
            if codigo == 9110:
                montos["INTERES EXENTO"] = random.uniform(3e6, 9e6)
                montos["LICENCIA TRIPULANTE"] = random.uniform(2e7, 4e7)
            if codigo == 5220:
                montos["LOCALES COMERCIALES"] = 1.5e9
            if codigo == 9302:
                montos["ATERRIZAJE NACIONAL"] = 40 * 60000
            for detalle, total in montos.items():
                cuenta = next(p for p in PLAN if detalle in p[7])
                partes = random.randint(1, 4)
                for i in range(partes):
                    rut, cliente = random.choice(CLIENTES)
                    numero += 1
                    filas_sac.append({
                        "UNIDAD_PRESTACION_SERVICIO_": codigo, "DESC_UNID_PRESTACION_SERVICIO_": nombre.upper(),
                        "UNIDAD_FACTURACION_": codigo, "DESCRIPCION_UNIDAD_FACTURACION": nombre.upper(),
                        "FECHA_EMISION_": emision, "FECHA_VENCIMIENTO_": emision, "FECHA_PAGO_": None,
                        "DOCUMENTO_": "FE", "TIPO_": "OP", "NUMERO_": numero, "PERIODO_": date(anio, mes, 1),
                        "RUT_": rut, "CLIENTE_": cliente, "ESTADO_": "EM", "MONEDA_": "P", "TASA_": 0,
                        "DETALLE_": detalle, "MONTO_": round(total / partes), "CUENTA_GESTION_": cuenta[0],
                        "CUENTA_PRESUPUESTARIA_": cuenta[1], "MES_": mes, "TIPO_DE_CAMBIO_": None,
                    })
    sac = pd.DataFrame(filas_sac)
    sac["FECHA_EMISION_"] = pd.to_datetime(sac["FECHA_EMISION_"])
    sac["FECHA_VENCIMIENTO_"] = pd.to_datetime(sac["FECHA_VENCIMIENTO_"])
    sac["PERIODO_"] = pd.to_datetime(sac["PERIODO_"])
    anio = sac["FECHA_EMISION_"].dt.year
    sac[anio == 2025].to_csv(SALIDA / "informe_sac_2025_ejemplo.csv", index=False, sep=";", date_format="%d-%m-%Y")
    with pd.ExcelWriter(SALIDA / "informe_gestion_2026_ejemplo.xlsx", engine="xlsxwriter") as xw:
        sac[anio == 2026].to_excel(xw, sheet_name="2026", index=False)
        _maestros_excel(xw)
    pd.DataFrame(filas_pax, columns=["Año", "Mes", "Aeródromo", "Tipo Vuelo", "Pasajeros"]).to_csv(
        SALIDA / "pasajeros_copae_ejemplo.csv", index=False, sep=";")
    pd.DataFrame(filas_op, columns=["Fecha", "Aeródromo", "Tipo Vuelo", "Tipo Operación", "Operador", "PMD", "Cantidad"]).to_csv(
        SALIDA / "operaciones_sac_ejemplo.csv", index=False, sep=";")
    totales = [{"ANIO": a, "MES": m, "CONCEPTO_PROY": "", "MONTO": round(2.1e10 * ESTACIONALIDAD[m - 1] * f)}
               for a, f in ((2019, 1.0), (2022, 0.8), (2023, 0.9), (2024, 0.97)) for m in range(1, 13)]
    pd.DataFrame(totales).to_csv(SALIDA / "totales_anteriores_ejemplo.csv", index=False, sep=";")
    print(f"Ejemplos generados en {SALIDA}: {len(sac)} líneas SAC, {len(filas_pax)} filas PAX, {len(filas_op)} filas OP")


def _maestros_excel(xw):
    plan = pd.DataFrame([(70000 + i, p[0], p[1], p[2], p[3], p[4], "1ª A", p[5], p[6]) for i, p in enumerate(PLAN)],
                        columns=["Codigo de facturacion", "Cuenta de Gestion", "Cuenta Presupuestaria", "Producto",
                                 "Subproducto", "Denominación", "Categoria ", "Categoria", "Tipo de Ingreso"])
    plan.to_excel(xw, sheet_name="PlanDeCuentas", index=False)
    pd.DataFrame([("Derecho Embarque", "Derecho de Embarque"), ("Tasas", "Tasas"), ("Combustible", "Combustible"),
                  ("Concesiones", "Concesiones"), ("Otros Ingresos", "Otros Ingresos"),
                  ("Habilitación y Licencias", "Otros Ingresos")],
                 columns=["Categoria", "Concepto"]).to_excel(xw, sheet_name="Conceptos", index=False)
    asoc = [(u[0], u[1].upper(), u[2], u[3], "SI" if u[4] else "NO", "SI" if u[2] else "NO", "SI" if not u[6] else "NO",
             u[6] if u[6] else "NO") for u in UNIDADES]
    pd.DataFrame(asoc, columns=["UNIDAD", "NOMBRE", "CATEGORÍA", "REGIÓN", "CONSIDERAR\nEN  PAX", "CONSIDERAR EN\nOPERACIONES",
                                "UNIDAD PROYECCIÓN MENSUAL", "ASOCIAR\nINGRESO"]).to_excel(xw, sheet_name="asociación", index=False)
    nombres_cat = {1: "Primera", 2: "Segunda", 3: "Tercera"}
    matriz = [(u[0], u[1], nombres_cat[u[2]], 1, 1, 1, 0, 1, 1 if u[2] in (1, 2) else 0, 1) for u in UNIDADES if u[2]]
    pd.DataFrame(matriz, columns=["Unidad", "Nombre", "Categoría", "Tasa Aterrizaje", "Tasa Estacionamiento",
                                  "Tasa Iluminación", "Tasa I.L.S.", "Tasa Servicio en Ruta", "Derechos de Embarque",
                                  "Derechos por Combustible"]).to_excel(xw, sheet_name="matriz", index=False)


if __name__ == "__main__":
    generar()
