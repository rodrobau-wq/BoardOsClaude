-- 0001_extensions.sql — extensões necessárias
-- pgcrypto: gen_random_uuid()  | postgis: geolocalização de loja/concorrente
CREATE EXTENSION IF NOT EXISTS pgcrypto;
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS btree_gist;
