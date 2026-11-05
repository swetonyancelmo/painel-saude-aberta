import json
from pathlib import Path
from typing import Any

import pytest

from painel_etl.transform.municipios import Municipio, normalizar_municipios

FIXTURES = Path(__file__).parent / "fixtures"


@pytest.fixture
def registros_ibge_pe() -> list[dict[str, Any]]:
    """Resposta real da API de localidades do IBGE para PE (2026-11-04), só com os campos usados."""
    dados: list[dict[str, Any]] = json.loads(
        (FIXTURES / "ibge_municipios_pe.json").read_text(encoding="utf-8")
    )
    return dados


@pytest.fixture
def municipios_pe(registros_ibge_pe: list[dict[str, Any]]) -> list[Municipio]:
    return normalizar_municipios(registros_ibge_pe)
