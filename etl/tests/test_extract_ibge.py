import gzip
import json

from painel_etl.extract.ibge import decodificar_resposta

REGISTROS = [{"municipio-id": 2611533, "municipio-nome": "Quixaba", "UF-sigla": "PE"}]


def test_decodifica_json_simples() -> None:
    corpo = json.dumps(REGISTROS).encode("utf-8")
    assert decodificar_resposta(corpo) == REGISTROS


def test_decodifica_json_comprimido_com_gzip() -> None:
    # A API do IBGE responde com gzip mesmo sem o cabeçalho Accept-Encoding.
    corpo = gzip.compress(json.dumps(REGISTROS, ensure_ascii=False).encode("utf-8"))
    assert decodificar_resposta(corpo) == REGISTROS
