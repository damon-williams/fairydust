---
name: "Test API Endpoints"
description: "Run comprehensive tests on fairydust API endpoints"
category: "testing"
---

# Test API Endpoints

Run tests on fairydust microservices and API endpoints.

## What this command does:

1. **Run pytest** on the test suite
2. **Check specific service health** endpoints
3. **Test database connections** 
4. **Validate API responses** for critical endpoints
5. **Show coverage report** if available

## Usage:
```
/project:test-endpoints [service name or test pattern]
```

## Arguments:
- `$ARGUMENTS` - Optional service name (identity, ledger, apps, content, admin) or pytest pattern

## Examples:
```
/project:test-endpoints identity
/project:test-endpoints test_auth.py
/project:test-endpoints  # Run all tests
```

## Services tested:
- **Identity Service** (port 8001): Authentication, user management
- **Ledger Service** (port 8002): DUST transactions
- **Apps Service** (port 8003): App marketplace, LLM management  
- **Admin Portal** (port 8004): Admin dashboard
- **Content Service** (port 8006): User-generated content

This ensures code quality before deployment as documented in CLAUDE.md.