package com.agriscan.controller;

import com.agriscan.dto.request.SurveyRequest;
import com.agriscan.dto.response.SurveyResponse;
import com.agriscan.service.SurveyService;
import jakarta.validation.Valid;
import lombok.RequiredArgsConstructor;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.bind.annotation.*;

import java.util.UUID;

@RestController
@RequestMapping("/api/surveys")
@RequiredArgsConstructor
public class SurveyController {

    private final SurveyService surveyService;

    @PostMapping
    public ResponseEntity<SurveyResponse> createSurvey(@Valid @RequestBody SurveyRequest request) {
        return ResponseEntity.status(HttpStatus.CREATED).body(surveyService.createSurvey(request));
    }

    @GetMapping("/{id}")
    public ResponseEntity<SurveyResponse> getSurveyById(@PathVariable UUID id) {
        return ResponseEntity.ok(surveyService.getSurveyById(id));
    }
}
