package com.agriscan.entity;

import jakarta.persistence.*;
import lombok.*;

import java.time.OffsetDateTime;
import java.util.UUID;

@Entity
@Table(name = "surveys")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Survey {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "plot_id", nullable = false)
    private Plot plot;

    @Column(name = "survey_code", length = 100, nullable = false, unique = true)
    private String surveyCode;

    @Column(name = "started_at", nullable = false)
    private OffsetDateTime startedAt;

    @Column(name = "ended_at")
    private OffsetDateTime endedAt;

    @Column(name = "acquisition_method", length = 30)
    private String acquisitionMethod;

    @Column(name = "operator", length = 150)
    private String operator;

    @Column(name = "camera_model", length = 100)
    private String cameraModel;

    @Column(name = "camera_filter", length = 50)
    private String cameraFilter;

    @Column(name = "processing_status", length = 30, nullable = false)
    @Builder.Default
    private String processingStatus = "PENDING";

    @Column(name = "metadata_path", columnDefinition = "TEXT")
    private String metadataPath;

    @Column(name = "orthomosaic_path", columnDefinition = "TEXT")
    private String orthomosaicPath;

    @Column(name = "ndvi_path", columnDefinition = "TEXT")
    private String ndviPath;

    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        if (processingStatus == null) {
            processingStatus = "PENDING";
        }
        if (createdAt == null) {
            createdAt = OffsetDateTime.now();
        }
    }
}
