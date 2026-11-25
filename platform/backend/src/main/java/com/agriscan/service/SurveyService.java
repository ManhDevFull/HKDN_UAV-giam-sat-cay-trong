package com.agriscan.service;

import com.agriscan.dto.request.SurveyRequest;
import com.agriscan.dto.response.SurveyResponse;
import com.agriscan.entity.Plot;
import com.agriscan.entity.Survey;
import com.agriscan.exception.BadRequestException;
import com.agriscan.exception.ConflictException;
import com.agriscan.exception.ResourceNotFoundException;
import com.agriscan.mapper.SurveyMapper;
import com.agriscan.repository.PlotRepository;
import com.agriscan.repository.SurveyRepository;
import lombok.RequiredArgsConstructor;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;

import java.util.List;
import java.util.UUID;

@Service
@RequiredArgsConstructor
public class SurveyService {

    private final SurveyRepository surveyRepository;
    private final PlotRepository plotRepository;
    private final SurveyMapper surveyMapper;

    @Transactional(readOnly = true)
    public List<SurveyResponse> getSurveysByPlotId(UUID plotId) {
        if (!plotRepository.existsById(plotId)) {
            throw new ResourceNotFoundException("Plot not found with id: " + plotId);
        }
        return surveyRepository.findByPlotIdOrderByStartedAtDesc(plotId)
                .stream()
                .map(surveyMapper::toResponse)
                .toList();
    }

    @Transactional(readOnly = true)
    public SurveyResponse getSurveyById(UUID id) {
        Survey survey = surveyRepository.findById(id)
                .orElseThrow(() -> new ResourceNotFoundException("Survey not found with id: " + id));
        return surveyMapper.toResponse(survey);
    }

    @Transactional
    public SurveyResponse createSurvey(SurveyRequest request) {
        Plot plot = plotRepository.findById(request.plotId())
                .orElseThrow(() -> new ResourceNotFoundException("Plot not found with id: " + request.plotId()));

        String normalizedCode = request.surveyCode().trim();
        if (surveyRepository.existsBySurveyCode(normalizedCode)) {
            throw new ConflictException("Survey code already exists: " + normalizedCode);
        }

        if (request.endedAt() != null && request.endedAt().isBefore(request.startedAt())) {
            throw new BadRequestException("endedAt cannot be before startedAt");
        }

        Survey survey = Survey.builder()
                .plot(plot)
                .surveyCode(normalizedCode)
                .startedAt(request.startedAt())
                .endedAt(request.endedAt())
                .acquisitionMethod(request.acquisitionMethod())
                .operator(request.operator() != null ? request.operator().trim() : null)
                .cameraModel(request.cameraModel() != null ? request.cameraModel().trim() : null)
                .cameraFilter(request.cameraFilter() != null ? request.cameraFilter().trim() : null)
                .processingStatus("PENDING")
                .metadataPath(request.metadataPath())
                .orthomosaicPath(request.orthomosaicPath())
                .ndviPath(request.ndviPath())
                .build();

        Survey saved = surveyRepository.save(survey);
        return surveyMapper.toResponse(saved);
    }
}
