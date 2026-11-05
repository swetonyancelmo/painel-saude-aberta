"""Conversão entre o código de município do IBGE (7 dígitos) e o do DATASUS (6 dígitos).

O IBGE identifica cada município com 7 dígitos: 2 da UF, 4 do município e 1 dígito
verificador (DV) no final. O DATASUS usa só os 6 primeiros, sem o DV.

- 7 -> 6: basta remover o último dígito.
- 6 -> 7: calcula-se o DV. O IBGE usa um algoritmo de módulo 10 com pesos 1 e 2
  alternados, mas 9 municípios do país não seguem a regra (incluindo Quixaba, em PE).
  Esses casos ficam numa tabela de exceções, conferida com a API de localidades do IBGE
  em 2026-11-04 (ver ADR-0002).
"""

PESOS_DV = (1, 2, 1, 2, 1, 2)

# Códigos oficiais cujo DV não segue o algoritmo: código de 6 dígitos -> código de 7.
EXCECOES_DV: dict[str, str] = {
    "220191": "2201919",  # Bom Princípio do Piauí (PI)
    "220198": "2201988",  # Brejo do Piauí (PI)
    "220225": "2202251",  # Canavieira (PI)
    "261153": "2611533",  # Quixaba (PE)
    "311783": "3117836",  # Cônego Marinho (MG)
    "315213": "3152131",  # Ponto Chique (MG)
    "430587": "4305871",  # Coronel Barros (RS)
    "520393": "5203939",  # Buriti de Goiás (GO)
    "520396": "5203962",  # Buritinópolis (GO)
}


def _validar(codigo: str, tamanho: int) -> None:
    if len(codigo) != tamanho or not codigo.isdigit():
        raise ValueError(f"código de município inválido: {codigo!r} (esperado {tamanho} dígitos)")


def digito_verificador(codigo6: str) -> str:
    """Calcula o DV pelo algoritmo do IBGE (sem considerar as exceções).

    Cada dígito é multiplicado pelo peso (1, 2, 1, 2, ...); quando o produto tem dois
    dígitos, eles são somados (ex.: 7 x 2 = 14 -> 1 + 4 = 5). O DV é o que falta para a
    soma chegar ao próximo múltiplo de 10.
    """
    _validar(codigo6, 6)
    soma = 0
    for digito, peso in zip(codigo6, PESOS_DV, strict=True):
        produto = int(digito) * peso
        soma += produto // 10 + produto % 10
    return str((10 - soma % 10) % 10)


def codigo7_para_6(codigo7: str) -> str:
    """Converte o código IBGE (7 dígitos) para o formato do DATASUS (6 dígitos)."""
    _validar(codigo7, 7)
    return codigo7[:6]


def codigo6_para_7(codigo6: str) -> str:
    """Converte o código do DATASUS (6 dígitos) para o código IBGE (7 dígitos)."""
    _validar(codigo6, 6)
    if codigo6 in EXCECOES_DV:
        return EXCECOES_DV[codigo6]
    return codigo6 + digito_verificador(codigo6)
