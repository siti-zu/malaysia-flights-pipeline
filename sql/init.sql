-- Runs once, the first time the Postgres container creates the database.
-- Creates the raw layer: data stored exactly as OpenSky returned it.

CREATE SCHEMA IF NOT EXISTS raw;

-- One row per flight returned by an API call.
-- The loader deletes and re-inserts one airport + direction + date at a time,
-- so re-running the same day never creates duplicates.
CREATE TABLE IF NOT EXISTS raw.flights (
    id          BIGSERIAL PRIMARY KEY,
    run_id      UUID        NOT NULL,          -- ingestion run that loaded this row; set by main.py, no default so a missing ID fails loudly
    airport     TEXT        NOT NULL,          -- ICAO code queried, e.g. WMKK
    direction   TEXT        NOT NULL CHECK (direction IN ('arrival', 'departure')),
    query_date  DATE        NOT NULL,          -- the UTC day that was requested
    payload     JSONB       NOT NULL,          -- the flight object, untouched
    _loaded_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_raw_flights_partition
    ON raw.flights (airport, direction, query_date);

-- One row per API call, for monitoring and debugging.
CREATE TABLE IF NOT EXISTS raw.api_runs (
    id            BIGSERIAL PRIMARY KEY,
    run_id        UUID        NOT NULL,        -- groups every call made by one ingestion run
    airport       TEXT        NOT NULL,
    direction     TEXT        NOT NULL CHECK (direction IN ('arrival', 'departure')),
    query_date    DATE        NOT NULL,
    status_code   INTEGER,                     -- HTTP status, e.g. 200, 404, 429
    row_count     INTEGER,                     -- flights returned
    credits_left  INTEGER,                     -- from X-Rate-Limit-Remaining header
    error_message TEXT,
    run_at        TIMESTAMPTZ NOT NULL DEFAULT now()
);