# AgriScan Platform — Backend (Spring Boot)

Dịch vụ REST API và Spatial Data Management cho dự án **AgriScan** (Nhóm C).

## Tech Stack
- Java 17+ / Spring Boot 3.x
- Spring Web, Spring Data JPA, Hibernate Spatial (JTS)
- PostgreSQL 16 + PostGIS 3.4 (SRID `4326`)
- Flyway Migrations (`src/main/resources/db/migration/`)

## Chạy cục bộ
1. Sao chép `.env.example` thành `.env` (hoặc export biến môi trường `DB_URL`, `DB_USERNAME`, `DB_PASSWORD`).
2. Đảm bảo PostgreSQL/PostGIS đang chạy (`docker compose up -d` tại `platform/`).
3. Chạy ứng dụng:
   ```bash
   mvn spring-boot:run
   ```
