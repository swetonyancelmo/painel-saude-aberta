"""Logs estruturados no formato chave=valor."""

import logging


def configurar_logs() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s nivel=%(levelname)s modulo=%(name)s %(message)s",
    )


def kv(evento: str, **campos: object) -> str:
    """Monta a mensagem `evento=... chave=valor ...` (valores com espaço vão entre aspas)."""
    partes = [f"evento={evento}"]
    for chave, valor in campos.items():
        texto = str(valor)
        partes.append(f'{chave}="{texto}"' if " " in texto else f"{chave}={texto}")
    return " ".join(partes)
