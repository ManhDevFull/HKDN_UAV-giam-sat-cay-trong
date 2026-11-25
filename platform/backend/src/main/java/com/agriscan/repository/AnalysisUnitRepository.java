package com.agriscan.repository;

import com.agriscan.entity.AnalysisUnit;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface AnalysisUnitRepository extends JpaRepository<AnalysisUnit, UUID> {

    List<AnalysisUnit> findByPlotId(UUID plotId);

    boolean existsByPlotId(UUID plotId);
}
