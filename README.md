# ✨ Fairydust Platform

A comprehensive microservices backend platform powering AI-enabled mobile applications with a virtual currency economy (DUST). Built for scalability, modularity, and seamless integration with modern mobile apps.

## 🏗️ Architecture Overview

Fairydust is a **microservices-based platform** that provides the backend infrastructure for AI-powered mobile applications. Each service handles a specific domain:

```
🏦 Identity Service (8001)    → Authentication, User Management, OAuth/OTP
💰 Ledger Service (8002)      → DUST Transactions, Balance Management  
📱 Apps Service (8003)        → App Marketplace, LLM Configuration
👨‍💼 Admin Portal (8004)       → Management Dashboard, Analytics
🔨 Builder Portal (8005)      → App Developer Tools
📝 Content Service (8006)     → User-Generated Content, Stories, Recipes
```

### Key Features

- 🔐 **Multi-modal Authentication** - OAuth (Google, Apple, Facebook), OTP via Email/SMS
- 💎 **DUST Economy** - Virtual currency system with action-based pricing
- 🤖 **LLM Integration** - Configurable AI models (Anthropic Claude, OpenAI GPT)
- 📊 **Real-time Analytics** - Usage tracking, cost management, performance metrics
- 🏪 **App Marketplace** - Developer portal with auto-approval workflows
- 👥 **Progressive Profiling** - Smart user data collection and relationship management
- 🌍 **External Integrations** - TripAdvisor, Google Places, Maps APIs

## 🚀 Quick Start

### Prerequisites

- **Python 3.11+**
- **PostgreSQL 16+** 
- **Redis 7+**
- **Node.js 18+** (for Admin UI)
- **Docker & Docker Compose** (recommended)

### 🐳 Docker Development (Recommended)

```bash
# Clone and setup
git clone <repository-url>
cd fairydust

# Create environment file
cp .env.example .env
# Edit .env with your configuration

# Start all services
docker-compose up

# Services will be available at:
# Identity: http://localhost:8001
# Ledger: http://localhost:8002  
# Apps: http://localhost:8003
# Admin: http://localhost:8004
# Builder: http://localhost:8005
# Content: http://localhost:8006
```

### 🔧 Manual Development Setup

```bash
# Install Python dependencies
cd services/identity
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Setup database and Redis locally
# Edit .env with your database/Redis URLs

# Run identity service
python main.py

# In separate terminals, repeat for other services
```

### 🎨 Admin UI Development

```bash
cd services/admin-ui
npm install
npm run dev  # Development server
npm run build  # Production build
```

## 🔑 Environment Configuration

### Required API Keys

```bash
# AI/LLM Services
ANTHROPIC_API_KEY=sk-ant-...          # Claude AI integration
OPENAI_API_KEY=sk-...                 # OpenAI GPT integration

# External APIs  
GOOGLE_PLACES_API_KEY=AIza...         # Restaurant/location data
TRIPADVISOR_API_KEY=...               # Activity recommendations

# Authentication
JWT_SECRET_KEY=your-super-secret-key  # Must be secure!
GOOGLE_CLIENT_ID=...                  # OAuth login
APPLE_CLIENT_ID=...                   # OAuth login  
FACEBOOK_CLIENT_ID=...                # OAuth login

# Communication
RESEND_API_KEY=re_...                 # Email service (OTP, notifications)
TWILIO_ACCOUNT_SID=AC...              # SMS service (OTP)
TWILIO_AUTH_TOKEN=...                 # SMS authentication
TWILIO_PHONE_NUMBER=+1...             # SMS sender number

# Database & Cache
DATABASE_URL=postgresql://user:pass@host:port/db
REDIS_URL=redis://localhost:6379/0
```

### Service-Specific Configuration

```bash
# Service identification
SERVICE_NAME=identity|ledger|apps|admin|builder|content

# Production settings
ENVIRONMENT=development|staging|production
SKIP_SCHEMA_INIT=true  # Set for admin/builder services
```

## 📊 API Documentation

Each service provides interactive API documentation:

- **Identity Service**: http://localhost:8001/docs
- **Ledger Service**: http://localhost:8002/docs  
- **Apps Service**: http://localhost:8003/docs
- **Content Service**: http://localhost:8006/docs

### Core API Endpoints

```bash
# Authentication
POST /auth/otp/request              # Request OTP
POST /auth/otp/verify               # Verify OTP + login
POST /auth/oauth/{provider}         # OAuth callback
POST /auth/refresh                  # Refresh tokens

# User Management  
GET  /users/me                      # Get user profile
PATCH /users/me                     # Update profile
GET  /users/{id}/people             # Get "people in my life"
POST /users/{id}/people             # Add person

# DUST Economy
GET  /balance/{user_id}             # Get DUST balance
POST /transactions/consume          # Consume DUST
POST /grants/app-initial            # Grant initial DUST
POST /grants/app-streak             # Daily streak bonus

# Content & Apps
POST /apps/story/generate           # Generate AI story
POST /apps/recipe/generate          # Generate recipe
POST /activity/search               # Find activities
GET  /apps                          # List apps
```

## 🚢 Deployment

### Railway Deployment (Production)

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and setup
railway login
railway init

# Deploy services
railway up

# Configure environment variables in Railway dashboard
# Set all required API keys and database URLs
```

### Environment URLs

**Staging** (develop branch):
- Identity: `https://fairydust-identity-staging.up.railway.app`
- Admin: `https://fairydust-admin-staging.up.railway.app`
- Content: `https://fairydust-content-staging.up.railway.app`

**Production** (main branch):
- Identity: `https://fairydust-identity-production.up.railway.app`
- Admin: `https://fairydust-admin-production.up.railway.app`
- Content: `https://fairydust-content-production.up.railway.app`

## 🧪 Testing

### Run Tests

```bash
# All tests
./test.sh

# Service-specific tests
cd services/identity
PYTHONPATH=/Users/$(whoami)/Projects/fairydust pytest tests/ -v

# With coverage
pytest --cov=. --cov-report=term-missing

# Specific test file
pytest tests/test_auth.py::test_request_otp_email
```

### Test Configuration

- **Test Database**: `fairydust_test`
- **Test Redis**: `redis://localhost:6379/1`  
- **Markers**: `unit`, `integration`, `api`, `e2e`, `slow`

## 🔧 Development Workflow

### Code Quality (Mandatory)

```bash
# ALWAYS run before committing
./scripts/format.sh          # Auto-format code (black + ruff)
./scripts/lint.sh            # Check code quality  
pytest tests/               # Run tests
git add . && git commit     # Commit formatted code
```

### Git Workflow (Critical)

```bash
# ⚠️ NEVER commit directly to main!
git checkout develop        # Work on develop branch
# ... make changes ...
git push origin develop     # Deploy to staging

# After staging approval:
# Create PR: develop → main (for production)
```

### Custom Commands

Use the included Claude Code commands for streamlined development:

```bash
/project:generate-pr        # Create full PR workflow
/project:format-and-commit  # Format + commit changes
/project:rebuild-admin      # Rebuild React admin portal  
/project:test-endpoints     # Test API endpoints
```

## 📂 Project Structure

```
fairydust/
├── services/
│   ├── identity/          # User auth, profiles, OAuth/OTP
│   │   ├── main.py
│   │   ├── models.py
│   │   ├── routes.py
│   │   └── auth.py
│   ├── ledger/            # DUST transactions, balances
│   ├── apps/              # App marketplace, LLM configs
│   ├── content/           # Stories, recipes, activities
│   ├── admin/             # Management dashboard (Python)
│   ├── admin-ui/          # Admin portal frontend (React)
│   └── builder/           # Developer portal
├── shared/                # Shared utilities
│   ├── database.py        # PostgreSQL connection pool
│   ├── auth_middleware.py # JWT authentication
│   ├── llm_pricing.py     # AI cost calculations
│   └── redis_client.py    # Redis connection
├── tests/                 # Test suite
│   ├── unit/             # Unit tests
│   ├── integration/      # Service interaction tests
│   ├── api/              # API endpoint tests
│   └── e2e/              # End-to-end tests
├── scripts/              # Development tools
├── .claude/              # Custom commands
└── docker-compose.yml    # Local development
```

## 🛡️ Security Features

- **JWT Authentication** - 1-hour access tokens, 30-day refresh tokens
- **OTP Security** - 6-digit codes, 10-minute expiry
- **Rate Limiting** - Per-user and per-endpoint limits
- **Input Validation** - Pydantic models with strict validation
- **SQL Injection Prevention** - Parameterized queries throughout
- **CORS Protection** - Configurable allowed origins
- **Token Revocation** - Redis-based blacklisting

## 🎯 Core Applications

### Story Generator
- **AI Models**: Claude 3.5 Sonnet, GPT-4  
- **Features**: Character-based stories, multiple lengths, target audiences
- **Cost**: 2-6 DUST per story

### Recipe Generator  
- **Integration**: Dietary restrictions, "people in my life" preferences
- **Features**: Complexity levels, serving sizes, ingredient inclusion/exclusion
- **Cost**: 3-5 DUST per recipe

### Activity Finder
- **APIs**: TripAdvisor Content API, Google Places
- **Features**: Location-based search, AI-enhanced descriptions
- **Cost**: 3 DUST per search

### Fortune Teller
- **Features**: Astrological calculations, personalized readings
- **Data**: Birth dates, zodiac signs, life path numbers
- **Cost**: Variable based on reading type

## 🏦 DUST Economy

### Virtual Currency System
- **Initial Grant**: 0 DUST (apps handle initial grants)
- **Daily Streaks**: 1-25 DUST bonuses via apps
- **App Grants**: Up to 100 DUST initial grant per app
- **Consumption**: Action-based pricing (2-6 DUST per action)

### Pricing Examples
```
Story Generation:    2-6 DUST (based on length)
Recipe Generation:   3-5 DUST (based on complexity)  
Activity Search:     3 DUST (per search)
Fortune Reading:     4-8 DUST (based on type)
```

## 🔌 External Integrations

### AI/LLM Services
- **Anthropic Claude** - Primary AI provider
- **OpenAI GPT** - Fallback AI provider  
- **Server-side Pricing** - Automatic cost calculation

### Content APIs
- **TripAdvisor** - Activity recommendations, ratings, photos
- **Google Places** - Restaurant data, locations, reviews
- **Google Maps** - Distance calculations, geocoding

### Communication
- **Resend** - Transactional emails, OTP delivery
- **Twilio** - SMS OTP, international support

## 📈 Performance & Monitoring

### Database Optimization
- **Connection Pooling** - Service-specific pool sizes
- **Indexed Queries** - Optimized for common access patterns
- **JSONB Fields** - Flexible metadata storage

### Caching Strategy  
- **Redis Caching** - App configurations (15-minute TTL)
- **LLM Response Caching** - Cost optimization
- **Session Management** - Distributed session storage

### Monitoring
- **Health Checks** - `/health` endpoints for all services
- **Usage Analytics** - LLM consumption, user behavior
- **Error Tracking** - Centralized logging and error handling

## 👥 Contributing

### Development Guidelines
1. **Follow the git workflow** - develop → staging → main
2. **Format before commit** - Use `./scripts/format.sh`
3. **Write tests** - Cover new functionality
4. **Update documentation** - Keep README and API docs current
5. **Test in staging** - Always validate in staging before production

### Code Standards
- **Python**: Black formatting, Ruff linting, Type hints
- **TypeScript**: ESLint, Prettier, Strict mode
- **API Design**: RESTful endpoints, consistent error handling
- **Database**: Raw SQL with asyncpg, no ORM

## 📝 License

This project is proprietary software. All rights reserved.

---

Built with ❤️ for scalable AI-powered mobile applications.

For detailed development guidance, see [CLAUDE.md](./CLAUDE.md).