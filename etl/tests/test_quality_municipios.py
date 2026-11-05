from dataclasses import replace

from painel_etl.quality.municipios import checar_municipios
from painel_etl.transform.municipios import Municipio


def test_lista_oficial_de_pe_passa(municipios_pe: list[Municipio]) -> None:
    assert checar_municipios(municipios_pe, uf="PE") == []


def test_contagem_diferente_do_esperado(municipios_pe: list[Municipio]) -> None:
    problemas = checar_municipios(municipios_pe[:-1], uf="PE")
    assert problemas == ["contagem=184 esperado=185 uf=PE"]


def test_uf_sem_total_configurado(municipios_pe: list[Municipio]) -> None:
    problemas = checar_municipios(municipios_pe, uf="XX")
    assert any("não configurado" in p for p in problemas)


def test_detecta_duplicado(municipios_pe: list[Municipio]) -> None:
    com_duplicado = [*municipios_pe[:-1], municipios_pe[0]]
    problemas = checar_municipios(com_duplicado, uf="PE")
    assert f"codigo_ibge7 duplicado: ['{municipios_pe[0].codigo_ibge7}']" in problemas
    assert f"codigo_ibge6 duplicado: ['{municipios_pe[0].codigo_ibge6}']" in problemas


def test_detecta_uf_errada_e_nome_vazio(municipios_pe: list[Municipio]) -> None:
    alterados = [
        replace(municipios_pe[0], uf="PB"),
        replace(municipios_pe[1], nome=""),
        *municipios_pe[2:],
    ]
    problemas = checar_municipios(alterados, uf="PE")
    assert f"municípios fora da uf=PE: ['{municipios_pe[0].codigo_ibge7}']" in problemas
    assert f"municípios sem nome: ['{municipios_pe[1].codigo_ibge7}']" in problemas


def test_detecta_codigo_que_a_conversao_nao_reproduz(municipios_pe: list[Municipio]) -> None:
    # Simula um município novo cujo DV foge do algoritmo e não está em EXCECOES_DV.
    recife = next(m for m in municipios_pe if m.codigo_ibge6 == "261160")
    alterados = [
        replace(recife, codigo_ibge7="2611609") if m is recife else m for m in municipios_pe
    ]
    problemas = checar_municipios(alterados, uf="PE")
    assert problemas == ["conversão 6->7 diverge do código oficial: ['2611609']"]
