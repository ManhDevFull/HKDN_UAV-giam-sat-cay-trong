package com.agriscan.entity;

import jakarta.persistence.*;
import lombok.*;
import org.locationtech.jts.geom.Point;
import org.locationtech.jts.geom.Polygon;

import java.util.UUID;

@Entity
@Table(
        name = "analysis_units",
        uniqueConstraints = @UniqueConstraint(columnNames = {"plot_id", "unit_code"})
)
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class AnalysisUnit {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "plot_id", nullable = false)
    private Plot plot;

    @Column(name = "unit_code", length = 100, nullable = false)
    private String unitCode;

    @Column(name = "geometry", nullable = false, columnDefinition = "geometry(Polygon,4326)")
    private Polygon geometry;

    @Column(name = "center_point", nullable = false, columnDefinition = "geometry(Point,4326)")
    private Point centerPoint;

    @Column(name = "area_m2")
    private Double areaM2;
}
