"""Download dos microdados mensais de vacinação (SI-PNI) publicados pelo OpenDataSUS.

Cada mês é um zip público no S3 do Ministério da Saúde com um único CSV dentro
(ver ADR-0003). O fluxo de `extract(ano, mes)`:

1. Se o CSV já existe em data/raw/, não acessa a rede (cache pelo nome).
2. Se o zip já existe (download anterior concluído), só descompacta.
3. Senão, baixa o zip em streaming para um arquivo `.part`, confere o tamanho com o
   Content-Length e só então renomeia. Um arquivo com o nome final está sempre completo,
   e é isso que torna seguro o cache pelo nome.
4. Descompacta o CSV (também via `.part`), confere o tamanho e apaga o zip.

Uso (dentro de etl/):
    uv run python -m painel_etl.extract.vacinacao --ano 2024 --mes 1
"""

import argparse
import logging
import time
import urllib.error
import urllib.request
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import BinaryIO, Protocol

from painel_etl.config import DIR_RAW
from painel_etl.logs import configurar_logs, kv

logger = logging.getLogger("painel_etl.extract.vacinacao")

URL_BASE = "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/PNI/csv"
MESES = ("jan", "fev", "mar", "abr", "mai", "jun", "jul", "ago", "set", "out", "nov", "dez")

TAMANHO_BLOCO = 8 * 1024 * 1024  # 8 MB por leitura
LOG_PROGRESSO_A_CADA = 256 * 1024 * 1024  # um log de progresso a cada 256 MB
STATUS_TEMPORARIOS = {408, 429, 500, 502, 503, 504}


class Resposta(Protocol):
    """O que usamos da resposta HTTP (permite trocar por um objeto falso nos testes)."""

    status: int

    def read(self, n: int = -1) -> bytes: ...
    def getheader(self, nome: str) -> str | None: ...
    def __enter__(self) -> "Resposta": ...
    def __exit__(self, *args: object) -> None: ...


AbrirUrl = Callable[[str, float], Resposta]


class ErroDownload(Exception):
    """Falha definitiva ao baixar um arquivo (já com URL e status na mensagem)."""


def _abrir_url_padrao(url: str, timeout: float) -> Resposta:
    requisicao = urllib.request.Request(url, headers={"User-Agent": "painel-saude-aberta-etl"})
    resposta: Resposta = urllib.request.urlopen(requisicao, timeout=timeout)
    return resposta


def _validar_periodo(ano: int, mes: int) -> None:
    if not 1 <= mes <= 12:
        raise ValueError(f"mês inválido: {mes} (esperado 1 a 12)")
    if ano < 2020:
        raise ValueError(f"ano inválido: {ano} (os microdados do OpenDataSUS começam em 2020)")


def nome_csv(ano: int, mes: int) -> str:
    _validar_periodo(ano, mes)
    return f"vacinacao_{MESES[mes - 1]}_{ano}.csv"


def url_zip(ano: int, mes: int) -> str:
    _validar_periodo(ano, mes)
    return f"{URL_BASE}/vacinacao_{MESES[mes - 1]}_{ano}_csv.zip"


def _copiar_em_blocos(origem: BinaryIO | Resposta, destino: BinaryIO, url: str) -> int:
    total = 0
    proximo_log = LOG_PROGRESSO_A_CADA
    while bloco := origem.read(TAMANHO_BLOCO):
        destino.write(bloco)
        total += len(bloco)
        if total >= proximo_log:
            logger.info(kv("download_progresso", url=url, baixado_mb=total // 1024**2))
            proximo_log += LOG_PROGRESSO_A_CADA
    return total


def _baixar_uma_vez(url: str, destino: Path, abrir_url: AbrirUrl, timeout: float) -> int:
    """Uma tentativa de download. Grava em `destino` e confere o tamanho."""
    with abrir_url(url, timeout) as resposta, destino.open("wb") as arquivo:
        esperado = resposta.getheader("Content-Length")
        baixado = _copiar_em_blocos(resposta, arquivo, url)
    if esperado is not None and baixado != int(esperado):
        raise ConnectionError(f"download incompleto: {baixado} de {esperado} bytes")
    return baixado


def baixar_com_retry(
    url: str,
    destino: Path,
    *,
    tentativas: int = 4,
    espera_inicial: float = 2.0,
    timeout: float = 60.0,
    abrir_url: AbrirUrl = _abrir_url_padrao,
    dormir: Callable[[float], None] = time.sleep,
) -> int:
    """Baixa `url` para `destino` com retry e backoff exponencial (2 s, 4 s, 8 s, ...).

    Erros temporários (rede, timeout, HTTP 408/429/5xx, download incompleto) são
    repetidos. Os demais (ex.: 404) falham na hora. Retorna o tamanho em bytes.
    """
    parcial = destino.with_name(destino.name + ".part")
    for tentativa in range(1, tentativas + 1):
        try:
            tamanho = _baixar_uma_vez(url, parcial, abrir_url, timeout)
        except urllib.error.HTTPError as erro:
            if erro.code not in STATUS_TEMPORARIOS:
                parcial.unlink(missing_ok=True)
                raise ErroDownload(f"falha ao baixar {url}: status={erro.code}") from erro
            motivo = f"status={erro.code}"
        except (urllib.error.URLError, TimeoutError, ConnectionError) as erro:
            motivo = f"{type(erro).__name__}: {erro}"
        else:
            parcial.replace(destino)  # renomeação atômica: só agora o nome final existe
            return tamanho

        parcial.unlink(missing_ok=True)
        if tentativa == tentativas:
            raise ErroDownload(f"falha ao baixar {url} após {tentativas} tentativas: {motivo}")
        espera = espera_inicial * 2 ** (tentativa - 1)
        logger.warning(
            kv(
                "download_tentativa_falhou",
                url=url,
                tentativa=tentativa,
                espera_s=espera,
                motivo=motivo,
            )
        )
        dormir(espera)
    raise AssertionError("inalcançável")  # o laço sempre retorna ou levanta erro


def descompactar_csv(arquivo_zip: Path, nome: str, destino: Path) -> int:
    """Extrai `nome` do zip para `destino` (via `.part`) e confere o tamanho declarado."""
    parcial = destino.with_name(destino.name + ".part")
    with zipfile.ZipFile(arquivo_zip) as zf:
        info = zf.getinfo(nome)
        with zf.open(info) as origem, parcial.open("wb") as saida:
            tamanho = _copiar_em_blocos(origem, saida, str(arquivo_zip))
    if tamanho != info.file_size:
        parcial.unlink(missing_ok=True)
        raise ErroDownload(f"CSV extraído com {tamanho} bytes, esperado {info.file_size}")
    parcial.replace(destino)
    return tamanho


def extract(
    ano: int,
    mes: int,
    *,
    destino: Path = DIR_RAW,
    forcar: bool = False,
    manter_zip: bool = False,
    abrir_url: AbrirUrl = _abrir_url_padrao,
    dormir: Callable[[float], None] = time.sleep,
) -> Path:
    """Garante que o CSV de vacinação do mês está em `destino` e retorna o caminho dele.

    `forcar=True` baixa de novo mesmo com o arquivo em cache (o Ministério republica
    os arquivos quando há correções).
    """
    arquivo_csv = destino / nome_csv(ano, mes)
    arquivo_zip = destino / f"{arquivo_csv.stem}_csv.zip"
    periodo = f"{ano}-{mes:02d}"

    if forcar:
        arquivo_csv.unlink(missing_ok=True)
        arquivo_zip.unlink(missing_ok=True)

    if arquivo_csv.exists() and arquivo_csv.stat().st_size > 0:
        logger.info(
            kv(
                "extract_cache",
                periodo=periodo,
                arquivo=arquivo_csv.name,
                tamanho_bytes=arquivo_csv.stat().st_size,
            )
        )
        return arquivo_csv

    destino.mkdir(parents=True, exist_ok=True)
    if arquivo_zip.exists():
        logger.info(kv("extract_zip_em_cache", periodo=periodo, arquivo=arquivo_zip.name))
    else:
        url = url_zip(ano, mes)
        logger.info(kv("download_inicio", periodo=periodo, url=url))
        inicio = time.perf_counter()
        tamanho = baixar_com_retry(url, arquivo_zip, abrir_url=abrir_url, dormir=dormir)
        logger.info(
            kv(
                "download_fim",
                periodo=periodo,
                arquivo=arquivo_zip.name,
                tamanho_bytes=tamanho,
                tempo_s=round(time.perf_counter() - inicio, 1),
            )
        )

    inicio = time.perf_counter()
    tamanho_csv = descompactar_csv(arquivo_zip, arquivo_csv.name, arquivo_csv)
    logger.info(
        kv(
            "descompactar_fim",
            periodo=periodo,
            arquivo=arquivo_csv.name,
            tamanho_bytes=tamanho_csv,
            tempo_s=round(time.perf_counter() - inicio, 1),
        )
    )
    if not manter_zip:
        arquivo_zip.unlink()
    return arquivo_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Baixa os microdados de vacinação de um mês.")
    parser.add_argument("--ano", type=int, required=True)
    parser.add_argument("--mes", type=int, required=True)
    parser.add_argument("--forcar", action="store_true", help="ignora o cache e baixa de novo")
    args = parser.parse_args()

    configurar_logs()
    try:
        extract(args.ano, args.mes, forcar=args.forcar)
    except ErroDownload as erro:
        logger.error(kv("extract_falhou", ano=args.ano, mes=args.mes, motivo=erro))
        raise SystemExit(1) from erro


if __name__ == "__main__":
    main()
