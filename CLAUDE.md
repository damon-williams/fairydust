# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository..

## Commands

### Local Development
```bash
# With Docker (recommended)
docker-compose up

# Without Docker
cd services/identity
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
python main.py
```

### Testing
```bash
# Run all tests
./test.sh

# Run specific service tests
cd services/identity
PYTHONPATH=/Users/damonwilliams/Projects/fairydust pytest tests/ -v

# Run with coverage
pytest --cov=. --cov-report=term-missing

# Run specific test
pytest tests/test_auth.py::test_request_otp_email
```

### Deployment - CRITICAL GIT WORKFLOW

**🚨 NEVER COMMIT DIRECTLY TO MAIN BRANCH 🚨**

**Correct Git Workflow:**
1. **Always work on `develop` branch**
2. **Test in staging environment first** 
3. **Only merge to `main` via Pull Request after staging validation**

```bash
# Correct workflow:
git checkout develop          # Work on develop branch
git add .
git commit -m "feature"  
git push origin develop      # Deploy to staging via develop branch

# Test in staging environment thoroughly

# Only after staging approval:
# Create PR: develop → main (for production deployment)
```

**Branch Strategy:**
- `develop` → Staging environment (test everything here)
- `main` → Production environment (only via PR after staging approval)

**Railway Deployment:**
- Develop branch auto-deploys to: `*-staging.up.railway.app`
- Main branch auto-deploys to: `*-production.up.railway.app`

## Architecture Overview

fairydust is a microservices-based payment and identity platform for AI-powered applications using virtual currency called "DUST".

### Service Architecture
- **Identity Service** (port 8001): Authentication, user management, OAuth, OTP verification
- **Ledger Service** (port 8002): DUST balance tracking and transactions
- **Apps Service** (port 8003): App marketplace and consumption tracking
- **Admin Portal** (port 8004): Admin dashboard for user/app management
- **Builder Portal** (port 8005): Builder dashboard for app submission/management

### Shared Infrastructure
- **PostgreSQL**: Primary database with UUID keys, timestamps, and JSONB metadata
- **Redis**: Session management, OTP storage, token revocation
- **Shared utilities** (`/shared`): Database connections, Redis client, email service (Resend), SMS service (Twilio)

### Key Patterns

**Authentication Flow**:
1. Users can register/login with email OR phone (at least one required)
2. OTP verification via email (Resend) /SMS (Twilio) (10-minute expiry)
3. JWT access tokens (1-hour expiry) + refresh tokens (30-day expiry)
4. OAuth support for Google, Apple (partial), Facebook
5. Token revocation tracked in Redis

**User System**:
- Unique "fairynames" auto-generated: `{adjective}_{noun}_{4-digit-number}`
- New users receive 25 DUST initial grant
- Builder flag distinguishes app developers from regular users
- Balance tracked directly on user record (denormalized) + full history in dust_transactions

**Database Conventions**:
- All tables use UUID primary keys
- created_at/updated_at timestamps on all tables
- Foreign keys with CASCADE deletes
- Indexes on email, phone, fairyname, oauth provider IDs
- Raw SQL queries using asyncpg (no ORM)

**API Patterns**:
- FastAPI with Pydantic models for validation
- Dependency injection for DB/Redis connections
- Background tasks for email/SMS sending
- Health check endpoints for each service
- OpenAPI documentation at `/docs` and `/redoc`

## Development Notes

- Environment detection via `ENVIRONMENT` variable (development/production)
- SSL required for production database connections
- CORS configuration via `ALLOWED_ORIGINS` env var
- All configuration through environment variables
- Connection pooling with configurable min/max sizes
- Async/await patterns throughout the codebase