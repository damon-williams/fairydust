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

### Code Quality Checks
```bash
# Run linting (if configured)
npm run lint

# Run type checking (if configured)
npm run typecheck

# Python linting
ruff check .

# Format Python code
black .
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

### Environment Variables Configuration

**Where to set variables:**
1. **Railway Dashboard** → Select Service → Variables tab
2. **Local Development** → `.env` files in service directories
3. **Docker** → `docker-compose.yml` environment section

**Required Variables Per Service:**
```bash
# All Services
DATABASE_URL=postgresql://...
SERVICE_NAME=identity|content|apps|ledger|admin|builder

# Optional Pool Overrides (use defaults if not set)
DB_POOL_MIN_SIZE=5
DB_POOL_MAX_SIZE=15

# Production Only
SKIP_SCHEMA_INIT=true  # Set to true for admin/builder services
```

### Service URLs (Production)
- Identity: `https://fairydust-identity-production.up.railway.app`
- Ledger: `https://fairydust-ledger-production.up.railway.app`
- Apps: `https://fairydust-apps-production.up.railway.app`
- Admin: `https://fairydust-admin-production.up.railway.app`
- Builder: `https://fairydust-builder-production.up.railway.app`
- Content: `https://fairydust-content-production.up.railway.app`

## Architecture Overview

fairydust is a microservices-based payment and identity platform for AI-powered applications using virtual currency called "DUST".

### Service Architecture
- **Identity Service** (port 8001): Authentication, user management, OAuth, OTP verification, progressive profiling
- **Ledger Service** (port 8002): DUST balance tracking and transactions
- **Apps Service** (port 8003): App marketplace, LLM management, consumption tracking
- **Admin Portal** (port 8004): Admin dashboard for user/app/question/LLM management
- **Builder Portal** (port 8005): Builder dashboard for app submission/management
- **Content Service** (port 8006): User-generated content storage (recipes, stories)

### Shared Infrastructure
- **PostgreSQL**: Primary database with UUID keys, timestamps, and JSONB metadata
- **Redis**: Session management, OTP storage, token revocation, rate limiting
- **Shared utilities** (`/shared`):
  - Database connections with connection pooling
  - Redis client for caching and sessions
  - Email service (Resend)
  - SMS service (Twilio)
  - LLM pricing calculations
  - JSON parsing utilities
  - Streak calculation utilities

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
- Progressive profiling system to collect user preferences and personal information
- "People in My Life" feature for relationship context
- Daily login streaks with DUST rewards

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
- Centralized error handling and response formatting
- Rate limiting for API endpoints
- Request validation middleware

## Content Service

**Overview**: Dedicated microservice for user-generated content storage and management across all fairydust apps.

**Architecture**: Standalone service with domain-driven design, handling app-specific content with proper separation of concerns.

### Database Schema

**Table: `user_recipes`**
```sql
CREATE TABLE user_recipes (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    app_id VARCHAR(255) NOT NULL, -- 'fairydust-recipe', future: 'fairydust-inspire'
    title VARCHAR(500),
    content TEXT NOT NULL, -- Full recipe markdown content
    category VARCHAR(255), -- Dish name (e.g., "spaghetti carbonara")
    metadata JSONB DEFAULT '{}', -- Recipe parameters & additional data
    is_favorited BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

**Naming Convention for App-Specific Content:**
- Pattern: `{content_type}_{entity}` (e.g., `user_recipes`, `user_activities`)
- Use `app_id` field to distinguish between different apps
- Store app-specific data in JSONB `metadata` field for flexibility

### Service Details

**Port**: 8006  
**Base URL**: `https://content.fairydust.fun/recipes`  
**Health Check**: `/health`

### API Endpoints

- `GET /users/{user_id}/recipes` - Get user recipes with pagination/filtering
- `POST /users/{user_id}/recipes` - Save new recipe
- `PUT /users/{user_id}/recipes/{recipe_id}` - Update recipe (favorite, title)
- `DELETE /users/{user_id}/recipes/{recipe_id}` - Delete recipe
- `POST /users/{user_id}/recipes/sync` - Bulk sync for mobile apps

### Metadata Structure (JSONB)

```json
{
  "complexity": "Simple|Medium|Gourmet",
  "dish": "string",
  "include": "string",
  "exclude": "string", 
  "generation_params": {
    "model_used": "claude-3-5-sonnet-20241022",
    "dust_consumed": 3,
    "session_id": "string"
  },
  "parsed_data": {
    "prep_time": "string",
    "cook_time": "string", 
    "serves": "number",
    "nutrition": "string"
  }
}
```

### Security & Authorization

- Users can only access their own recipes (unless admin)
- JWT token validation via shared auth middleware
- Recipe content size limit: 10MB
- Proper error handling with standard HTTP codes

### Service Benefits

**Separation of Concerns**: Clear distinction between app lifecycle management (Apps Service) and content storage (Content Service)  
**Independent Scaling**: Content can scale independently based on storage and retrieval patterns  
**Dedicated Domain**: Focused on content management patterns, search, and user-generated data  
**Extensible Architecture**: Easy to add new content types for different apps  

### Story Generation Feature

**Table: `user_stories`**
```sql
CREATE TABLE user_stories (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    title VARCHAR(500) NOT NULL,
    content TEXT NOT NULL,
    genre VARCHAR(50) NOT NULL,
    story_length VARCHAR(20) NOT NULL,
    characters_involved JSONB NOT NULL,
    metadata JSONB DEFAULT '{}',
    dust_cost INTEGER NOT NULL,
    word_count INTEGER NOT NULL,
    is_favorited BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

**Story Generation System**:
- Personalized story generation with user's "People in My Life"
- Genre options: Adventure, Fantasy, Romance, Comedy, Mystery, Family, Bedtime
- Length options: Short (2 DUST), Medium (4 DUST), Long (6 DUST)
- Rate limiting: 5 stories per hour per user
- Content safety filtering based on target audience
- LLM-powered generation with cost tracking

### Future Extensions

This service can be extended for other apps:
- `fairydust-inspire`: Activity suggestions and user collections
- `smart-study-assistant`: Study materials and notes  
- Content sharing and collaboration features
- Advanced search and recommendation systems
- Content moderation and community features

### Integration with Other Services

- **Authentication**: Integrates with Identity Service for JWT validation
- **App Validation**: References Apps Service for app_id validation
- **Database**: Shares PostgreSQL instance with other services
- **Deployment**: Independent Railway service for dedicated scaling

## Apps Service - Enhanced Features

### App Submission & Approval
- **Auto-Approval**: New apps are automatically set to "Approved" status
- **No Manual Review Required**: Apps go live immediately upon submission
- **Status Workflow**: Created → Approved (skips Pending state)

### LLM Management

The Apps Service now includes comprehensive LLM management features:

### LLM Configuration
- **Model Selection**: Primary and fallback models per app
- **Provider Support**: Anthropic (Claude) and OpenAI (GPT)
- **Cost Tracking**: Server-side calculation using `/shared/llm_pricing.py`
- **Rate Limiting**: Per-app and per-user limits
- **Feature Flags**: App-specific feature toggles

### LLM Usage Logging
```sql
CREATE TABLE llm_usage_logs (
    id UUID PRIMARY KEY,
    user_id UUID NOT NULL,
    app_id VARCHAR(255) NOT NULL,
    model_used VARCHAR(255) NOT NULL,
    tokens_used INTEGER NOT NULL,
    cost_usd DECIMAL(10, 6) NOT NULL,
    latency_ms INTEGER,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
```

**Security Note**: Cost calculations are ALWAYS done server-side. Never accept cost values from client APIs.

## Progressive Profiling System

### User Profile Data
- **Dynamic Fields**: Store any type of user preference or personal data
- **Confidence Scoring**: Track data reliability (0.0 to 1.0)
- **Source Tracking**: Know where data came from (user_input, inferred, etc.)
- **App Context**: Associate data with specific apps

### People in My Life
- **Relationship Tracking**: Store family, friends, colleagues
- **Profile Data**: Attach preferences and details to each person
- **AI Context**: Generate personalized content based on relationships

### Question Management
- **Admin-Managed**: Questions created and managed via Admin Portal
- **Categories**: Organize questions by topic
- **DUST Rewards**: Incentivize user responses
- **Display Rules**: Control when/how questions appear

## Admin Portal Architecture

Recently refactored from a monolithic 2,448-line file into modular structure:

```
services/admin/routes/
├── auth.py          # Authentication & session management
├── dashboard.py     # Main dashboard with stats
├── users.py         # User management operations
├── apps.py          # App lifecycle management
├── questions.py     # Question management system
└── llm.py          # LLM configuration & analytics
```

Benefits:
- Improved maintainability and code organization
- Reduced memory footprint per module
- Easier debugging and testing
- Better separation of concerns

## Development Notes

- Environment detection via `ENVIRONMENT` variable (development/production)
- SSL required for production database connections
- CORS configuration via `ALLOWED_ORIGINS` env var
- All configuration through environment variables
- Connection pooling with configurable min/max sizes (reduced for admin service)
- Async/await patterns throughout the codebase
- JSON parsing centralized in `/shared/json_utils.py`
- LLM pricing centralized in `/shared/llm_pricing.py`
- Request validation centralized in `/shared/middleware.py`

## Centralized Middleware System

### Middleware Components
- **RequestValidationMiddleware**: Request size limits, content type validation, logging
- **SecurityHeadersMiddleware**: Security headers (X-Content-Type-Options, X-Frame-Options, etc.)
- **RequestSizeValidationMiddleware**: Endpoint-specific size limits
- **Standardized Error Handlers**: Consistent error response format across all services

### Implementation Pattern
```python
from shared.middleware import add_middleware_to_app

# Service-specific endpoint limits
endpoint_limits = {
    "/auth/otp/request": 1024,      # 1KB limit
    "/recipes": 10 * 1024 * 1024,   # 10MB limit
    "/stories/generate": 50 * 1024   # 50KB limit
}

add_middleware_to_app(
    app=app,
    service_name="identity",
    max_request_size=1 * 1024 * 1024,  # 1MB default
    endpoint_limits=endpoint_limits,
    log_requests=True
)
```

### Benefits
- **Consistent Error Responses**: Standardized format across all services
- **Security**: Automatic security headers and request validation
- **Logging**: Centralized request/response logging with timing
- **Performance**: Request size validation prevents oversized payloads
- **Maintainability**: Single source of truth for validation logic

### Standardized Error Response Format
```json
{
    "error": true,
    "message": "Validation error",
    "status_code": 422,
    "timestamp": 1640995200.0,
    "details": {...}
}
```

## Redis Caching Strategy

### App Configuration Caching
- **TTL**: 15 minutes for app configurations
- **Pattern**: Cache-aside with automatic invalidation
- **Implementation**: `/shared/app_config_cache.py`

### Caching Patterns Used
```python
from shared.app_config_cache import get_app_config_cache

# Try cache first, fallback to database
cache = await get_app_config_cache()
cached_config = await cache.get_model_config(app_id)

if cached_config:
    return cached_config
else:
    # Fetch from database and cache result
    config = await db.fetch_one("SELECT * FROM app_model_configs WHERE app_id = $1", app_id)
    await cache.set_model_config(app_id, config)
    return config
```

### Cache Invalidation
- **Update Operations**: Automatically invalidate cache on configuration updates
- **TTL Expiry**: 15-minute automatic expiration prevents stale data
- **Manual Invalidation**: Available for admin operations

### Benefits
- **40-60% reduction** in database queries for app configurations
- **Faster API responses** for story generation and admin operations
- **Better scaling** under high load
- **Graceful degradation** if cache is unavailable

## Performance Optimizations

### Recent Optimizations Implemented
1. **Database Query Optimization**: Replaced SELECT * with specific column selections
2. **JSON Parsing Centralization**: Reduced code duplication with shared utilities  
3. **Admin Portal Modularization**: Split 2,448-line file into focused modules
4. **Service-Specific Connection Pooling**: Optimized pool sizes per service usage patterns
5. **Redis Caching for App Configurations**: 15-minute TTL with cache invalidation
6. **Centralized Request Validation Middleware**: Standardized error handling and security

### Database Connection Pooling

**Service-Specific Pool Sizes:**
- **Identity Service**: min=5, max=15 (high frequency auth requests)
- **Content Service**: min=3, max=10 (fewer but longer story generation operations)  
- **Apps Service**: min=2, max=8 (moderate usage)
- **Ledger Service**: min=4, max=12 (frequent small transactions)
- **Admin/Builder**: min=1, max=3 (low usage, occasional access)

**Environment Variables:**
```bash
SERVICE_NAME=identity          # Determines default pool sizes
DB_POOL_MIN_SIZE=5            # Override minimum connections
DB_POOL_MAX_SIZE=15           # Override maximum connections
```

### Best Practices
- **Avoid SELECT ***: Always specify needed columns in queries
- **Use Centralized Utilities**: Leverage shared JSON parsing and pricing functions
- **Modular Route Files**: Keep route files focused and under 500 lines
- **Connection Management**: Use service-specific connection pool configurations
- **Caching Strategy**: Use Redis caching for frequently accessed configurations
- **Middleware Pattern**: Apply centralized validation and security middleware
- **Error Handling**: Use standardized error responses via shared middleware

## Common Issues and Solutions

### PostgreSQL "too many connections" Error
- **Cause**: Default connection pool sizes too high
- **Solution**: Reduce min_size and max_size in database.py per service needs
- **Prevention**: Monitor active connections and adjust pools accordingly

### Admin Portal Startup Hang
- **Cause**: Schema initialization conflict with other services
- **Solution**: Set `SKIP_SCHEMA_INIT=true` for admin service
- **Prevention**: Only one service should initialize database schema

### JSON Parsing Errors
- **Cause**: Inconsistent handling of JSONB fields from database
- **Solution**: Use centralized parsing functions in `/shared/json_utils.py`
- **Prevention**: Always use parse_jsonb_field() for database JSONB columns