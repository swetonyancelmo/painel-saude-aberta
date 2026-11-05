# CLAUDE.md — Painel Saúde Aberta

Guia para agentes de IA (Claude Code e similares) que trabalham neste repositório.
Leia este arquivo inteiro antes de escrever qualquer código.

---

## 1. O que é o projeto

Painel de indicadores de saúde pública construído com **dados abertos** do
OpenDataSUS / DATASUS. É um **projeto de portfólio** de um desenvolvedor
Fullstack Júnior: o código precisa ser legível, testado e fácil de explicar
numa entrevista. Clareza vale mais que esperteza.

Fluxo de dados:

```
OpenDataSUS (CSV)
      │
      ▼
 ETL em Python  ──►  testes de qualidade de dados
      │
      ▼
 PostgreSQL (dados agregados)
      │
      ▼
 API GraphQL (NestJS)
      │
      ▼
 Dashboard (Next.js) ──► filtro por município, gráficos, exportação PDF/XLSX
```

### Escopo do MVP (não expandir sem pedido explícito)

- **Base:** vacinação (SI-PNI), microdados anonimizados do OpenDataSUS.
- **Recorte:** estado de **Pernambuco (PE)**, ano de **2024**.
- **Indicador principal:** doses aplicadas por **município × vacina × mês**.

Só depois que a fatia vertical (ETL → banco → API → tela) estiver funcionando
de ponta a ponta é que se amplia o recorte (mais UFs, mais anos, outras bases).

---

## 2. Estrutura do repositório

```
painel-saude-aberta/
├── CLAUDE.md               ← este arquivo
├── README.md               ← apresentação para humanos (recrutadores)
├── docker-compose.yml      ← PostgreSQL local
├── .env.example            ← variáveis de ambiente (copiar para .env)
├── etl/                    ← pipeline em Python (projeto uv, pyproject.toml)
│   ├── src/painel_etl/     ← pacote Python (import painel_etl....)
│   │   ├── extract/        ← download (OpenDataSUS, API do IBGE)
│   │   ├── transform/      ← limpeza, filtro por UF, agregação, conversão de códigos
│   │   ├── load/           ← gravação idempotente no PostgreSQL
│   │   ├── quality/        ← checagens de qualidade de dados
│   │   └── carga_*.py      ← orquestradores de cada passo (python -m painel_etl.carga_...)
│   ├── tests/              ← pytest (unitários + qualidade + integração com o banco)
│   │   └── fixtures/       ← dados pequenos e estáticos para os testes
│   ├── notebooks/          ← exploração inicial (não é código de produção)
│   ├── sql/                ← DDL / migrations do schema
│   └── data/
│       ├── raw/            ← arquivos baixados (NUNCA versionar)
│       └── processed/      ← saídas intermediárias (NUNCA versionar)
├── api/                    ← NestJS + GraphQL (a ser gerado com Nest CLI)
├── web/                    ← Next.js (a ser gerado com create-next-app)
├── docs/
│   └── adr/                ← Architecture Decision Records
├── scripts/                ← utilitários de dev (seed, reset do banco etc.)
└── .github/workflows/      ← CI (GitHub Actions)
```

`api/` e `web/` estão vazios de propósito: devem ser gerados com as CLIs
oficiais (`npx @nestjs/cli new api` e `npx create-next-app@latest web`) para
manter a estrutura padrão de cada framework.

---

## 3. Stack e versões

| Camada | Tecnologia |
|---|---|
| ETL | Python 3.12+, pandas (ou polars), SQLAlchemy/psycopg, pytest |
| Banco | PostgreSQL 16 (via Docker) |
| API | Node 20+ LTS, NestJS, GraphQL (code-first, Apollo), TypeORM ou Prisma |
| Front | Next.js (App Router), TypeScript, uma lib de gráficos (Recharts ou similar) |
| Exportação | XLSX: `exceljs`; PDF: `@react-pdf/renderer` ou geração no servidor |
| CI | GitHub Actions |
| Deploy | Front na Vercel; API + Postgres no Railway |

Gerenciador de dependências Python: `uv` (preferido) ou `pip` + `venv`.
Gerenciador Node: `pnpm` (preferido) ou `npm`. Escolha um e mantenha.

---

## 4. Regras de domínio e dados (IMPORTANTE)

1. **Nunca grave microdados individuais no banco.** O ETL lê os microdados,
   agrega por município/vacina/mês e grava **apenas contagens**. Isso reduz o
   volume e é a decisão de privacidade do projeto (ver ADR-001).
2. **Arquivos são grandes** (~1,4 GB por mês nacional). Leia em *chunks* ou com
   leitura colunar, selecionando só as colunas necessárias. Filtre a UF o mais
   cedo possível.
3. **Município é identificado pelo código IBGE.** Atenção: o DATASUS costuma
   usar o código de **6 dígitos** (sem dígito verificador) e o IBGE o de **7**.
   Normalize e documente a escolha.
4. **Carga idempotente:** rodar o ETL duas vezes para o mesmo mês não pode
   duplicar dados. Use `UPSERT` (`ON CONFLICT ... DO UPDATE`) ou
   "apaga a partição do mês e regrava" dentro de uma transação.
5. **Qualidade de dados é obrigatória**, não opcional. Toda carga deve passar por:
   - contagem de linhas dentro de um intervalo esperado;
   - ausência de nulos nas colunas-chave (município, vacina, data);
   - ausência de duplicados na chave da tabela fato;
   - todo código de município existe na dimensão `municipio`;
   - datas dentro do período solicitado.
   Se uma checagem falhar, a carga **não acontece** e o erro é logado com detalhe.
6. **Não reaproveitar nada de empregadores ou clientes** (código, queries,
   nomes de tabela, regras de negócio). Este projeto é 100% autoral e público.

### Modelo de dados alvo (dimensional)

- `municipio` (dimensão): `id` = código IBGE de 7 dígitos, `codigo_ibge6` (DATASUS,
  usado no join com os microdados), nome, UF. Ver ADR-0002. Converter 6 ↔ 7 com
  `painel_etl.transform.codigo_municipio` (nunca só pelo algoritmo do dígito
  verificador: há exceções, como Quixaba-PE).
- `vacina` (dimensão): id, nome/descrição normalizada.
- `doses_mensais` (fato): municipio_id, vacina_id, ano_mes, total_doses.
  Chave única: (municipio_id, vacina_id, ano_mes).
- `etl_execucao` (controle): id, período, início, fim, status, linhas lidas,
  linhas gravadas, mensagem de erro.

Mudanças nesse modelo exigem um novo ADR.

---

## 5. Convenções de código

- **Idioma:** nomes de domínio em português (`municipio`, `doses_mensais`);
  termos técnicos em inglês quando é o padrão (`extract`, `resolver`, `service`).
  Comentários e documentação em português.
- **Python:** type hints em tudo, `ruff` para lint/format, funções pequenas e
  puras no `transform` (fáceis de testar). Sem `except:` genérico.
- **TypeScript:** `strict: true`, ESLint + Prettier, sem `any`.
- **Configuração:** tudo via variáveis de ambiente (`.env`). Nunca commitar
  segredos. Novas variáveis devem ser adicionadas ao `.env.example`.
- **Logs:** estruturados (JSON ou chave=valor), com o período processado e a
  contagem de linhas em cada etapa.
- **Commits:** Conventional Commits (`feat:`, `fix:`, `test:`, `docs:`, `chore:`).
  Commits pequenos e focados.

---

## 6. Como rodar (atualizar conforme as partes forem criadas)

```bash
cp .env.example .env
docker compose up -d          # sobe o PostgreSQL
# ETL (ambiente Python 3.12 gerenciado com uv, em etl/)
cd etl && uv sync             # cria .venv e instala o pacote painel_etl
uv run jupyter lab notebooks/ # exploração (01_exploracao.ipynb)
uv run ruff check . && uv run ruff format --check .
uv run pytest                 # testes marcados `integracao` são pulados sem o banco
uv run python -m painel_etl.carga_municipios --uf PE   # dimensão municipio (API do IBGE)
# Dados brutos: etl/data/raw/vacinacao_jan_2024.csv (latin-1, separador ';')
# ETL:  (a definir na Fase 1)  ex.: python -m etl.run --mes 2024-01 --uf PE
# API:  cd api && pnpm start:dev
# Web:  cd web && pnpm dev
```

---

## 7. Fases do projeto (ordem de trabalho)

0. **Esqueleto** — repositório, Docker, README. ✅ (estrutura criada)
1. **ETL** — exploração em notebook → script `extract/transform/load` → testes de qualidade.
2. **Modelagem + ADR** — schema SQL e ADR-001 (agregação vs. microdados; modelo dimensional).
3. **API GraphQL** — query `doses(municipio, vacina, periodo)`, paginação, DataLoader, testes de integração.
4. **Dashboard** — filtros, gráfico de série temporal, tabela, exportação XLSX e PDF.
5. **CI e deploy** — GitHub Actions, Vercel, Railway, ETL agendado mensalmente.

O quadro de tarefas detalhado está no Trello ("Painel Saúde Aberta").
Trabalhe **uma fase por vez** e não pule para a próxima sem a anterior funcionar.

---

## 8. Como o agente deve trabalhar aqui

- Antes de codar algo não trivial, descreva o plano em poucas linhas e espere
  confirmação se a mudança afetar o schema, a API pública ou o escopo.
- Escreva o teste junto com o código (especialmente no `transform` e no `quality`).
- Rode lint e testes antes de declarar algo pronto.
- Prefira soluções simples e "chatas" (*boring tech*). Nada de Kafka, Spark,
  microsserviços ou cache distribuído neste projeto.
- Não baixe dados reais em testes automatizados: use *fixtures* pequenas em
  `etl/tests/fixtures/`.
- Ao tomar uma decisão de arquitetura relevante, crie um ADR em `docs/adr/`
  usando o template `0000-template.md`.
- Atualize este CLAUDE.md quando comandos, estrutura ou convenções mudarem.

---

## 9. Fontes de dados

- OpenDataSUS: https://opendatasus.saude.gov.br/ (catálogo `dadosabertos.saude.gov.br`)
- Vacinação — registros individuais anonimizados (CSV), 2020 em diante.
- Códigos de municípios: IBGE (tabela de municípios / API de localidades).
- Biblioteca de apoio opcional: PySUS (`pysus`) para descoberta e download.

Respeite os termos de uso e cite as fontes no README e no rodapé do dashboard.
