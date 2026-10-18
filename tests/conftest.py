import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
EJEMPLOS = RAIZ / "ejemplos"


@pytest.fixture(autouse=True)
def datos_temporales(tmp_path, monkeypatch):
    """Cada test usa su propia carpeta de datos."""
    monkeypatch.setenv("PROYECCION_DATA_DIR", str(tmp_path / "data"))
    return tmp_path / "data"
