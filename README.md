# fairydust Platform

A payment and identity platform for AI-powered applications using virtual currency (DUST).

## Architecture

The platform consists of microservices:
- **Identity Service** - Authentication, user management, OAuth/OTP
- **Ledger Service** - DUST balance tracking and transactions
- **Billing Service** - Stripe integration for payments

## Quick Start

### Prerequisites
- Python 3.11+
- PostgreSQL 16+
- Redis 7+
- Docker & Docker Compose (optional)

### Local Development with Docker

1. Clone the repository:
```bash
git clone <your-repo-url>
cd fairydust
```

2. Copy environment files:
```bash
cp .env.example .env
# Edit .env with your configuration
```

3. Start services:
```bash
docker-compose up
```

The Identity Service will be available at `http://localhost:8001`

### Local Development without Docker

1. Install PostgreSQL and Redis locally

2. Create Python virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
cd services/identity
pip install -r requirements.txt
```

4. Set up environment:
```bash
cp .env.example .env
# Edit .env with your configuration
```

5. Run the service:
```bash
python main.py
```

## API Documentation

Once running, visit:
- Swagger UI: `http://localhost:8001/docs`
- ReDoc: `http://localhost:8001/redoc`

## Deployment on Railway

1. Install Railway CLI:
```bash
npm install -g @railway/cli
```

2. Login and initialize:
```bash
railway login
railway init
```

3. Add PostgreSQL and Redis:
```bash
railway add
# Select PostgreSQL and Redis
```

4. Deploy:
```bash
railway up
```

## Environment Variables

See `.env.example` for all required environment variables.

### Critical for Production:
- `JWT_SECRET_KEY` - Must be a strong, unique secret
- OAuth credentials for Google/Apple/Facebook
- SMTP credentials for email
- Twilio credentials for SMS

## Project Structure

```
fairydust/
├── services/
│   ├── identity/       # Authentication service
│   ├── ledger/        # DUST transaction service
│   └── billing/       # Payment processing service
├── shared/            # Shared utilities
├── widgets/           # Frontend components
└── docker-compose.yml
```

## Testing

Run tests:
```bash
pytest
```

## Security Notes

- All passwords are hashed using bcrypt
- JWTs expire after 1 hour
- Refresh tokens expire after 30 days
- OTPs expire after 10 minutes
- All sensitive operations require authentication

## Next Steps

1. Set up OAuth applications (Google, Apple, Facebook)
2. Configure SMTP for email
3. Set up Twilio for SMS
4. Deploy to Railway
5. Implement Ledger Service
6. Implement Billing Service