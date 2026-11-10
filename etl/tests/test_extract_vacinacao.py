"""Testes do download de vacinação, sem rede: a função que abre URLs é substituída por um falso."""

import io
import urllib.error
import zipfile
from pathlib import Path

import pytest

from painel_etl.extract.vacinacao import (
    ErroDownload,
    baixar_com_retry,
    extract,
    nome_csv,
    url_zip,
)

CONTEUDO_CSV = b"co_documento;sg_uf_estabelecimento\nabc;PE\ndef;SP\n"


def zip_do_mes(nome: str = "vacinacao_jan_2024.csv", conteudo: bytes = CONTEUDO_CSV) -> bytes:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(nome, conteudo)
    return buffer.getvalue()


class RespostaFalsa(io.BytesIO):
    def __init__(self, corpo: bytes, content_length: int | None = None) -> None:
        super().__init__(corpo)
        self.status = 200
        self._tamanho = len(corpo) if content_length is None else content_length

    def getheader(self, nome: str) -> str | None:
        return str(self._tamanho) if nome == "Content-Length" else None


class AbrirUrlFalso:
    """Devolve, em ordem, cada item da lista: uma RespostaFalsa ou uma exceção a levantar."""

    def __init__(self, *roteiro: RespostaFalsa | Exception) -> None:
        self.roteiro = list(roteiro)
        self.urls: list[str] = []

    def __call__(self, url: str, timeout: float) -> RespostaFalsa:
        self.urls.append(url)
        item = self.roteiro.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


def http_error(status: int) -> urllib.error.HTTPError:
    return urllib.error.HTTPError("http://x", status, "erro", None, None)  # type: ignore[arg-type]


class Dormir:
    def __init__(self) -> None:
        self.esperas: list[float] = []

    def __call__(self, segundos: float) -> None:
        self.esperas.append(segundos)


# --- nomes e URLs -----------------------------------------------------------------------


def test_url_e_nome_do_arquivo() -> None:
    assert url_zip(2024, 1) == (
        "https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/PNI/csv/vacinacao_jan_2024_csv.zip"
    )
    assert nome_csv(2024, 12) == "vacinacao_dez_2024.csv"


@pytest.mark.parametrize(("ano", "mes"), [(2024, 0), (2024, 13), (2019, 5)])
def test_periodo_invalido(ano: int, mes: int) -> None:
    with pytest.raises(ValueError, match="inválido"):
        url_zip(ano, mes)


# --- extract: download e cache ----------------------------------------------------------


def test_extract_baixa_descompacta_e_apaga_o_zip(tmp_path: Path) -> None:
    abrir = AbrirUrlFalso(RespostaFalsa(zip_do_mes()))

    caminho = extract(2024, 1, destino=tmp_path, abrir_url=abrir)

    assert caminho == tmp_path / "vacinacao_jan_2024.csv"
    assert caminho.read_bytes() == CONTEUDO_CSV
    assert abrir.urls == [url_zip(2024, 1)]
    assert sorted(p.name for p in tmp_path.iterdir()) == ["vacinacao_jan_2024.csv"]


def test_segunda_chamada_nao_baixa_de_novo(tmp_path: Path) -> None:
    abrir = AbrirUrlFalso(RespostaFalsa(zip_do_mes()))

    primeira = extract(2024, 1, destino=tmp_path, abrir_url=abrir)
    segunda = extract(2024, 1, destino=tmp_path, abrir_url=abrir)

    assert primeira == segunda
    assert len(abrir.urls) == 1  # o roteiro só tinha uma resposta: outra chamada quebraria


def test_csv_ja_existente_nao_acessa_a_rede(tmp_path: Path) -> None:
    (tmp_path / "vacinacao_jan_2024.csv").write_bytes(CONTEUDO_CSV)
    abrir = AbrirUrlFalso()  # roteiro vazio: qualquer acesso à rede falharia

    extract(2024, 1, destino=tmp_path, abrir_url=abrir)

    assert abrir.urls == []


def test_csv_vazio_nao_conta_como_cache(tmp_path: Path) -> None:
    (tmp_path / "vacinacao_jan_2024.csv").write_bytes(b"")
    abrir = AbrirUrlFalso(RespostaFalsa(zip_do_mes()))

    caminho = extract(2024, 1, destino=tmp_path, abrir_url=abrir)

    assert caminho.read_bytes() == CONTEUDO_CSV


def test_zip_ja_baixado_so_descompacta(tmp_path: Path) -> None:
    (tmp_path / "vacinacao_jan_2024_csv.zip").write_bytes(zip_do_mes())
    abrir = AbrirUrlFalso()

    caminho = extract(2024, 1, destino=tmp_path, abrir_url=abrir)

    assert caminho.read_bytes() == CONTEUDO_CSV
    assert abrir.urls == []


def test_forcar_baixa_de_novo(tmp_path: Path) -> None:
    (tmp_path / "vacinacao_jan_2024.csv").write_bytes(b"versao antiga\n")
    abrir = AbrirUrlFalso(RespostaFalsa(zip_do_mes()))

    caminho = extract(2024, 1, destino=tmp_path, forcar=True, abrir_url=abrir)

    assert caminho.read_bytes() == CONTEUDO_CSV
    assert len(abrir.urls) == 1


# --- retry e erros ----------------------------------------------------------------------


def test_erros_temporarios_sao_repetidos_com_backoff(tmp_path: Path) -> None:
    abrir = AbrirUrlFalso(
        urllib.error.URLError("conexão recusada"),
        http_error(503),
        RespostaFalsa(zip_do_mes()),
    )
    dormir = Dormir()

    caminho = extract(2024, 1, destino=tmp_path, abrir_url=abrir, dormir=dormir)

    assert caminho.read_bytes() == CONTEUDO_CSV
    assert len(abrir.urls) == 3
    assert dormir.esperas == [2.0, 4.0]


def test_download_incompleto_e_repetido(tmp_path: Path) -> None:
    corpo = zip_do_mes()
    abrir = AbrirUrlFalso(
        RespostaFalsa(corpo[:10], content_length=len(corpo)),  # conexão caiu no meio
        RespostaFalsa(corpo),
    )

    tamanho = baixar_com_retry(
        "http://x/a.zip", tmp_path / "a.zip", abrir_url=abrir, dormir=Dormir()
    )

    assert tamanho == len(corpo)
    assert (tmp_path / "a.zip").read_bytes() == corpo


def test_404_falha_na_hora_com_url_e_status(tmp_path: Path) -> None:
    abrir = AbrirUrlFalso(http_error(404))
    dormir = Dormir()

    with pytest.raises(ErroDownload) as erro:
        extract(2024, 1, destino=tmp_path, abrir_url=abrir, dormir=dormir)

    assert url_zip(2024, 1) in str(erro.value)
    assert "status=404" in str(erro.value)
    assert dormir.esperas == []
    assert list(tmp_path.iterdir()) == []  # nenhum arquivo parcial fica para trás


def test_desiste_depois_de_todas_as_tentativas(tmp_path: Path) -> None:
    abrir = AbrirUrlFalso(*[http_error(500) for _ in range(4)])
    dormir = Dormir()

    with pytest.raises(ErroDownload, match="após 4 tentativas: status=500"):
        baixar_com_retry("http://x/a.zip", tmp_path / "a.zip", abrir_url=abrir, dormir=dormir)

    assert dormir.esperas == [2.0, 4.0, 8.0]
    assert list(tmp_path.iterdir()) == []
