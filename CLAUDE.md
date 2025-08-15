# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

fairydust is a **mobile app backend** that powers a collection of AI-powered mini-apps using DUST (virtual currency) for AI operation costs. Provides microservices for user management, app marketplace, content storage, and DUST economy.

## Environment Variables

### Required API Keys
- `ANTHROPIC_API_KEY`: LLM provider for content generation
- `OPENAI_API_KEY`: LLM provider for content generation,
- `GOOGLE_PLACES_API_KEY`: Restaurant discovery (content service)
- `TRIPADVISOR_API_KEY`: Activity search (content service)

### HubSpot CRM Integration
- `ZAPIER_HUBSPOT_WEBHOOK`: Zapier webhook URL for syncing users to HubSpot
- `HUBSPOT_WEBHOOK_ENABLED`: Enable/disable HubSpot webhook (optional, default: true)

### Service Authentication
- `SERVICE_JWT_TOKEN`: JWT token for service-to-service authentication (apps → ledger)
  - Must be an admin user JWT token for ledger service operations
  - Used for referral/promotional code DUST grants
  - Falls back to user token if not set

## Commands

### Development Workflow
```bash
# Format code (ALWAYS before commit)
./scripts/format.sh

# Check code quality
./scripts/lint.sh

# Run tests
./test.sh

# Quick commit (auto-formats)
./scripts/commit.sh "your message"
```

### Git Workflow
- **Work on `develop` branch** → Auto-deploys to staging
- **Merge to `main` via PR** → Auto-deploys to production
- **NEVER commit directly to main**

### Admin Portal Deployment
```bash
# React app requires manual build/deploy EVERY TIME
cd services/admin-ui
npm run build
cp -r dist/* ../admin/static/
git add . && git commit -m "Update admin portal"
```

### CRITICAL DEPLOYMENT REMINDERS
⚠️ **Admin Portal Static Files**: The React admin UI builds to `dist/` but must be manually copied to `../admin/static/` and committed. If changes don't appear, check:
1. Did you run `npm run build`?
2. Did you copy with `cp -r dist/* ../admin/static/`?
3. Did you commit the static files with `git add ../admin/static/`?
4. Version number should be updated in 3 places: `package.json`, `main.py`, and `Sidebar.tsx`

⚠️ **Version Bumping**: Always increment version in ALL three files when making admin portal changes:
- `services/admin-ui/package.json` 
- `services/admin/main.py` 
- `services/admin-ui/src/components/layout/Sidebar.tsx`

### Environment Variables
```bash
# All Services
DATABASE_URL=postgresql://...
SERVICE_NAME=identity|content|apps|ledger|admin

# Optional
DB_POOL_MIN_SIZE=5
DB_POOL_MAX_SIZE=15
SKIP_SCHEMA_INIT=true  # admin service only
```

## Architecture

### Services
- **Identity** (8001): Auth, users, OAuth, OTP, progressive profiling
- **Ledger** (8002): DUST balance and transactions
- **Apps** (8003): App marketplace, LLM management
- **Admin** (8004): Admin dashboard
- **Content** (8006): User-generated content (recipes, stories, activities)

### Stack
- **FastAPI** + Pydantic validation
- **PostgreSQL** with UUID keys, JSONB metadata
- **Redis** for sessions, OTP, rate limiting
- **Railway** deployment (staging/production)

### Key Patterns
- JWT auth (1hr access, 30day refresh)
- DUST grants handled by apps, not identity service
- Environment-based service URLs (staging/production)
- Centralized utilities in `/shared/`
- Rate limiting: 15 recipes/hour, 5 stories/hour
- Raw SQL with asyncpg (no ORM)

## Content Service Apps

### Recipe App
- **Generate**: `POST /apps/recipe/generate` - Create new recipes
- **Adjust**: `POST /apps/recipe/adjust` - Modify existing recipes
- **List**: `GET /users/{user_id}/recipes` - Get user's recipes
- **Features**: Complexity levels, dietary restrictions, "People in My Life" personalization

### Story App  
- **Generate**: `POST /apps/story/generate` - Create personalized stories
- **Length options**: Short (2 DUST), Medium (4 DUST), Long (6 DUST)
- **Genres**: Adventure, Fantasy, Romance, Comedy, Mystery, Family, Bedtime
- **Features**: Character integration, target audience filtering

### Activity App
- **Search**: `POST /activity/search` - Find local activities
- **TripAdvisor integration** for attractions/destinations
- **AI-powered recommendations** with personalization
- **Cost**: 3 DUST per search

### Restaurant App
- **Generate**: `POST /restaurant/generate` - Find restaurant recommendations
- **Google Places integration** with OpenTable booking
- **Features**: Cuisine filtering, party size, special occasions

## Key Implementation Details

### LLM System
- **Providers**: Anthropic (primary), OpenAI (fallback)
- **Cost calculation**: Server-side only via `/shared/llm_pricing.py`
- **Usage logging**: All LLM calls logged with tokens, cost, latency
- **App configuration**: Per-app model selection and parameters via Admin Portal

### Service Communication
```python
# Environment-based URLs (NEVER hardcode production URLs)
environment = os.getenv('ENVIRONMENT', 'staging')
base_url_suffix = 'production' if environment == 'production' else 'staging'
ledger_url = f"https://fairydust-ledger-{base_url_suffix}.up.railway.app"
```

### Common Issues
- **PostgreSQL connections**: Use service-specific pool sizes
- **Admin Portal changes not visible**: Must rebuild React app and commit static files
- **JSON parsing errors**: Use `parse_jsonb_field()` for JSONB columns

## Docker & Python Library Management

### Docker Build System
fairydust uses **dual Dockerfile approach**:
- **Main Dockerfile** (`/Dockerfile`): Installs all service dependencies for multi-service deployment
- **Individual service Dockerfiles** (`services/*/Dockerfile`): Service-specific builds with Railway

### Critical Python Library Debugging Steps

When adding new Python packages to `requirements.txt`, common issues arise:

#### 1. **Docker Layer Caching Issues**
```dockerfile
# ALWAYS add cache-busting when adding new dependencies
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt
```

#### 2. **Package Import Path Debugging** 
Many packages install with different import paths than their package names:

```dockerfile
# Debug package installation and import paths
RUN echo "📦 Installed packages:" && pip list | grep <package-name>
RUN echo "🔍 Package files:" && find /usr/local/lib/python*/site-packages -name "*<package>*"
RUN python -c "import <package>; print('✅ Success')" || echo "❌ Import failed"
```

#### 3. **Common Import Path Gotchas**
- `uuid7` package → `from uuid_extensions import uuid7` (not `import uuid7`)
- Some packages have nested module structures different from package name
- Check actual file locations in site-packages to determine correct import

#### 4. **Verification Pattern**
```dockerfile
# Standard verification for new packages
RUN python -c "import <actual_import_path>; print('✅ <package> installed successfully')" || echo "❌ <package> failed to install"
```

#### 5. **Railway Build Debugging**
- Railway may use main Dockerfile OR individual service Dockerfiles
- Check `services/*/railway.json` for `dockerfilePath` configuration
- Build logs show which Dockerfile is actually being used
- Add debugging steps to both Dockerfiles when troubleshooting

#### Example Debug Session
```dockerfile
# Complete debugging template for new packages
RUN echo "🐍 Python version:" && python --version
RUN echo "📦 Target package:" && pip list | grep <package> || echo "Package not found"
RUN echo "📂 Python path:" && python -c "import sys; print('\n'.join(sys.path))"
RUN echo "🔍 Package files:" && find /usr/local/lib/python*/site-packages -name "*<package>*" 2>/dev/null || echo "No files found"
RUN python -c "from <correct_import_path> import <module>; print('✅ Import successful')" || echo "❌ Import failed"
```

### Best Practices
- Always run `./scripts/format.sh` before committing
- Use centralized utilities in `/shared/`
- Never accept DUST cost values from client APIs (server-side only)
- Environment-based service URLs for staging/production routing