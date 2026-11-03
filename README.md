# Painel Saúde Aberta

Painel de indicadores de vacinação construído com dados abertos do OpenDataSUS.

**Stack:** Python (ETL) · PostgreSQL · NestJS + GraphQL · Next.js

> 🚧 Em construção. Veja o andamento no quadro do Trello e as decisões em `docs/adr/`.

## Arquitetura

```
OpenDataSUS → ETL (Python) → PostgreSQL → API GraphQL (NestJS) → Dashboard (Next.js)
```

## Como rodar

```bash
cp .env.example .env
docker compose up -d
```

## Fontes de dados

- [OpenDataSUS](https://opendatasus.saude.gov.br/) — Ministério da Saúde
- IBGE — códigos de municípios
