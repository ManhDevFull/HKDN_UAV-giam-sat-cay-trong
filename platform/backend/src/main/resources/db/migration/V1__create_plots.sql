CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

CREATE TABLE plots (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    name        VARCHAR(150) NOT NULL,
    crop_type   VARCHAR(100) NOT NULL,
    owner_name  VARCHAR(150),
    boundary    GEOMETRY(POLYGON, 4326) NOT NULL,
    area_m2     DOUBLE PRECISION,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_plots_boundary ON plots USING GIST (boundary);
