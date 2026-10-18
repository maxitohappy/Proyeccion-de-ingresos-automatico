"""Simulación de ingresos y pasajeros por unidad a varios años (solicitudes de simulación de
un aeródromo): crecimiento de PAX, reajuste por IPC, tarifas de
derecho de embarque, tipo de cambio y escenarios de pago al concesionario (TPE)."""
from __future__ import annotations

import io
from dataclasses import dataclass, field

import pandas as pd

from .esquema import MESES

CONCEPTOS_SIM = {
    "DE_NAC": "D° Embarque Nacional",
    "DE_INT": "D° Embarque Internacional",
    "CONCESIONES": "Concesiones (ingresos comerciales)",
    "TASAS": "Tasas Aeronáuticas",
    "COMBUSTIBLE": "Combustible",
    "OTROS": "Otros Ingresos",
}
CONCEPTOS_REAJUSTABLES = ["CONCESIONES", "TASAS", "COMBUSTIBLE", "OTROS"]


@dataclass
class SupuestosSimulacion:
    nombre: str
    anio_base: int
    anio_final: int
    pax_nac: dict[int, list]                       # año -> 12 valores (None = se proyecta)
    pax_int: dict[int, list]
    crec_nac: dict[int, float]                     # por año (el del año base completa sus meses faltantes)
    crec_int: dict[int, float]
    ipc: dict[int, float]
    tarifa_nac: float                              # tarifa D° embarque nacional del año base ($)
    tarifa_int_usd: dict[int, float]
    tipo_cambio: dict[int, float]
    ingresos_base: dict[str, float]                # año base: CONCESIONES, TASAS, COMBUSTIBLE, OTROS
    ingresos_historicos: dict[int, dict[str, float]] = field(default_factory=dict)
    tpe: list[float] = field(default_factory=list)  # $ por pasajero en el primer año de concesión
    anio_inicio_tpe: int | None = None
    notas: str = ""

    @property
    def anios_proyeccion(self) -> list[int]:
        return list(range(self.anio_base, self.anio_final + 1))

    @property
    def anios_historicos(self) -> list[int]:
        return sorted(a for a in set(self.pax_nac) | set(self.ingresos_historicos) if a < self.anio_base)


@dataclass
class ResultadoSimulacion:
    pax_nac: pd.DataFrame       # meses × años
    pax_int: pd.DataFrame
    pax_anual: pd.DataFrame     # [Nacional, Internacional, Total] × años
    tarifas: pd.DataFrame       # [tarifa nac, tarifa int USD, TC] × años
    ingresos: pd.DataFrame      # conceptos + Total × años
    pagos: pd.DataFrame         # escenarios × años
    tpe: pd.DataFrame


def _mensual(datos: dict[int, list], crec: dict[int, float], historicos: list[int], proy: list[int]) -> pd.DataFrame:
    df = pd.DataFrame(index=range(1, 13))
    for a in historicos:
        df[a] = [(v if v is not None else 0.0) for v in (datos.get(a) or [0.0] * 12)]
    for a in proy:
        reales = datos.get(a) or [None] * 12
        previo = df[a - 1] if (a - 1) in df.columns else pd.Series(0.0, index=df.index)
        g = float(crec.get(a, 0.0))
        df[a] = [reales[m - 1] if reales[m - 1] is not None and not pd.isna(reales[m - 1])
                 else previo[m] * (1 + g) for m in range(1, 13)]
    df.index = MESES
    return df.astype(float)


def calcular(s: SupuestosSimulacion) -> ResultadoSimulacion:
    hist, proy = s.anios_historicos, s.anios_proyeccion
    pax_nac = _mensual(s.pax_nac, s.crec_nac, hist, proy)
    pax_int = _mensual(s.pax_int, s.crec_int, hist, proy)
    anual = pd.DataFrame({"Nacional": pax_nac.sum(), "Internacional": pax_int.sum()}).T
    anual.loc["Total"] = anual.sum()

    tarifa_nac, tpe = {}, {}
    for a in proy:
        tarifa_nac[a] = s.tarifa_nac if a == s.anio_base else tarifa_nac[a - 1] * (1 + s.ipc.get(a, 0.0))
    tarifas = pd.DataFrame({
        a: {"Tarifa D° embarque nacional ($)": tarifa_nac[a],
            "Tarifa D° embarque internacional (USD)": s.tarifa_int_usd.get(a, 0.0),
            "Tipo de cambio ($/USD)": s.tipo_cambio.get(a, 0.0),
            "IPC (reajuste)": s.ipc.get(a, 0.0)}
        for a in proy
    })

    ingresos = pd.DataFrame(index=list(CONCEPTOS_SIM), columns=hist + proy, dtype=float)
    for a in hist:
        for c in CONCEPTOS_SIM:
            ingresos.loc[c, a] = float(s.ingresos_historicos.get(a, {}).get(c, 0.0))
    for a in proy:
        ingresos.loc["DE_NAC", a] = anual.loc["Nacional", a] * tarifa_nac[a]
        ingresos.loc["DE_INT", a] = anual.loc["Internacional", a] * s.tarifa_int_usd.get(a, 0.0) * s.tipo_cambio.get(a, 0.0)
        for c in CONCEPTOS_REAJUSTABLES:
            ingresos.loc[c, a] = (float(s.ingresos_base.get(c, 0.0)) if a == s.anio_base
                                  else ingresos.loc[c, a - 1] * (1 + s.ipc.get(a, 0.0)))
    ingresos.index = [CONCEPTOS_SIM[c] for c in ingresos.index]
    ingresos.loc["Total"] = ingresos.sum()

    inicio = s.anio_inicio_tpe or (s.anio_base + 1)
    filas_tpe, filas_pago = {}, {}
    for i, valor in enumerate(s.tpe, start=1):
        t = {}
        for a in proy:
            if a < inicio:
                continue
            t[a] = float(valor) if a == inicio else t[a - 1] * (1 + s.ipc.get(a, 0.0))
        filas_tpe[f"Escenario TPE {i}"] = t
        filas_pago[f"Pago al concesionario escenario {i}"] = {a: t[a] * anual.loc["Total", a] for a in t}
    return ResultadoSimulacion(
        pax_nac=pax_nac, pax_int=pax_int, pax_anual=anual, tarifas=tarifas, ingresos=ingresos,
        pagos=pd.DataFrame(filas_pago).T, tpe=pd.DataFrame(filas_tpe).T,
    )


def exportar_excel(s: SupuestosSimulacion) -> bytes:
    """Libro con la misma lógica que la simulación, con fórmulas vivas para que el
    destinatario pueda cambiar supuestos (crecimientos, IPC, tarifas, TC, TPE)."""
    import xlsxwriter
    from xlsxwriter.utility import xl_rowcol_to_cell as celda

    hist, proy = s.anios_historicos, s.anios_proyeccion
    anios = hist + proy
    buf = io.BytesIO()
    wb = xlsxwriter.Workbook(buf, {"in_memory": True})
    ws = wb.add_worksheet("Simulación")
    f_tit = wb.add_format({"bold": True, "font_size": 14, "font_color": "#1F3864"})
    f_sub = wb.add_format({"italic": True, "font_color": "#555555"})
    f_enc = wb.add_format({"bold": True, "bg_color": "#8EA9DB", "border": 1, "align": "center"})
    f_lab = wb.add_format({"bold": True, "bg_color": "#D9E1F2", "border": 1})
    f_pct = wb.add_format({"num_format": "0.0%", "bg_color": "#FFF2CC", "border": 1})
    f_inp = wb.add_format({"num_format": "#,##0", "bg_color": "#FFF2CC", "border": 1})
    f_num = wb.add_format({"num_format": "#,##0", "border": 1})
    f_tot = wb.add_format({"num_format": "#,##0", "bold": True, "border": 1, "bg_color": "#E2EFDA"})
    f_nota = wb.add_format({"font_color": "#7F7F7F", "italic": True})
    ws.set_column(0, 0, 3)
    ws.set_column(1, 1, 42)
    ws.set_column(2, 2 + len(anios), 15)

    ws.write(0, 1, s.nombre, f_tit)
    ws.write(1, 1, "(Simulación de pasajeros embarcados e ingresos; celdas amarillas = supuestos editables)", f_sub)
    col = {a: 2 + i for i, a in enumerate(anios)}

    # --- Supuestos ---
    r = 3
    ws.write(r, 1, "Supuestos", f_enc)
    for a in proy:
        ws.write(r, col[a], a, f_enc)
    fila = {}
    for etiqueta, clave_, valores, fmt in (
        ("Crecimiento % tráfico nacional", "cn", s.crec_nac, f_pct),
        ("Crecimiento % tráfico internacional", "ci", s.crec_int, f_pct),
        ("Reajuste de tarifas (IPC)", "ipc", s.ipc, f_pct),
        ("Tarifa D° embarque internacional (USD)", "usd", s.tarifa_int_usd, f_inp),
        ("Tipo de cambio ($/USD)", "tc", s.tipo_cambio, f_inp),
    ):
        r += 1
        fila[clave_] = r
        ws.write(r, 1, etiqueta, f_lab)
        for a in proy:
            ws.write_number(r, col[a], float(valores.get(a, 0.0)), fmt)
    r += 1
    fila["tn"] = r
    ws.write(r, 1, "Tarifa D° embarque nacional ($)", f_lab)
    for a in proy:
        if a == s.anio_base:
            ws.write_number(r, col[a], float(s.tarifa_nac), f_inp)
        else:
            ws.write_formula(r, col[a], f"={celda(r, col[a - 1])}*(1+{celda(fila['ipc'], col[a])})", f_num)
    inicio = s.anio_inicio_tpe or (s.anio_base + 1)
    filas_tpe = []
    for i, valor in enumerate(s.tpe, start=1):
        r += 1
        filas_tpe.append(r)
        ws.write(r, 1, f"Escenario TPE {i} ($ por pasajero)", f_lab)
        for a in proy:
            if a < inicio:
                continue
            if a == inicio:
                ws.write_number(r, col[a], float(valor), f_inp)
            else:
                ws.write_formula(r, col[a], f"={celda(r, col[a - 1])}*(1+{celda(fila['ipc'], col[a])})", f_num)

    # --- PAX mensual ---
    def tabla_pax(r0: int, titulo: str, datos: dict, fila_crec: int) -> int:
        ws.write(r0, 1, titulo, f_enc)
        for a in anios:
            ws.write(r0, col[a], a, f_enc)
        for m in range(1, 13):
            rr = r0 + m
            ws.write(rr, 1, MESES[m - 1], f_lab)
            for a in anios:
                v = (datos.get(a) or [None] * 12)[m - 1]
                if v is not None and not pd.isna(v):
                    ws.write_number(rr, col[a], float(v), f_inp if a in proy else f_num)
                elif a in proy and (a - 1) in col:
                    ws.write_formula(rr, col[a], f"={celda(rr, col[a - 1])}*(1+{celda(fila_crec, col[a])})", f_num)
                else:
                    ws.write_number(rr, col[a], 0, f_num)
        rt = r0 + 13
        ws.write(rt, 1, "Total", f_lab)
        for a in anios:
            ws.write_formula(rt, col[a], f"=SUM({celda(r0 + 1, col[a])}:{celda(r0 + 12, col[a])})", f_tot)
        return rt

    r += 2
    total_nac = tabla_pax(r, "Pasajeros nacionales embarcados", s.pax_nac, fila["cn"])
    r = total_nac + 2
    total_int = tabla_pax(r, "Pasajeros internacionales embarcados", s.pax_int, fila["ci"])

    # --- Ingresos ---
    r = total_int + 2
    ws.write(r, 1, "Ingresos ($)", f_enc)
    for a in anios:
        ws.write(r, col[a], a, f_enc)
    filas_ing = {}
    for c, etiqueta in CONCEPTOS_SIM.items():
        r += 1
        filas_ing[c] = r
        ws.write(r, 1, etiqueta, f_lab)
        for a in hist:
            ws.write_number(r, col[a], float(s.ingresos_historicos.get(a, {}).get(c, 0.0)), f_num)
        for a in proy:
            if c == "DE_NAC":
                ws.write_formula(r, col[a], f"={celda(total_nac, col[a])}*{celda(fila['tn'], col[a])}", f_num)
            elif c == "DE_INT":
                ws.write_formula(r, col[a], f"={celda(total_int, col[a])}*{celda(fila['usd'], col[a])}*{celda(fila['tc'], col[a])}", f_num)
            elif a == s.anio_base:
                ws.write_number(r, col[a], float(s.ingresos_base.get(c, 0.0)), f_inp)
            else:
                ws.write_formula(r, col[a], f"={celda(r, col[a - 1])}*(1+{celda(fila['ipc'], col[a])})", f_num)
    r += 1
    ws.write(r, 1, "Total", f_lab)
    primera, ultima = min(filas_ing.values()), max(filas_ing.values())
    for a in anios:
        ws.write_formula(r, col[a], f"=SUM({celda(primera, col[a])}:{celda(ultima, col[a])})", f_tot)

    # --- Pago al concesionario ---
    if filas_tpe:
        r += 2
        ws.write(r, 1, "Pago al concesionario", f_enc)
        for a in proy:
            if a >= inicio:
                ws.write(r, col[a], a, f_enc)
        for i, ft in enumerate(filas_tpe, start=1):
            r += 1
            ws.write(r, 1, f"Escenario {i}", f_lab)
            for a in proy:
                if a >= inicio:
                    ws.write_formula(
                        r, col[a], f"={celda(ft, col[a])}*({celda(total_nac, col[a])}+{celda(total_int, col[a])})", f_num)
    if s.notas:
        r += 2
        ws.write(r, 1, s.notas, f_nota)
    wb.close()
    return buf.getvalue()
