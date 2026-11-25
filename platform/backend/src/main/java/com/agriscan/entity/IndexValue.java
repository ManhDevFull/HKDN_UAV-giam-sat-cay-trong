package com.agriscan.entity;

import jakarta.persistence.*;
import lombok.*;

import java.util.UUID;

@Entity
@Table(
        name = "index_values",
        uniqueConstraints = @UniqueConstraint(columnNames = {"survey_id", "unit_id", "index_name"})
)
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class IndexValue {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "survey_id", nullable = false)
    private Survey survey;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "unit_id", nullable = false)
    private AnalysisUnit unit;

    @Column(name = "index_name", length = 30, nullable = false)
    private String indexName;

    @Column(name = "mean_value")
    private Double meanValue;

    @Column(name = "median_value")
    private Double medianValue;

    @Column(name = "std_value")
    private Double stdValue;

    @Column(name = "min_value")
    private Double minValue;

    @Column(name = "max_value")
    private Double maxValue;

    @Column(name = "pixel_count")
    private Integer pixelCount;
}
