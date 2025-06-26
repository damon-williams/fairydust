import asyncio
import os
import uuid
from collections.abc import AsyncGenerator
from typing import Any

import httpx
import pytest
from faker import Faker

# Set test environment
os.environ["ENVIRONMENT"] = "test"
os.environ["DATABASE_URL"] = "postgresql://postgres:password@localhost:5432/fairydust_test"
os.environ["REDIS_URL"] = "redis://localhost:6379/1"
os.environ["JWT_SECRET_KEY"] = "test-secret-key"

fake = Faker()


@pytest.fixture(scope="session")
def event_loop():
    """Create an instance of the default event loop for the test session."""
    loop = asyncio.get_event_loop_policy().new_event_loop()
    yield loop
    loop.close()


@pytest.fixture
async def test_user() -> dict[str, Any]:
    """Create a test user for authentication tests."""
    return {
        "id": str(uuid.uuid4()),
        "fairyname": f"test_user_{fake.random_int(1000, 9999)}",
        "email": fake.email(),
        "phone": fake.phone_number(),
        "dust_balance": 25,
        "is_builder": True,
        "is_admin": False,
        "is_active": True,
    }


@pytest.fixture
async def test_app() -> dict[str, Any]:
    """Create a test app for API tests."""
    return {
        "id": str(uuid.uuid4()),
        "name": fake.company(),
        "slug": fake.slug(),
        "description": fake.text(max_nb_chars=200),
        "category": "entertainment",
        "dust_per_use": 5,
        "status": "approved",
        "is_active": True,
    }


@pytest.fixture
async def http_client() -> AsyncGenerator[httpx.AsyncClient, None]:
    """HTTP client for API testing."""
    async with httpx.AsyncClient() as client:
        yield client


@pytest.fixture
def api_base_url() -> str:
    """Base URL for API tests - can be overridden via environment variable."""
    return os.getenv("API_BASE_URL", "http://localhost:8002")  # Ledger service default


@pytest.fixture
def identity_service_url() -> str:
    """Identity service URL for authentication tests."""
    return os.getenv("IDENTITY_SERVICE_URL", "http://localhost:8001")


@pytest.fixture
def apps_service_url() -> str:
    """Apps service URL for app management tests."""
    return os.getenv("APPS_SERVICE_URL", "http://localhost:8003")


@pytest.fixture
def ledger_service_url() -> str:
    """Ledger service URL for transaction tests."""
    return os.getenv("LEDGER_SERVICE_URL", "http://localhost:8002")
