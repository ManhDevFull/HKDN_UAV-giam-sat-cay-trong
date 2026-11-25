package com.agriscan.repository;

import com.agriscan.entity.IndexValue;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface IndexValueRepository extends JpaRepository<IndexValue, UUID> {

    List<IndexValue> findBySurveyId(UUID surveyId);
}
