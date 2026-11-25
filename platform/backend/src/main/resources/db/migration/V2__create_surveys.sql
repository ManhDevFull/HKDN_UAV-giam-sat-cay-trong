CREATE TABLE surveys (
    id                  UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    plot_id             UUID NOT NULL REFERENCES plots(id) ON DELETE RESTRICT,
    survey_code         VARCHAR(100) UNIQUE NOT NULL,
    started_at          TIMESTAMPTZ NOT NULL,
    ended_at            TIMESTAMPTZ,
    acquisition_method  VARCHAR(30) CHECK (acquisition_method IN ('handheld', 'pole', 'fixed', 'drone')),
    operator            VARCHAR(150),
    camera_model        VARCHAR(100),
    camera_filter       VARCHAR(50),
    processing_status   VARCHAR(30) NOT NULL DEFAULT 'PENDING'
                        CHECK (processing_status IN ('PENDING', 'PROCESSING', 'COMPLETED', 'FAILED')),
    metadata_path       TEXT,
    orthomosaic_path    TEXT,
    ndvi_path           TEXT,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX idx_surveys_plot_id ON surveys (plot_id);
