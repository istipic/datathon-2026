-- One PostgreSQL server, three databases (one per app).
-- Runs once on first initialisation of the data volume (psql, so \connect works).

CREATE DATABASE blizu;
CREATE DATABASE otporno;
CREATE DATABASE nabavaradar;

\connect blizu
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;

\connect otporno
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;

\connect nabavaradar
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS vector;
