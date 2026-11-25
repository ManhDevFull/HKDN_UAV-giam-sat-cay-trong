package com.agriscan.mapper;

import com.agriscan.dto.response.PlotResponse;
import com.agriscan.entity.Plot;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Component;

@Component
@RequiredArgsConstructor
public class PlotMapper {

    private final GeoJsonMapper geoJsonMapper;

    public PlotResponse toResponse(Plot plot) {
        return new PlotResponse(
                plot.getId(),
                plot.getName(),
                plot.getCropType(),
                plot.getOwnerName(),
                geoJsonMapper.toGeoJson(plot.getBoundary()),
                plot.getAreaM2(),
                plot.getCreatedAt()
        );
    }
}
