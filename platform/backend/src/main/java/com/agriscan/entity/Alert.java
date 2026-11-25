package com.agriscan.entity;

import jakarta.persistence.*;
import lombok.*;
import org.locationtech.jts.geom.Geometry;

import java.time.OffsetDateTime;
import java.util.UUID;

@Entity
@Table(name = "alerts")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Alert {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "survey_id", nullable = false)
    private Survey survey;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "unit_id", nullable = false)
    private AnalysisUnit unit;

    @Column(name = "alert_code", length = 100, nullable = false, unique = true)
    private String alertCode;

    @Column(name = "anomaly_type", length = 30)
    private String anomalyType;

    @Column(name = "index_name", length = 30, nullable = false)
    private String indexName;

    @Column(name = "observed_value", nullable = false)
    private Double observedValue;

    @Column(name = "reference_value")
    private Double referenceValue;

    @Column(name = "severity", length = 20)
    private String severity;

    @Column(name = "priority_score", nullable = false)
    private Double priorityScore;

    @Column(name = "geometry", nullable = false, columnDefinition = "geometry(Geometry,4326)")
    private Geometry geometry;

    @Column(name = "status", length = 30, nullable = false)
    @Builder.Default
    private String status = "PENDING";

    @Column(name = "reason", columnDefinition = "TEXT")
    private String reason;

    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        if (status == null) {
            status = "PENDING";
        }
        if (createdAt == null) {
            createdAt = OffsetDateTime.now();
        }
    }
}
