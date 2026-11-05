"""Normalização da lista de municípios do IBGE para o formato da dimensão `municipio`."""

from dataclasses import dataclass
from typing import Any

from painel_etl.transform.codigo_municipio import codigo7_para_6


@dataclass(frozen=True)
class Municipio:
    codigo_ibge7: str
    codigo_ibge6: str
    nome: str
    uf: str


def normalizar_municipios(registros: list[dict[str, Any]]) -> list[Municipio]:
    """Converte a resposta "nivelada" da API do IBGE em `Municipio`s, ordenados por código."""
    municipios = [
        Municipio(
            codigo_ibge7=str(r["municipio-id"]),
            codigo_ibge6=codigo7_para_6(str(r["municipio-id"])),
            nome=str(r["municipio-nome"]).strip(),
            uf=str(r["UF-sigla"]).strip().upper(),
        )
        for r in registros
    ]
    return sorted(municipios, key=lambda m: m.codigo_ibge7)
