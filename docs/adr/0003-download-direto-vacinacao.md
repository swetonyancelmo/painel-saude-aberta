# ADR-0003: Download direto dos microdados de vacinação (sem PySUS)

- **Status:** aceito
- **Data:** 2026-11-04

## Contexto
O ETL precisa baixar, para um ano e mês, os microdados de vacinação (SI-PNI) do
OpenDataSUS. O CLAUDE.md sugeria o PySUS como biblioteca de apoio opcional.

O que verificamos em 2026-11-04:

- O dataset "Doses aplicadas pelo Programa Nacional de Imunizações (PNI) - 2024" aponta
  cada mês para um zip público no S3 do Ministério da Saúde:
  `https://s3.sa-east-1.amazonaws.com/ckan.saude.gov.br/PNI/csv/vacinacao_<mes>_<ano>_csv.zip`,
  com `<mes>` em `jan, fev, mar, abr, mai, jun, jul, ago, set, out, nov, dez`.
  Os 12 meses de 2024 (e jan/2025) respondem `200`, com zips de **1,1 a 4,4 GB**. Cada zip
  tem um único CSV (zip64, deflate), ex.: `vacinacao_jan_2024.csv` com ~7,3 GB.
- PySUS 2.11.7: a documentação não confirma suporte a esses microdados de 2024. O caminho
  mais próximo (`pysus.dadosgov.pni`) exige token do dados.gov.br. Instalar o PySUS
  **rebaixaria o pandas de 3.1 para 2.3.3** e adicionaria 38 pacotes (duckdb, boto3,
  fastparquet, sqlalchemy etc.), conforme `uv pip install --dry-run pysus`.

## Decisão
Baixar direto da URL do S3 com a biblioteca padrão do Python (`urllib`, `zipfile`), em
`painel_etl.extract.vacinacao.extract(ano, mes)`:

- cache pelo nome do arquivo em `etl/data/raw/` (CSV presente e não vazio = não baixa);
- download em streaming para `.part`, conferência do tamanho com o `Content-Length` e
  renomeação atômica. Arquivo com o nome final está sempre completo;
- retry com backoff exponencial (2 s, 4 s, 8 s) para erros de rede, 408, 429 e 5xx;
  outros status (ex.: 404) falham na hora com URL e status na mensagem;
- o zip é descompactado (tamanho conferido com o declarado no zip) e apagado.

## Alternativas consideradas
- **PySUS** — conflita com o pandas 3, traz dependências pesadas, exige token no caminho
  mais provável e não documenta suporte a esses arquivos. Ganho pequeno: o download é uma
  URL com padrão previsível.
- **`requests`/`httpx` + `tenacity` para o retry** — funcionaria, mas são 2 dependências
  para algo que cabe em ~40 linhas da biblioteca padrão, fáceis de testar e explicar.
- **Ler o CSV direto de dentro do zip, sem descompactar** — economiza ~7 GB de disco por mês,
  mas mistura extract com transform. Pode ser revisto se o disco virar problema.

## Consequências
- Sem dependências novas. Os testes substituem a função que abre a URL e não usam rede.
- A URL é hospedada pelo Ministério e pode mudar. Um 404 aparece no log com a URL exata.
- O cache é só por nome: se o Ministério republicar um mês com correções, é preciso rodar
  com `--forcar`. (O dataset é atualizado com frequência; vale comparar `Last-Modified`
  no futuro.)
- Cada mês ocupa de 1 a 4 GB para baixar e ~7 GB ou mais descompactado em `data/raw/`.
- Não há retomada de download interrompido (HTTP Range): uma falha recomeça o arquivo.
