from typing import Any

import httpx
import pytest


@pytest.mark.api
@pytest.mark.asyncio
async def test_dust_consumption_valid_request(
    http_client: httpx.AsyncClient,
    ledger_service_url: str,
    test_user: dict[str, Any],
    test_app: dict[str, Any],
):
    """Test successful DUST consumption through the API."""
    # Prepare the consumption request
    consumption_data = {
        "user_id": test_user["id"],
        "app_id": test_app["id"],
        "amount": test_app["dust_per_use"],
        "description": f"Used {test_app['name']} app",
    }

    # Make the API request
    response = await http_client.post(
        f"{ledger_service_url}/transactions/consume", json=consumption_data
    )

    # Assert successful response
    assert response.status_code == 200

    response_data = response.json()
    assert response_data["success"] is True
    assert "transaction_id" in response_data
    assert response_data["amount"] == test_app["dust_per_use"]
    assert response_data["new_balance"] == test_user["dust_balance"] - test_app["dust_per_use"]


@pytest.mark.api
@pytest.mark.asyncio
async def test_dust_consumption_insufficient_balance(
    http_client: httpx.AsyncClient,
    ledger_service_url: str,
    test_user: dict[str, Any],
    test_app: dict[str, Any],
):
    """Test DUST consumption when user has insufficient balance."""
    # Create a user with low balance
    low_balance_user = test_user.copy()
    low_balance_user["dust_balance"] = 2  # Less than app cost

    consumption_data = {
        "user_id": low_balance_user["id"],
        "app_id": test_app["id"],
        "amount": test_app["dust_per_use"],  # 5 DUST, more than user has
        "description": f"Used {test_app['name']} app",
    }

    response = await http_client.post(
        f"{ledger_service_url}/transactions/consume", json=consumption_data
    )

    # Should return 400 for insufficient balance
    assert response.status_code == 400

    response_data = response.json()
    assert response_data["success"] is False
    assert "insufficient" in response_data["error"].lower()


@pytest.mark.api
@pytest.mark.asyncio
async def test_dust_consumption_invalid_app(
    http_client: httpx.AsyncClient, ledger_service_url: str, test_user: dict[str, Any]
):
    """Test DUST consumption with invalid app ID."""
    consumption_data = {
        "user_id": test_user["id"],
        "app_id": "invalid-app-id",
        "amount": 5,
        "description": "Test invalid app",
    }

    response = await http_client.post(
        f"{ledger_service_url}/transactions/consume", json=consumption_data
    )

    # Should return 404 for invalid app
    assert response.status_code == 404

    response_data = response.json()
    assert response_data["success"] is False
    assert "app not found" in response_data["error"].lower()


@pytest.mark.api
@pytest.mark.asyncio
async def test_dust_consumption_missing_fields(
    http_client: httpx.AsyncClient, ledger_service_url: str
):
    """Test DUST consumption with missing required fields."""
    incomplete_data = {
        "app_id": "some-app-id",
        "amount": 5
        # Missing user_id and description
    }

    response = await http_client.post(
        f"{ledger_service_url}/transactions/consume", json=incomplete_data
    )

    # Should return 422 for validation error
    assert response.status_code == 422


@pytest.mark.api
@pytest.mark.asyncio
async def test_get_user_balance(
    http_client: httpx.AsyncClient, ledger_service_url: str, test_user: dict[str, Any]
):
    """Test retrieving user's DUST balance."""
    response = await http_client.get(f"{ledger_service_url}/balance/{test_user['id']}")

    assert response.status_code == 200

    response_data = response.json()
    assert "balance" in response_data
    assert "user_id" in response_data
    assert response_data["user_id"] == test_user["id"]


@pytest.mark.api
@pytest.mark.asyncio
async def test_get_user_transaction_history(
    http_client: httpx.AsyncClient, ledger_service_url: str, test_user: dict[str, Any]
):
    """Test retrieving user's transaction history."""
    response = await http_client.get(f"{ledger_service_url}/transactions/{test_user['id']}")

    assert response.status_code == 200

    response_data = response.json()
    assert "transactions" in response_data
    assert isinstance(response_data["transactions"], list)
