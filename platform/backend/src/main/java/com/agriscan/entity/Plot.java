package com.agriscan.entity;

import jakarta.persistence.*;
import lombok.*;
import org.locationtech.jts.geom.Polygon;

import java.time.OffsetDateTime;
import java.util.UUID;

@Entity
@Table(name = "plots")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class Plot {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @Column(name = "name", length = 150, nullable = false)
    private String name;

    @Column(name = "crop_type", length = 100, nullable = false)
    private String cropType;

    @Column(name = "owner_name", length = 150)
    private String ownerName;

    @Column(name = "boundary", nullable = false, columnDefinition = "geometry(Polygon,4326)")
    private Polygon boundary;

    @Column(name = "area_m2")
    private Double areaM2;

    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        if (createdAt == null) {
            createdAt = OffsetDateTime.now();
        }
    }
}
