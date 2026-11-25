package com.agriscan.dto.request;

import com.fasterxml.jackson.databind.JsonNode;
import jakarta.validation.constraints.NotBlank;
import jakarta.validation.constraints.NotNull;
import jakarta.validation.constraints.Positive;
import jakarta.validation.constraints.Size;

public record PlotRequest(
        @NotBlank(message = "Plot name is required")
        @Size(max = 150, message = "Plot name must not exceed 150 characters")
        String name,

        @NotBlank(message = "Crop type is required")
        @Size(max = 100, message = "Crop type must not exceed 100 characters")
        String cropType,

        @Size(max = 150, message = "Owner name must not exceed 150 characters")
        String ownerName,

        @NotNull(message = "Boundary GeoJSON Polygon is required")
        JsonNode boundary,

        @Positive(message = "Area must be positive")
        Double areaM2
) {
}
