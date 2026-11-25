CREATE TABLE index_values (
    id            UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    survey_id     UUID NOT NULL REFERENCES surveys(id) ON DELETE RESTRICT,
    unit_id       UUID NOT NULL REFERENCES analysis_units(id) ON DELETE RESTRICT,
    index_name    VARCHAR(30) NOT NULL,
    mean_value    DOUBLE PRECISION,
    median_value  DOUBLE PRECISION,
    std_value     DOUBLE PRECISION,
    min_value     DOUBLE PRECISION,
    max_value     DOUBLE PRECISION,
    pixel_count   INTEGER,
    UNIQUE (survey_id, unit_id, index_name)
);

CREATE INDEX idx_index_values_survey_id ON index_values (survey_id);
CREATE INDEX idx_index_values_unit_id ON index_values (unit_id);
