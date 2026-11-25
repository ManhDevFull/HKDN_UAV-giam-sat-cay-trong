CREATE TABLE alerts (
    id               UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    survey_id        UUID NOT NULL REFERENCES surveys(id) ON DELETE RESTRICT,
    unit_id          UUID NOT NULL REFERENCES analysis_units(id) ON DELETE RESTRICT,
    alert_code       VARCHAR(100) UNIQUE NOT NULL,
    anomaly_type     VARCHAR(30) CHECK (anomaly_type IN ('absolute', 'spatial', 'temporal')),
    index_name       VARCHAR(30) NOT NULL,
    observed_value   DOUBLE PRECISION NOT NULL,
    reference_value  DOUBLE PRECISION,
    severity         VARCHAR(20) CHECK (severity IN ('low', 'medium', 'high')),
    priority_score   DOUBLE PRECISION NOT NULL,
    geometry         GEOMETRY(GEOMETRY, 4326) NOT NULL,
    status           VARCHAR(30) NOT NULL DEFAULT 'PENDING'
                     CHECK (status IN ('PENDING', 'ASSIGNED', 'INSPECTING', 'VERIFIED', 'DISMISSED')),
    reason           TEXT,
    created_at       TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_alerts_geometry ON alerts USING GIST (geometry);
CREATE INDEX idx_alerts_survey_id ON alerts (survey_id);
CREATE INDEX idx_alerts_unit_id ON alerts (unit_id);
CREATE INDEX idx_alerts_status ON alerts (status);
