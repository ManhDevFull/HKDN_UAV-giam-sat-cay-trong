package com.agriscan.mapper;

import com.agriscan.dto.response.SurveyResponse;
import com.agriscan.entity.Survey;
import org.springframework.stereotype.Component;

@Component
public class SurveyMapper {

    public SurveyResponse toResponse(Survey survey) {
        return new SurveyResponse(
                survey.getId(),
                survey.getPlot().getId(),
                survey.getPlot().getName(),
                survey.getSurveyCode(),
                survey.getStartedAt(),
                survey.getEndedAt(),
                survey.getAcquisitionMethod(),
                survey.getOperator(),
                survey.getCameraModel(),
                survey.getCameraFilter(),
                survey.getProcessingStatus(),
                survey.getMetadataPath(),
                survey.getOrthomosaicPath(),
                survey.getNdviPath(),
                survey.getCreatedAt()
        );
    }
}
