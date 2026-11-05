"""Passo do ETL: carrega a dimensão `municipio` a partir da API do IBGE.

Uso (dentro de etl/):
    uv run python -m painel_etl.carga_municipios --uf PE
"""

import argparse
import logging
import sys

import psycopg

from painel_etl.config import DIR_RAW, database_url, uf_padrao
from painel_etl.extract.ibge import baixar_municipios, salvar_json
from painel_etl.load.municipios import (
    aplicar_schema,
    contar_municipios,
    gravar_municipios,
)
from painel_etl.logs import configurar_logs, kv
from painel_etl.quality.municipios import checar_municipios
from painel_etl.transform.municipios import normalizar_municipios

logger = logging.getLogger("painel_etl.carga_municipios")


class CargaAbortadaError(Exception):
    """Alguma checagem de qualidade falhou; nada foi gravado."""


def executar(uf: str) -> int:
    """Roda extract -> transform -> quality -> load. Retorna o total da UF no banco."""
    uf = uf.upper()

    brutos = baixar_municipios(uf)
    salvar_json(brutos, DIR_RAW / f"ibge_municipios_{uf.lower()}.json")
    logger.info(kv("extract", uf=uf, linhas_lidas=len(brutos)))

    municipios = normalizar_municipios(brutos)
    logger.info(kv("transform", uf=uf, linhas=len(municipios)))

    problemas = checar_municipios(municipios, uf=uf)
    if problemas:
        for problema in problemas:
            logger.error(kv("quality_falhou", uf=uf, detalhe=problema))
        raise CargaAbortadaError(f"{len(problemas)} checagem(ns) falharam para uf={uf}")
    logger.info(kv("quality_ok", uf=uf, linhas=len(municipios)))

    # O bloco `with` faz commit no final ou rollback se houver exceção.
    with psycopg.connect(database_url()) as conn:
        aplicar_schema(conn)
        gravadas = gravar_municipios(conn, municipios)
        total = contar_municipios(conn, uf)
    logger.info(kv("load", uf=uf, linhas_gravadas=gravadas, total_na_tabela=total))
    return total


def main() -> None:
    parser = argparse.ArgumentParser(description="Carrega a dimensão municipio (IBGE).")
    parser.add_argument("--uf", default=uf_padrao(), help="sigla da UF (padrão: ETL_UF ou PE)")
    args = parser.parse_args()

    configurar_logs()
    try:
        executar(args.uf)
    except CargaAbortadaError as erro:
        logger.error(kv("carga_abortada", uf=args.uf, motivo=erro))
        sys.exit(1)


if __name__ == "__main__":
    main()
