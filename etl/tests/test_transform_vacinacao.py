"""Testes do transform de vacinação com a fixture de 20 linhas (latin-1, ';', CRLF).

Conteúdo da fixture tests/fixtures/vacinacao_amostra.csv:
- 15 doses válidas em PE (Recife, Quixaba, Fernando de Noronha, Caruaru, Petrolina);
- 1 registro excluído (dt_deletado_rnds) e 1 com st_documento "entered-in-error";
- 3 doses em estabelecimentos de SP e PB (uma delas de paciente de PE);
- 1 dose em Recife de paciente da BA (conta, porque vale o estabelecimento).
"""

from pathlib import Path

import pandas as pd
import pytest

from painel_etl.transform.vacinacao import (
    COLUNAS_FATO,
    agregar,
    filtrar_uf,
    filtrar_validos,
    ler_em_chunks,
    normalizar,
    normalizar_nome_vacina,
    somar_parciais,
    transformar_mes,
)

FIXTURE = Path(__file__).parent / "fixtures" / "vacinacao_amostra.csv"
JAN_2024 = pd.Timestamp("2024-01-01")

# (municipio_id, vacina_id) -> total esperado em jan/2024
ESPERADO = {
    (2604106, 42): 3,  # Caruaru, Penta
    (2604106, 103): 1,  # Caruaru, COVID-19 bivalente
    (2605459, 24): 2,  # Fernando de Noronha, tríplice viral
    (2611101, 99): 1,  # Petrolina, COVID-19 pediátrica
    (2611533, 14): 2,  # Quixaba (exceção do dígito verificador), febre amarela
    (2611606, 9): 3,  # Recife, hepatite B (inclui paciente da BA)
    (2611606, 103): 3,  # Recife, COVID-19 bivalente (sem o excluído e o entered-in-error)
}


@pytest.fixture
def bruto() -> pd.DataFrame:
    return pd.concat(ler_em_chunks(FIXTURE), ignore_index=True)


def linha(**campos: str | None) -> dict[str, str | None]:
    """Uma linha bruta válida de Recife, com os campos sobrescritos."""
    base: dict[str, str | None] = {
        "sg_uf_estabelecimento": "PE",
        "co_municipio_estabelecimento": "261160",
        "co_vacina": "9",
        "sg_imunobiologico": "HB",
        "ds_nome": "vacina hepatite B (recombinante)",
        "dt_vacina": "2024-01-10",
        "st_documento": "final",
        "dt_deletado_rnds": None,
    }
    return base | campos


# --- leitura ----------------------------------------------------------------------------


def test_le_so_as_colunas_necessarias(bruto: pd.DataFrame) -> None:
    assert len(bruto) == 20
    assert "co_paciente" not in bruto.columns
    assert "no_municipio_estabelecimento" not in bruto.columns


def test_le_latin1_e_preserva_texto(bruto: pd.DataFrame) -> None:
    assert "vacina sarampo, caxumba, rubéola (atenuada)" in set(bruto["ds_nome"])
    assert bruto["co_municipio_estabelecimento"].str.len().eq(6).all()


# --- filtros ----------------------------------------------------------------------------


def test_filtra_pelo_estabelecimento_da_uf(bruto: pd.DataFrame) -> None:
    pe = filtrar_uf(bruto, "pe")
    assert len(pe) == 17
    assert set(pe["sg_uf_estabelecimento"]) == {"PE"}
    # paciente da BA vacinado em Recife conta; paciente de PE vacinado em SP não
    assert "355030" not in set(pe["co_municipio_estabelecimento"])


def test_descarta_excluidos_e_nao_finais() -> None:
    df = pd.DataFrame(
        [
            linha(),
            linha(dt_deletado_rnds="2024-02-01"),
            linha(st_documento="entered-in-error"),
        ]
    )
    assert len(filtrar_validos(df)) == 1


# --- normalização -----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("entrada", "esperado"),
    [
        ("  vacina hepatite B  (recombinante) ", "Vacina hepatite B (recombinante)"),
        ("vacina BCG", "Vacina BCG"),
        ("vacina rubéola", "Vacina rubéola"),  # acento decomposto (NFD) -> NFC
        ("", ""),
    ],
)
def test_normaliza_nome_da_vacina(entrada: str, esperado: str) -> None:
    resultado = normalizar_nome_vacina(entrada)
    assert resultado == esperado
    assert len(resultado) == len(esperado)  # garante a forma composta (NFC)


def test_normaliza_codigo_vacina_e_data() -> None:
    df = pd.DataFrame(
        [
            linha(co_municipio_estabelecimento="261153", dt_vacina="2024-01-31"),
            linha(co_municipio_estabelecimento="260545", co_vacina="103"),
        ]
    )
    resultado = normalizar(df)
    assert resultado["municipio_id"].tolist() == [2611533, 2605459]  # Quixaba, F. de Noronha
    assert resultado["vacina_id"].tolist() == [9, 103]
    assert resultado["ano_mes"].tolist() == [JAN_2024, JAN_2024]
    assert resultado["nome"].tolist() == ["Vacina hepatite B (recombinante)"] * 2


def test_valores_invalidos_viram_nulo_sem_derrubar_o_processo() -> None:
    df = pd.DataFrame(
        [linha(co_municipio_estabelecimento="26116", co_vacina="abc", dt_vacina="31/01/2024")]
    )
    resultado = normalizar(df)
    assert resultado["municipio_id"].isna().all()
    assert resultado["vacina_id"].isna().all()
    assert resultado["ano_mes"].isna().all()


# --- agregação --------------------------------------------------------------------------


def test_agrega_por_municipio_vacina_mes() -> None:
    df = normalizar(pd.DataFrame([linha(), linha(), linha(co_vacina="103")]))
    resultado = agregar(df)
    assert list(resultado.columns) == COLUNAS_FATO
    assert sorted(resultado["total_doses"]) == [1, 2]


def test_agregacao_mantem_chave_nula_para_a_qualidade() -> None:
    df = normalizar(pd.DataFrame([linha(), linha(co_municipio_estabelecimento="xx")]))
    resultado = agregar(df)
    assert resultado["total_doses"].sum() == 2  # nenhuma dose some em silêncio
    assert resultado["municipio_id"].isna().sum() == 1


def test_soma_parciais_de_chunks_diferentes() -> None:
    parte1 = agregar(normalizar(pd.DataFrame([linha(), linha(co_vacina="103")])))
    parte2 = agregar(normalizar(pd.DataFrame([linha(), linha()])))
    resultado = somar_parciais([parte1, parte2])
    totais = dict(zip(resultado["vacina_id"], resultado["total_doses"], strict=True))
    assert totais == {9: 3, 103: 1}


def test_soma_sem_parciais_devolve_dataframe_vazio() -> None:
    assert list(somar_parciais([]).columns) == COLUNAS_FATO


# --- fluxo completo ---------------------------------------------------------------------


@pytest.mark.parametrize("chunksize", [3, 7, 1000])
def test_transformar_mes_de_pe(chunksize: int) -> None:
    resultado = transformar_mes(FIXTURE, "PE", chunksize=chunksize)

    doses = resultado.doses
    assert list(doses.columns) == COLUNAS_FATO
    assert not doses.duplicated(["municipio_id", "vacina_id", "ano_mes"]).any()
    assert set(doses["ano_mes"]) == {JAN_2024}
    obtido = {
        (m, v): t
        for m, v, t in zip(
            doses["municipio_id"], doses["vacina_id"], doses["total_doses"], strict=True
        )
    }
    assert obtido == ESPERADO

    assert (resultado.linhas_lidas, resultado.linhas_uf, resultado.linhas_validas) == (20, 17, 15)
    assert doses["total_doses"].sum() == resultado.linhas_validas


def test_transformar_mes_devolve_vacinas_normalizadas() -> None:
    vacinas = transformar_mes(FIXTURE, "PE", chunksize=3).vacinas

    assert vacinas["vacina_id"].tolist() == [9, 14, 24, 42, 99, 103]
    nomes = dict(zip(vacinas["vacina_id"], vacinas["nome"], strict=True))
    # a linha com espaços sobrando não gera uma segunda versão do nome
    assert nomes[9] == "Vacina hepatite B (recombinante)"
    assert nomes[24] == "Vacina sarampo, caxumba, rubéola (atenuada)"
