import json
from pathlib import Path

import pytest

from painel_etl.transform.codigo_municipio import (
    codigo6_para_7,
    codigo7_para_6,
    digito_verificador,
)

FIXTURE_PE = Path(__file__).parent / "fixtures" / "ibge_municipios_pe.json"


def codigos_oficiais_pe() -> list[str]:
    registros = json.loads(FIXTURE_PE.read_text(encoding="utf-8"))
    return [str(r["municipio-id"]) for r in registros]


@pytest.mark.parametrize(
    ("codigo6", "codigo7"),
    [
        ("261160", "2611606"),  # Recife
        ("260545", "2605459"),  # Fernando de Noronha (distrito estadual)
        ("260005", "2600054"),  # Abreu e Lima
    ],
)
def test_converte_nos_dois_sentidos(codigo6: str, codigo7: str) -> None:
    assert codigo6_para_7(codigo6) == codigo7
    assert codigo7_para_6(codigo7) == codigo6


def test_quixaba_e_excecao_ao_algoritmo_do_dv() -> None:
    # O algoritmo daria 2611531, mas o código oficial é 2611533.
    assert digito_verificador("261153") == "1"
    assert codigo6_para_7("261153") == "2611533"


def test_ida_e_volta_em_todos_os_municipios_de_pe() -> None:
    codigos = codigos_oficiais_pe()
    assert len(codigos) == 185
    for codigo7 in codigos:
        assert codigo6_para_7(codigo7_para_6(codigo7)) == codigo7


@pytest.mark.parametrize("entrada", ["26116", "2611606", "26116a", "", " 261160"])
def test_codigo6_invalido(entrada: str) -> None:
    with pytest.raises(ValueError, match="inválido"):
        codigo6_para_7(entrada)


@pytest.mark.parametrize("entrada", ["261160", "26116060", "261160X"])
def test_codigo7_invalido(entrada: str) -> None:
    with pytest.raises(ValueError, match="inválido"):
        codigo7_para_6(entrada)
