"""Testes de integração com o PostgreSQL local (docker compose up -d).

Rodam dentro de uma transação que sofre rollback no final: o banco não é alterado.
São pulados se o banco não estiver acessível.
"""

from collections.abc import Iterator

import psycopg
import pytest

from painel_etl.config import database_url
from painel_etl.load.municipios import (
    aplicar_schema,
    contar_municipios,
    gravar_municipios,
)
from painel_etl.transform.municipios import Municipio

pytestmark = pytest.mark.integracao


@pytest.fixture
def conn() -> Iterator[psycopg.Connection]:
    try:
        conexao = psycopg.connect(database_url(), connect_timeout=2)
    except (psycopg.OperationalError, RuntimeError) as erro:
        pytest.skip(f"PostgreSQL indisponível: {erro}")
    try:
        aplicar_schema(conexao)
        conexao.execute("DELETE FROM municipio")
        yield conexao
    finally:
        conexao.rollback()
        conexao.close()


def test_carga_grava_todos_os_municipios(
    conn: psycopg.Connection, municipios_pe: list[Municipio]
) -> None:
    assert gravar_municipios(conn, municipios_pe) == 185
    assert contar_municipios(conn, "PE") == 185


def test_carga_e_idempotente(conn: psycopg.Connection, municipios_pe: list[Municipio]) -> None:
    gravar_municipios(conn, municipios_pe)
    gravar_municipios(conn, municipios_pe)
    assert contar_municipios(conn, "PE") == 185


def test_schema_rejeita_codigos_inconsistentes(conn: psycopg.Connection) -> None:
    with pytest.raises(psycopg.errors.CheckViolation):
        conn.execute("INSERT INTO municipio VALUES (2611606, 999999, 'Recife', 'PE')")
