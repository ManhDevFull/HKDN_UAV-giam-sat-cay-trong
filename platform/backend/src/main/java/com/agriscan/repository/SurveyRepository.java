package com.agriscan.repository;

import com.agriscan.entity.Survey;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface SurveyRepository extends JpaRepository<Survey, UUID> {

    List<Survey> findByPlotIdOrderByStartedAtDesc(UUID plotId);

    boolean existsByPlotId(UUID plotId);

    boolean existsBySurveyCode(String surveyCode);
}
