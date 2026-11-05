"""Configuração lida de variáveis de ambiente (arquivo .env na raiz do repositório)."""

import os
from pathlib import Path

from dotenv import find_dotenv, load_dotenv

ETL_DIR = Path(__file__).resolve().parents[2]
DIR_RAW = ETL_DIR / "data" / "raw"
DIR_SQL = ETL_DIR / "sql"

# Procura o .env subindo a partir do diretório atual (etl/ -> raiz do repositório).
load_dotenv(find_dotenv(usecwd=True))


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL não definida: copie .env.example para .env")
    return url


def uf_padrao() -> str:
    return os.environ.get("ETL_UF", "PE")
