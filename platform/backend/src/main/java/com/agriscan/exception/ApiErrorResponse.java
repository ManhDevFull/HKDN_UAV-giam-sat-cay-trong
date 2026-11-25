package com.agriscan.exception;

import java.time.OffsetDateTime;
import java.util.Map;

public record ApiErrorResponse(
        OffsetDateTime timestamp,
        int status,
        String error,
        String message,
        String path,
        Map<String, String> validationErrors
) {
    public ApiErrorResponse(int status, String error, String message, String path) {
        this(OffsetDateTime.now(), status, error, message, path, null);
    }

    public ApiErrorResponse(int status, String error, String message, String path, Map<String, String> validationErrors) {
        this(OffsetDateTime.now(), status, error, message, path, validationErrors);
    }
}
