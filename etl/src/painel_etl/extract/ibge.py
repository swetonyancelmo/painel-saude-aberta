"""Download da lista oficial de municípios (API de localidades do IBGE)."""

import gzip
import json
import urllib.request
from pathlib import Path
from typing import Any

URL_MUNICIPIOS_UF = (
    "https://servicodados.ibge.gov.br/api/v1/localidades/estados/{uf}/municipios?view=nivelado"
)


ASSINATURA_GZIP = b"\x1f\x8b"


def decodificar_resposta(corpo: bytes) -> list[dict[str, Any]]:
    """Converte o corpo da resposta em JSON.

    A API do IBGE devolve o corpo comprimido com gzip mesmo quando o cliente não pede,
    e o urllib não descomprime sozinho. Por isso checamos a assinatura do gzip.
    """
    if corpo.startswith(ASSINATURA_GZIP):
        corpo = gzip.decompress(corpo)
    dados: list[dict[str, Any]] = json.loads(corpo.decode("utf-8"))
    return dados


def baixar_municipios(uf: str, timeout: float = 30) -> list[dict[str, Any]]:
    """Retorna a resposta da API (formato "nivelado": um dicionário plano por município)."""
    url = URL_MUNICIPIOS_UF.format(uf=uf.upper())
    requisicao = urllib.request.Request(url, headers={"User-Agent": "painel-saude-aberta-etl"})
    with urllib.request.urlopen(requisicao, timeout=timeout) as resposta:
        return decodificar_resposta(resposta.read())


def salvar_json(dados: list[dict[str, Any]], caminho: Path) -> None:
    """Guarda a resposta bruta em data/raw/ para auditoria e reprocessamento."""
    caminho.parent.mkdir(parents=True, exist_ok=True)
    caminho.write_text(json.dumps(dados, ensure_ascii=False, indent=1), encoding="utf-8")
