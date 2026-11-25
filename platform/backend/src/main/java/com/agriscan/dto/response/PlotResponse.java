package com.agriscan.dto.response;

import com.fasterxml.jackson.databind.JsonNode;

import java.time.OffsetDateTime;
import java.util.UUID;

public record PlotResponse(
        UUID id,
        String name,
        String cropType,
        String ownerName,
        JsonNode boundary,
        Double areaM2,
        OffsetDateTime createdAt
) {
}
