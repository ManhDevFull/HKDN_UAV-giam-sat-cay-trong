package com.agriscan.repository;

import com.agriscan.entity.Plot;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.jpa.repository.JpaRepository;
import org.springframework.data.jpa.repository.Query;
import org.springframework.data.repository.query.Param;

import java.util.UUID;

public interface PlotRepository extends JpaRepository<Plot, UUID> {

    @Query("""
            SELECT p FROM Plot p
            WHERE (:keyword IS NULL OR :keyword = ''
                OR LOWER(p.name) LIKE LOWER(CONCAT('%', :keyword, '%'))
                OR LOWER(p.cropType) LIKE LOWER(CONCAT('%', :keyword, '%'))
                OR LOWER(COALESCE(p.ownerName, '')) LIKE LOWER(CONCAT('%', :keyword, '%')))
            """)
    Page<Plot> searchPlots(@Param("keyword") String keyword, Pageable pageable);
}
