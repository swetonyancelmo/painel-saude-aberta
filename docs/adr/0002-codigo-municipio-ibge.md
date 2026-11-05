# ADR-0002: Código de município — IBGE de 7 dígitos como chave, com o de 6 dígitos guardado

- **Status:** aceito
- **Data:** 2026-11-04

## Contexto
O IBGE identifica municípios com **7 dígitos** (2 da UF + 4 do município + 1 dígito
verificador). Os microdados do DATASUS usam só os **6 primeiros**, sem o dígito verificador
(confirmado na exploração de jan/2024: `co_municipio_estabelecimento` tem sempre 6 dígitos).

O dashboard e qualquer cruzamento com outras bases públicas (população, PIB, malhas do IBGE)
usam o código de 7 dígitos. O ETL precisa casar os dois formatos.

Ao validar com a API de localidades do IBGE (2026-11-04), descobrimos que o algoritmo
oficial do dígito verificador (módulo 10, pesos 1-2) **não reproduz 9 códigos do país**,
incluindo **Quixaba (PE, 2611533)**. Não há colisão: cada código de 6 dígitos corresponde a
exatamente um de 7.

## Decisão
A dimensão `municipio` usa o **código IBGE de 7 dígitos como chave primária (`id`)** e guarda
também o **código de 6 dígitos (`codigo_ibge6`, UNIQUE)** para o join com os microdados.
Um `CHECK (codigo_ibge6 = id / 10)` garante a consistência entre os dois.

A conversão em Python (`painel_etl.transform.codigo_municipio`) usa o algoritmo do dígito
verificador **mais uma tabela com as 9 exceções**. A carga da dimensão compara o resultado da
função com a lista oficial e aborta se divergir (avisa que a tabela de exceções precisa ser
atualizada).

A lista de municípios vem da API de localidades do IBGE, não do nome que aparece nos
microdados (que tem variações de grafia, ex.: "Belém de/do São Francisco").

## Alternativas consideradas
- **Guardar só o código de 6 dígitos** — mais simples para o ETL, mas obriga a converter
  em todo cruzamento com bases do IBGE e no front.
- **Guardar só o de 7 e converter no ETL** — exige a conversão 6 -> 7 correta em todo
  lugar; guardar os dois deixa o join um `JOIN ... ON codigo_ibge6` direto.
- **`id` serial separado + dois códigos UNIQUE** — um nível a mais de indireção sem ganho:
  o código do IBGE já é estável e único.
- **Calcular o DV só pelo algoritmo** — erra Quixaba em PE (e outros 8 municípios no país).

## Consequências
- `doses_mensais.municipio_id` guardará o código de 7 dígitos (ex.: Recife = 2611606),
  legível direto no banco.
- O modelo do CLAUDE.md ganha a coluna `municipio.codigo_ibge6`.
- Se o IBGE criar um município com DV fora da regra, a checagem de qualidade da carga
  falha e a tabela `EXCECOES_DV` precisa ser atualizada.
- PE tem 185 registros: 184 municípios + o distrito estadual de Fernando de Noronha
  (2605459), que o IBGE trata como município.
