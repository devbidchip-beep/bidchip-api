# BidChip API v2

Django REST API backend for the BidChip electronics surplus marketplace platform.

## Tech Stack

- Python 3.12 + Django 5.x
- Django REST Framework + drf-spectacular (OpenAPI docs)
- PostgreSQL 16
- Celery + Redis (async tasks)
- django-allauth (email authentication)
- django-otp (2FA, mandatory for staff)
- django-simple-history (audit trail on money/order models)
- django-fsm (order state machine)
- django-storages + boto3 (S3 file storage)
- Stripe (payments)
- Sentry (error tracking)

## Local Development Setup

### Prerequisites

- Python 3.12
- PostgreSQL 16
- Redis 7

### Setup

```bash
# Clone the repo
git clone https://github.com/devbidchip-beep/bidchip-api.git
cd bidchip-api

# Create and activate virtual environment
python3.12 -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate

# Install development dependencies
pip install -r requirements/dev.txt

# Copy environment file and configure
cp .env.example .env
# Edit .env with your local settings

# Run database migrations
python manage.py migrate

# Create a superuser
python manage.py createsuperuser

# Start the development server
python manage.py runserver
```

### Running Tests

```bash
pytest
# With coverage:
pytest --cov=. --cov-report=html
```

### Linting

```bash
ruff check .
ruff format .
```

## Docker Setup

```bash
# Copy and configure environment file
cp .env.example .env

# Build and start all services
docker compose up --build

# Run migrations inside the web container
docker compose exec web python manage.py migrate

# Create superuser
docker compose exec web python manage.py createsuperuser
```

Services available:
- API: http://localhost:8000
- API Docs (Swagger): http://localhost:8000/api/schema/swagger-ui/
- API Docs (ReDoc): http://localhost:8000/api/schema/redoc/
- Admin: http://localhost:8000/admin/

## Project Structure

```
bidchip-api/
├── config/          # Django project configuration
│   ├── settings/    # Environment-specific settings (base/dev/prod)
│   ├── urls.py      # Root URL configuration
│   ├── celery.py    # Celery application
│   └── wsgi.py      # WSGI entry point
├── accounts/        # User, Company, and authentication models
├── core/            # Platform settings, audit events, business calendar
├── requirements/    # Pinned dependencies per environment
└── .github/         # CI/CD workflows
```

## Environment Variables

See `.env.example` for all required environment variables.

## API Documentation

Once running, OpenAPI docs are available at:
- Swagger UI: `/api/schema/swagger-ui/`
- ReDoc: `/api/schema/redoc/`
- Raw schema: `/api/schema/`
