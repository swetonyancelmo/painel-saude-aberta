"""Checagens de qualidade da dimensão `municipio` (rodam antes de qualquer gravação)."""

from collections import Counter

from painel_etl.transform.codigo_municipio import codigo6_para_7
from painel_etl.transform.municipios import Municipio

# Total oficial por UF. PE: 184 municípios + o distrito estadual de Fernando de Noronha,
# que o IBGE trata como município (código 2605459).
TOTAL_ESPERADO_POR_UF: dict[str, int] = {"PE": 185}


def _duplicados(valores: list[str]) -> list[str]:
    return sorted(v for v, n in Counter(valores).items() if n > 1)


def checar_municipios(municipios: list[Municipio], uf: str) -> list[str]:
    """Retorna a lista de problemas encontrados. Lista vazia = pode carregar."""
    problemas: list[str] = []

    esperado = TOTAL_ESPERADO_POR_UF.get(uf)
    if esperado is None:
        problemas.append(f"total esperado de municípios não configurado para uf={uf}")
    elif len(municipios) != esperado:
        problemas.append(f"contagem={len(municipios)} esperado={esperado} uf={uf}")

    if dup := _duplicados([m.codigo_ibge7 for m in municipios]):
        problemas.append(f"codigo_ibge7 duplicado: {dup}")
    if dup := _duplicados([m.codigo_ibge6 for m in municipios]):
        problemas.append(f"codigo_ibge6 duplicado: {dup}")

    if outra_uf := sorted(m.codigo_ibge7 for m in municipios if m.uf != uf):
        problemas.append(f"municípios fora da uf={uf}: {outra_uf}")
    if sem_nome := sorted(m.codigo_ibge7 for m in municipios if not m.nome):
        problemas.append(f"municípios sem nome: {sem_nome}")

    # Garante que a conversão 6 -> 7 reproduz o código oficial. Se o IBGE criar um município
    # cujo DV foge do algoritmo, esta checagem avisa para atualizar EXCECOES_DV.
    if divergentes := sorted(
        m.codigo_ibge7 for m in municipios if codigo6_para_7(m.codigo_ibge6) != m.codigo_ibge7
    ):
        problemas.append(f"conversão 6->7 diverge do código oficial: {divergentes}")

    return problemas
