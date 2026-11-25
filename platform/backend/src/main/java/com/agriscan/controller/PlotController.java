package com.agriscan.controller;

import com.agriscan.dto.request.PlotRequest;
import com.agriscan.dto.response.PlotResponse;
import com.agriscan.dto.response.SurveyResponse;
import com.agriscan.service.PlotService;
import com.agriscan.service.SurveyService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.data.domain.Page;
import org.springframework.data.domain.Pageable;
import org.springframework.data.domain.Sort;
import org.springframework.data.web.PageableDefault;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.List;
import java.util.UUID;

@RestController
@RequestMapping("/api/plots")
@RequiredArgsConstructor
public class PlotController {

    private final PlotService plotService;
    private final SurveyService surveyService;

    @GetMapping
    public ResponseEntity<Page<PlotResponse>> getPlots(
            @RequestParam(required = false) String keyword,
            @PageableDefault(size = 20, sort = "createdAt", direction = Sort.Direction.DESC) Pageable pageable
    ) {
        return ResponseEntity.ok(plotService.getPlots(keyword, pageable));
    }

    @PostMapping
    public ResponseEntity<PlotResponse> createPlot(@Valid @RequestBody PlotRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(plotService.createPlot(request));
    }

    @GetMapping("/{id}")
    public ResponseEntity<PlotResponse> getPlotById(@PathVariable UUID id) {
        return ResponseEntity.ok(plotService.getPlotById(id));
    }

    @PutMapping("/{id}")
    public ResponseEntity<PlotResponse> updatePlot(
            @PathVariable UUID id,
            @Valid @RequestBody PlotRequest request
    ) {
        return ResponseEntity.ok(plotService.updatePlot(id, request));
    }

    @DeleteMapping("/{id}")
    public ResponseEntity<Void> deletePlot(@PathVariable UUID id) {
        plotService.deletePlot(id);
        return ResponseEntity.noContent().build();
    }

    @GetMapping("/{id}/surveys")
    public ResponseEntity<List<SurveyResponse>> getPlotSurveys(@PathVariable UUID id) {
        return ResponseEntity.ok(surveyService.getSurveysByPlotId(id));
    }
}
