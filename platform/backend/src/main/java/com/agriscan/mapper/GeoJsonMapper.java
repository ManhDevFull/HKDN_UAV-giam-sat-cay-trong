package com.agriscan.mapper;

import com.agriscan.exception.BadRequestException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import lombok.RequiredArgsConstructor;
import org.locationtech.jts.geom.*;
import org.springframework.stereotype.Component;

import java.util.ArrayList;
import java.util.List;

@Component
@RequiredArgsConstructor
public class GeoJsonMapper {

    public static final int SRID_WGS84 = 4326;
    private static final GeometryFactory GEOMETRY_FACTORY = new GeometryFactory(new PrecisionModel(), SRID_WGS84);

    private final ObjectMapper objectMapper;

    public Polygon toPolygon(JsonNode geoJson) {
        if (geoJson == null || geoJson.isNull()) {
            throw new BadRequestException("Boundary GeoJSON is required");
        }
        String type = geoJson.path("type").asText();
        if (!"Polygon".equalsIgnoreCase(type)) {
            throw new BadRequestException("Boundary GeoJSON type must be 'Polygon'");
        }
        JsonNode coordinatesNode = geoJson.path("coordinates");
        if (!coordinatesNode.isArray() || coordinatesNode.isEmpty()) {
            throw new BadRequestException("Polygon coordinates must be a non-empty array of linear rings");
        }

        LinearRing shell = toLinearRing(coordinatesNode.get(0));
        LinearRing[] holes = new LinearRing[coordinatesNode.size() - 1];
        for (int i = 1; i < coordinatesNode.size(); i++) {
            holes[i - 1] = toLinearRing(coordinatesNode.get(i));
        }

        Polygon polygon = GEOMETRY_FACTORY.createPolygon(shell, holes);
        polygon.setSRID(SRID_WGS84);
        if (!polygon.isValid()) {
            throw new BadRequestException("Invalid Polygon geometry");
        }
        return polygon;
    }

    public JsonNode toGeoJson(Polygon polygon) {
        if (polygon == null) {
            return null;
        }
        ObjectNode root = objectMapper.createObjectNode();
        root.put("type", "Polygon");

        ArrayNode rings = objectMapper.createArrayNode();
        rings.add(ringToArray(polygon.getExteriorRing()));
        for (int i = 0; i < polygon.getNumInteriorRing(); i++) {
            rings.add(ringToArray(polygon.getInteriorRingN(i)));
        }
        root.set("coordinates", rings);
        return root;
    }

    /**
     * Approximate geodesic area in square meters using spherical excess/local projection
     * as a fallback if PostGIS calculation is unavailable.
     */
    public double approximateAreaM2(Polygon polygon) {
        if (polygon == null || polygon.isEmpty()) {
            return 0.0;
        }
        Coordinate centroid = polygon.getCentroid().getCoordinate();
        double latRad = Math.toRadians(centroid.y);
        double metersPerDegLat = 111132.92 - 559.82 * Math.cos(2 * latRad) + 1.175 * Math.cos(4 * latRad);
        double metersPerDegLon = 111412.84 * Math.cos(latRad) - 93.5 * Math.cos(3 * latRad);
        return Math.abs(polygon.getArea()) * metersPerDegLat * metersPerDegLon;
    }

    private LinearRing toLinearRing(JsonNode ringNode) {
        if (!ringNode.isArray() || ringNode.size() < 4) {
            throw new BadRequestException("Polygon ring must contain at least 4 coordinate pairs");
        }
        List<Coordinate> coords = new ArrayList<>(ringNode.size());
        for (JsonNode point : ringNode) {
            if (!point.isArray() || point.size() < 2) {
                throw new BadRequestException("Each coordinate must be [longitude, latitude]");
            }
            double lon = point.get(0).asDouble();
            double lat = point.get(1).asDouble();
            coords.add(new Coordinate(lon, lat));
        }
        Coordinate first = coords.get(0);
        Coordinate last = coords.get(coords.size() - 1);
        if (!first.equals2D(last)) {
            coords.add(new Coordinate(first.x, first.y));
        }
        return GEOMETRY_FACTORY.createLinearRing(coords.toArray(new Coordinate[0]));
    }

    private ArrayNode ringToArray(LineString ring) {
        ArrayNode array = objectMapper.createArrayNode();
        for (Coordinate coord : ring.getCoordinates()) {
            ArrayNode pt = objectMapper.createArrayNode();
            pt.add(coord.x);
            pt.add(coord.y);
            array.add(pt);
        }
        return array;
    }
}
