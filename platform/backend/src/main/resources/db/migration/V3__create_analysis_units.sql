CREATE TABLE analysis_units (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    plot_id       UUID NOT NULL REFERENCES plots(id) ON DELETE RESTRICT,
    unit_code     VARCHAR(100) NOT NULL,
    geometry      GEOMETRY(POLYGON, 4326) NOT NULL,
    center_point  GEOMETRY(POINT, 4326) NOT NULL,
    area_m2       DOUBLE PRECISION,
    UNIQUE (plot_id, unit_code)
);

CREATE INDEX idx_analysis_units_geometry ON analysis_units USING GIST (geometry);
CREATE INDEX idx_analysis_units_center_point ON analysis_units USING GIST (center_point);
