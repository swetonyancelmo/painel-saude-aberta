"""Transformação dos microdados de vacinação em doses por município × vacina × mês.

Cada chunk do CSV passa por funções pequenas e puras (DataFrame entra, DataFrame sai):

    filtrar_uf -> filtrar_validos -> normalizar -> agregar

e os agregados parciais são somados no final (`somar_parciais`). Assim, a memória guarda
só contagens (milhares de linhas), nunca os microdados do mês inteiro.

Decisões (ver notebook 01_exploracao):
- município = município do ESTABELECIMENTO (onde a dose foi aplicada);
- vacina_id = co_vacina (código do SI-PNI); o nome normalizado vai para a dimensão vacina;
- descarta registros com st_documento != "final" ou com dt_deletado_rnds preenchido;
- código de município ou data inválidos viram nulo (não derrubam o processo) e são
  mantidos na agregação (dropna=False) para a checagem de qualidade apontá-los.
"""

import logging
import unicodedata
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from painel_etl.logs import kv
from painel_etl.transform.codigo_municipio import codigo6_para_7

logger = logging.getLogger("painel_etl.transform.vacinacao")

# Só o necessário. Dados do paciente (co_paciente etc.) não são lidos.
COLUNAS_LIDAS = [
    "sg_uf_estabelecimento",
    "co_municipio_estabelecimento",
    "co_vacina",
    "sg_imunobiologico",
    "ds_nome",
    "dt_vacina",
    "st_documento",
    "dt_deletado_rnds",
]
CHAVE_FATO = ["municipio_id", "vacina_id", "ano_mes"]
COLUNAS_FATO = [*CHAVE_FATO, "total_doses"]
COLUNAS_VACINA = ["vacina_id", "sigla", "nome"]


@dataclass(frozen=True)
class ResultadoTransform:
    doses: pd.DataFrame  # colunas da tabela fato: municipio_id, vacina_id, ano_mes, total_doses
    vacinas: pd.DataFrame  # dimensão vacina: vacina_id, sigla, nome
    linhas_lidas: int  # linhas do CSV nacional
    linhas_uf: int  # linhas do estabelecimento na UF
    linhas_validas: int  # depois de descartar excluídos/não finais (= soma de total_doses)


# --- leitura --------------------------------------------------------------------------


def ler_em_chunks(caminho: Path, chunksize: int = 500_000) -> Iterator[pd.DataFrame]:
    """Lê o CSV do OpenDataSUS em pedaços, só com as colunas usadas, tudo como texto."""
    yield from pd.read_csv(
        caminho,
        sep=";",
        encoding="latin-1",
        usecols=COLUNAS_LIDAS,
        dtype=str,  # preserva zeros à esquerda; conversões são explícitas em `normalizar`
        keep_default_na=False,
        na_values=[""],
        chunksize=chunksize,
    )


# --- funções puras --------------------------------------------------------------------


def filtrar_uf(df: pd.DataFrame, uf: str) -> pd.DataFrame:
    """Mantém só as doses aplicadas em estabelecimentos da UF."""
    return df.loc[df["sg_uf_estabelecimento"] == uf.upper()]


def filtrar_validos(df: pd.DataFrame) -> pd.DataFrame:
    """Descarta registros excluídos ou que não estão no status final."""
    return df.loc[(df["st_documento"] == "final") & df["dt_deletado_rnds"].isna()]


def normalizar_nome_vacina(nome: str) -> str:
    """Padroniza o nome: Unicode NFC, sem espaços sobrando, primeira letra maiúscula.

    O resto da caixa é mantido para não estragar siglas ("vacina BCG", "G1P[8]").
    """
    texto = " ".join(unicodedata.normalize("NFC", nome).split())
    return texto[:1].upper() + texto[1:]


def _codigo6_para_7_ou_nulo(codigo6: object) -> int | None:
    if not isinstance(codigo6, str):
        return None
    try:
        return int(codigo6_para_7(codigo6.strip()))
    except ValueError:
        return None


def normalizar(df: pd.DataFrame) -> pd.DataFrame:
    """Converte para as colunas finais: municipio_id, vacina_id, ano_mes, sigla, nome."""
    # Poucos códigos distintos por chunk: converte cada um uma vez e mapeia.
    codigos = df["co_municipio_estabelecimento"]
    mapa = {c: _codigo6_para_7_ou_nulo(c) for c in codigos.dropna().unique()}
    datas = pd.to_datetime(df["dt_vacina"], format="%Y-%m-%d", errors="coerce")
    return pd.DataFrame(
        {
            "municipio_id": codigos.map(mapa).astype("Int64"),
            "vacina_id": pd.to_numeric(df["co_vacina"], errors="coerce").astype("Int64"),
            "ano_mes": datas.dt.to_period("M").dt.to_timestamp(),  # primeiro dia do mês
            "sigla": df["sg_imunobiologico"].str.strip(),
            "nome": df["ds_nome"].map(normalizar_nome_vacina, na_action="ignore"),
        },
        index=df.index,
    )


def agregar(df: pd.DataFrame) -> pd.DataFrame:
    """Conta doses por município × vacina × mês (mantém chaves nulas para a qualidade)."""
    return (
        df.groupby(CHAVE_FATO, dropna=False)
        .size()
        .rename("total_doses")
        .reset_index()
        .astype({"total_doses": "int64"})
    )


def somar_parciais(parciais: list[pd.DataFrame]) -> pd.DataFrame:
    """Soma os agregados de cada chunk (a mesma chave pode aparecer em vários chunks)."""
    if not parciais:
        return pd.DataFrame(columns=COLUNAS_FATO)
    return (
        pd.concat(parciais, ignore_index=True)
        .groupby(CHAVE_FATO, dropna=False)["total_doses"]
        .sum()
        .reset_index()
        .sort_values(CHAVE_FATO, ignore_index=True)
    )


def extrair_vacinas(df: pd.DataFrame) -> pd.DataFrame:
    """Lista de vacinas distintas (vacina_id, sigla, nome) para a dimensão `vacina`."""
    return (
        df.loc[df["vacina_id"].notna(), COLUNAS_VACINA]
        .drop_duplicates("vacina_id")
        .sort_values("vacina_id", ignore_index=True)
    )


# --- orquestração ---------------------------------------------------------------------


def transformar_mes(caminho: Path, uf: str, chunksize: int = 500_000) -> ResultadoTransform:
    """Lê o CSV de um mês e devolve as doses agregadas da UF e a lista de vacinas."""
    parciais: list[pd.DataFrame] = []
    vacinas: list[pd.DataFrame] = []
    lidas = na_uf = validas = 0

    for chunk in ler_em_chunks(caminho, chunksize):
        lidas += len(chunk)
        da_uf = filtrar_uf(chunk, uf)
        na_uf += len(da_uf)
        if da_uf.empty:
            continue
        validos = filtrar_validos(da_uf)
        validas += len(validos)
        normalizado = normalizar(validos)
        parciais.append(agregar(normalizado))
        vacinas.append(extrair_vacinas(normalizado))

    doses = somar_parciais(parciais)
    todas_vacinas = (
        extrair_vacinas(pd.concat(vacinas, ignore_index=True))
        if vacinas
        else pd.DataFrame(columns=COLUNAS_VACINA)
    )
    logger.info(
        kv(
            "transform",
            arquivo=caminho.name,
            uf=uf,
            linhas_lidas=lidas,
            linhas_uf=na_uf,
            linhas_descartadas=na_uf - validas,
            linhas_validas=validas,
            linhas_agregadas=len(doses),
            vacinas=len(todas_vacinas),
        )
    )
    return ResultadoTransform(doses, todas_vacinas, lidas, na_uf, validas)
