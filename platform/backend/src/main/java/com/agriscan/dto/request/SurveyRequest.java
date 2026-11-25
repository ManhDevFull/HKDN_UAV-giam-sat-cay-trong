package com.agriscan.dto.request;

import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Pattern;
import jakarta.validation.constraints.Size;

import java.time.OffsetDateTime;
import java.util.UUID;

public record SurveyRequest(
        @NotNull(message = "plotId is required")
        UUID plotId,

        @NotBlank(message = "surveyCode is required")
        @Size(max = 100, message = "surveyCode must not exceed 100 characters")
        String surveyCode,

        @NotNull(message = "startedAt is required")
        OffsetDateTime startedAt,

        OffsetDateTime endedAt,

        @NotBlank(message = "acquisitionMethod is required")
        @Pattern(
                regexp = "^(handheld|pole|fixed|drone)$",
                message = "acquisitionMethod must be one of: handheld, pole, fixed, drone"
        )
        String acquisitionMethod,

        @Size(max = 150, message = "operator must not exceed 150 characters")
        String operator,

        @Size(max = 100, message = "cameraModel must not exceed 100 characters")
        String cameraModel,

        @Size(max = 50, message = "cameraFilter must not exceed 50 characters")
        String cameraFilter,

        String metadataPath,
        String orthomosaicPath,
        String ndviPath
) {
}
