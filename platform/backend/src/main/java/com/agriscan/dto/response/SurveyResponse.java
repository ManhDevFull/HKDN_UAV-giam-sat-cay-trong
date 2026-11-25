package com.agriscan.dto.response;

import java.time.OffsetDateTime;
import java.util.UUID;

public record SurveyResponse(
        UUID id,
        UUID plotId,
        String plotName,
        String surveyCode,
        OffsetDateTime startedAt,
        OffsetDateTime endedAt,
        String acquisitionMethod,
        String operator,
        String cameraModel,
        String cameraFilter,
        String processingStatus,
        String metadataPath,
        String orthomosaicPath,
        String ndviPath,
        OffsetDateTime createdAt
) {
}
