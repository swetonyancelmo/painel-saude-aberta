-- Dimensão município (ver ADR-0002).
-- Idempotente: pode ser executado várias vezes.

CREATE TABLE IF NOT EXISTS municipio (
    id            integer PRIMARY KEY,          -- código IBGE de 7 dígitos (com dígito verificador)
    codigo_ibge6  integer NOT NULL UNIQUE,      -- código usado pelo DATASUS (sem dígito verificador)
    nome          text    NOT NULL,
    uf            char(2) NOT NULL,
    CONSTRAINT ck_municipio_codigo6 CHECK (codigo_ibge6 = id / 10)
);

COMMENT ON TABLE municipio IS 'Municípios segundo a API de localidades do IBGE.';
COMMENT ON COLUMN municipio.id IS 'Código IBGE de 7 dígitos.';
COMMENT ON COLUMN municipio.codigo_ibge6 IS 'Código de 6 dígitos (DATASUS), usado no join com os microdados.';
