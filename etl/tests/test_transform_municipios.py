from typing import Any

from painel_etl.transform.municipios import Municipio, normalizar_municipios


def test_normaliza_registro_da_api() -> None:
    registros = [{"municipio-id": 2611606, "municipio-nome": " Recife ", "UF-sigla": "pe"}]
    assert normalizar_municipios(registros) == [
        Municipio(codigo_ibge7="2611606", codigo_ibge6="261160", nome="Recife", uf="PE")
    ]


def test_ordena_por_codigo() -> None:
    registros = [
        {"municipio-id": 2611606, "municipio-nome": "Recife", "UF-sigla": "PE"},
        {"municipio-id": 2600054, "municipio-nome": "Abreu e Lima", "UF-sigla": "PE"},
    ]
    codigos = [m.codigo_ibge7 for m in normalizar_municipios(registros)]
    assert codigos == ["2600054", "2611606"]


def test_fixture_de_pe_inclui_fernando_de_noronha(registros_ibge_pe: list[dict[str, Any]]) -> None:
    municipios = {m.codigo_ibge7: m for m in normalizar_municipios(registros_ibge_pe)}
    assert len(municipios) == 185
    assert municipios["2605459"].nome == "Fernando de Noronha"
    assert municipios["2605459"].codigo_ibge6 == "260545"
