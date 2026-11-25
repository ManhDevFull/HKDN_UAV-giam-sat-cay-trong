package com.agriscan.repository;

import com.agriscan.entity.Alert;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface AlertRepository extends JpaRepository<Alert, UUID> {

    List<Alert> findBySurveyId(UUID surveyId);

    List<Alert> findByStatus(String status);
}
