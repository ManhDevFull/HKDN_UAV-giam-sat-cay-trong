package com.agriscan.entity;

import jakarta.persistence.*;
import lombok.*;
import org.locationtech.jts.geom.Point;

import java.time.OffsetDateTime;
import java.util.UUID;

@Entity
@Table(name = "field_checks")
@Getter
@Setter
@NoArgsConstructor
@AllArgsConstructor
@Builder
public class FieldCheck {

    @Id
    @GeneratedValue(strategy = GenerationType.UUID)
    private UUID id;

    @ManyToOne(fetch = FetchType.LAZY, optional = false)
    @JoinColumn(name = "alert_id", nullable = false)
    private Alert alert;

    @Column(name = "inspector", length = 150, nullable = false)
    private String inspector;

    @Column(name = "checked_at", nullable = false)
    private OffsetDateTime checkedAt;

    @Column(name = "conclusion", length = 50)
    private String conclusion;

    @Column(name = "notes", columnDefinition = "TEXT")
    private String notes;

    @Column(name = "image_path", columnDefinition = "TEXT")
    private String imagePath;

    @Column(name = "location", columnDefinition = "geometry(Point,4326)")
    private Point location;

    @Column(name = "created_at", nullable = false, updatable = false)
    private OffsetDateTime createdAt;

    @PrePersist
    protected void onCreate() {
        if (createdAt == null) {
            createdAt = OffsetDateTime.now();
        }
    }
}
