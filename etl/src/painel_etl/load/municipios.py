"""Gravação idempotente da dimensão `municipio` no PostgreSQL."""

import psycopg

from painel_etl.config import DIR_SQL
from painel_etl.transform.municipios import Municipio

ARQUIVO_DDL = DIR_SQL / "001_municipio.sql"

SQL_UPSERT = """
    INSERT INTO municipio (id, codigo_ibge6, nome, uf)
    VALUES (%s, %s, %s, %s)
    ON CONFLICT (id) DO UPDATE
       SET codigo_ibge6 = EXCLUDED.codigo_ibge6,
           nome         = EXCLUDED.nome,
           uf           = EXCLUDED.uf
"""


def aplicar_schema(conn: psycopg.Connection) -> None:
    """Cria a tabela se ainda não existir."""
    conn.execute(ARQUIVO_DDL.read_text(encoding="utf-8"))


def gravar_municipios(conn: psycopg.Connection, municipios: list[Municipio]) -> int:
    """Faz UPSERT dos municípios. Não faz commit: quem chama controla a transação."""
    linhas = [(int(m.codigo_ibge7), int(m.codigo_ibge6), m.nome, m.uf) for m in municipios]
    with conn.cursor() as cur:
        cur.executemany(SQL_UPSERT, linhas)
    return len(linhas)


def contar_municipios(conn: psycopg.Connection, uf: str) -> int:
    linha = conn.execute("SELECT count(*) FROM municipio WHERE uf = %s", (uf,)).fetchone()
    return int(linha[0]) if linha else 0
