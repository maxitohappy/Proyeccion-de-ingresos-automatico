"""Constantes compartidas: columnas del informe SAC, conceptos y meses."""

# Columnas crudas del informe "Ingresos Operaciones por Concepto" (SAC), columnas A–V.
COLUMNAS_SAC = [
    "UNIDAD_PRESTACION_SERVICIO",
    "DESC_UNID_PRESTACION_SERVICIO",
    "UNIDAD_FACTURACION",
    "DESCRIPCION_UNIDAD_FACTURACION",
    "FECHA_EMISION",
    "FECHA_VENCIMIENTO",
    "FECHA_PAGO",
    "DOCUMENTO",
    "TIPO",
    "NUMERO",
    "PERIODO",
    "RUT",
    "CLIENTE",
    "ESTADO",
    "MONEDA",
    "TASA",
    "DETALLE",
    "MONTO",
    "CUENTA_GESTION",
    "CUENTA_PRESUPUESTARIA",
    "MES",
    "TIPO_DE_CAMBIO",
]

# Columnas mínimas sin las cuales no se puede clasificar.
COLUMNAS_OBLIGATORIAS = ["UNIDAD_PRESTACION_SERVICIO", "MONTO", "CUENTA_GESTION", "MES"]

# Unidad cuyos ingresos se transfieren a la Sociedad Concesionaria (Aldeasa) y se descartan.
UNIDADES_DESCARTADAS_DEFECTO = [5220]

NACIONAL = "Nacional"
INTERNACIONAL = "Internacional"

# Conceptos del plan de cuentas (hoja "Conceptos").
DE = "Derecho de Embarque"
TASAS = "Tasas"
COMBUSTIBLE = "Combustible"
CONCESIONES = "Concesiones"
OTROS = "Otros Ingresos"
CONCEPTOS = [DE, TASAS, COMBUSTIBLE, CONCESIONES, OTROS]

# Los 7 conceptos con que se proyecta (instructivo, actividad 6).
CONCEPTOS_PROYECCION = {
    "DE_NAC": "Derecho de embarque nacional",
    "DE_INT": "Derecho de embarque internacional",
    "TASAS_NAC": "Tasas nacionales",
    "TASAS_INT": "Tasas internacionales",
    "COMBUSTIBLE": "Combustibles",
    "CONCESIONES": "Concesiones",
    "OTROS": "Otros ingresos",
}

MESES = [
    "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
    "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
]
MESES_CORTOS = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"]


def concepto_proyeccion(concepto: str, tipo: str) -> str:
    """Traduce (concepto del plan de cuentas, tipo de ingreso) a la clave de proyección."""
    internacional = str(tipo).strip().lower().startswith("int")
    if concepto == DE:
        return "DE_INT" if internacional else "DE_NAC"
    if concepto == TASAS:
        return "TASAS_INT" if internacional else "TASAS_NAC"
    if concepto == COMBUSTIBLE:
        return "COMBUSTIBLE"
    if concepto == CONCESIONES:
        return "CONCESIONES"
    return "OTROS"
