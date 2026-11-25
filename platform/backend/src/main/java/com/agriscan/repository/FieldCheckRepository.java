package com.agriscan.repository;

import com.agriscan.entity.FieldCheck;
import org.springframework.data.jpa.repository.JpaRepository;

import java.util.List;
import java.util.UUID;

public interface FieldCheckRepository extends JpaRepository<FieldCheck, UUID> {

    List<FieldCheck> findByAlertIdOrderByCheckedAtDesc(UUID alertId);
}
