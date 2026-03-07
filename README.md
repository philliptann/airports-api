# OurAirports Django API (Docker)

Django + DRF + Postgres, with:
- Import OurAirports `airports.csv` and `runways.csv`
- Admin CSV import/export via `django-import-export`
- API endpoints for airports, runways, and runway **thresholds**
- OpenAPI schema + Swagger UI via `drf-spectacular`

## Quick start

1) Copy env file

```bash
cp .env.example .env
```

2) Build + run

```bash
docker compose up --build
```

3) Create DB tables (runs automatically on container start), then import OurAirports:

```bash
docker compose exec web python manage.py import_ourairports
```

4) Browse API

- http://localhost:8000/api/airports/
- http://localhost:8000/api/runways/
- http://localhost:8000/api/thresholds/
- http://localhost:8000/api/airports/EGLL/thresholds/
- http://localhost:8000/api/runways/?airport_ident=EGLL

5) API docs

- Swagger UI: http://localhost:8000/api/docs/
- OpenAPI JSON: http://localhost:8000/api/schema/

## Admin
Create a superuser:
```bash
docker compose exec web python manage.py createsuperuser
```
Admin at:
- http://localhost:8000/admin/

The Airport and Runway models have import/export buttons in the admin.
