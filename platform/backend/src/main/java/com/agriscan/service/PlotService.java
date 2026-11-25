package com.agriscan.service;

import com.agriscan.dto.request.PlotRequest;
import com.agriscan.dto.response.PlotResponse;
import com.agriscan.entity.Plot;
import com.agriscan.exception.ConflictException;
import com.agriscan.exception.ResourceNotFoundException;
import com.agriscan.mapper.GeoJsonMapper;
import com.agriscan.mapper.PlotMapper;
import com.agriscan.repository.AnalysisUnitRepository;
import com.agriscan.repository.PlotRepository;
import com.agriscan.repository.SurveyRepository;
import jakarta.persistence.EntityManager;
import lombok.RequiredArgsConstructor;
import org.locationtech.jts.geom.Polygon;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.UUID;

@Service
@RequiredArgsConstructor
public class PlotService {

    private final PlotRepository plotRepository;
    private final SurveyRepository surveyRepository;
    private final AnalysisUnitRepository analysisUnitRepository;
    private final GeoJsonMapper geoJsonMapper;
    private final PlotMapper plotMapper;
    private final EntityManager entityManager;

    @Transactional(readOnly = true)
    public Page<PlotResponse> getPlots(String keyword, Pageable pageable) {
        return plotRepository.searchPlots(keyword, pageable)
                .map(plotMapper::toResponse);
    }

    @Transactional(readOnly = true)
    public PlotResponse getPlotById(UUID id) {
        Plot plot = findPlotOrThrow(id);
        return plotMapper.toResponse(plot);
    }

    @Transactional
    public PlotResponse createPlot(PlotRequest request) {
        Polygon boundary = geoJsonMapper.toPolygon(request.boundary());
        Double areaM2 = request.areaM2() != null
                ? request.areaM2()
                : calculateAreaM2(request.boundary().toString(), boundary);

        Plot plot = Plot.builder()
                .name(request.name().trim())
                .cropType(request.cropType().trim())
                .ownerName(request.ownerName() != null ? request.ownerName().trim() : null)
                .boundary(boundary)
                .areaM2(areaM2)
                .build();

        Plot saved = plotRepository.save(plot);
        return plotMapper.toResponse(saved);
    }

    @Transactional
    public PlotResponse updatePlot(UUID id, PlotRequest request) {
        Plot plot = findPlotOrThrow(id);
        Polygon boundary = geoJsonMapper.toPolygon(request.boundary());
        Double areaM2 = request.areaM2() != null
                ? request.areaM2()
                : calculateAreaM2(request.boundary().toString(), boundary);

        plot.setName(request.name().trim());
        plot.setCropType(request.cropType().trim());
        plot.setOwnerName(request.ownerName() != null ? request.ownerName().trim() : null);
        plot.setBoundary(boundary);
        plot.setAreaM2(areaM2);

        Plot saved = plotRepository.save(plot);
        return plotMapper.toResponse(saved);
    }

    @Transactional
    public void deletePlot(UUID id) {
        Plot plot = findPlotOrThrow(id);
        if (surveyRepository.existsByPlotId(id) || analysisUnitRepository.existsByPlotId(id)) {
            throw new ConflictException("Cannot delete plot because historical surveys or analysis units exist");
        }
        plotRepository.delete(plot);
    }

    private Plot findPlotOrThrow(UUID id) {
        return plotRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Plot not found with id: " + id));
    }

    private Double calculateAreaM2(String geoJsonString, Polygon fallbackPolygon) {
        try {
            Object result = entityManager
                    .createNativeQuery("SELECT ST_Area(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(:geojson), 4326), 32648))")
                    .setParameter("geojson", geoJsonString)
                    .getSingleResult();
            if (result instanceof Number number) {
                return Math.round(number.doubleValue() * 100.0) / 100.0;
            }
        } catch (Exception ignored) {
            // Fallback to local JTS approximation if PostGIS transform is unavailable
        }
        return Math.round(geoJsonMapper.approximateAreaM2(fallbackPolygon) * 100.0) / 100.0;
    }
}
