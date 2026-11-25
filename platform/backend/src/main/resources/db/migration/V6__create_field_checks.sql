CREATE TABLE field_checks (
    id          UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    alert_id    UUID NOT NULL REFERENCES alerts(id) ON DELETE RESTRICT,
    inspector   VARCHAR(150) NOT NULL,
    checked_at  TIMESTAMPTZ NOT NULL,
    conclusion  VARCHAR(50) CHECK (conclusion IN ('NORMAL', 'WATER_STRESS', 'NUTRIENT_STRESS', 'PEST_OR_DISEASE_SUSPECTED', 'OTHER')),
    notes       TEXT,
    image_path  TEXT,
    location    GEOMETRY(POINT, 4326),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_field_checks_location ON field_checks USING GIST (location);
CREATE INDEX idx_field_checks_alert_id ON field_checks (alert_id);
