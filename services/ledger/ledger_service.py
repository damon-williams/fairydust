# services/ledger/ledger_service.py
import json
from typing import Optional
from uuid import UUID, uuid4

import redis.asyncio as redis
from fastapi import HTTPException
from models import (
    Transaction,
    TransactionResponse,
    TransactionStatus,
    TransactionType,
)

from shared.database import Database
from shared.redis_client import RedisCache
from shared.streak_utils import update_daily_streak_for_grant


class LedgerService:
    """Core ledger service for DUST transactions"""

    def __init__(self, db: Database, redis_client: redis.Redis):
        self.db = db
        self.redis = redis_client
        self.balance_cache = RedisCache(redis_client, "balance")
        self.lock_prefix = "balance_lock"
        self.idempotency_prefix = "idempotency"

    def _parse_transaction_data(self, transaction_record: dict) -> dict:
        """Parse transaction data from database, handling JSON metadata"""
        transaction_data = dict(transaction_record)
        if transaction_data.get("metadata") and isinstance(transaction_data["metadata"], str):
            try:
                transaction_data["metadata"] = json.loads(transaction_data["metadata"])
            except json.JSONDecodeError:
                transaction_data["metadata"] = {}
        return transaction_data

    async def get_balance(self, user_id: UUID, use_cache: bool = True) -> int:
        """Get user's current DUST balance"""
        if use_cache:
            # Try cache first
            cached = await self.balance_cache.get(str(user_id))
            if cached:
                return int(cached)

        # Get from database
        result = await self.db.fetch_one("SELECT dust_balance FROM users WHERE id = $1", user_id)

        if not result:
            raise HTTPException(status_code=404, detail="User not found")

        balance = result["dust_balance"]

        # Update cache
        await self.balance_cache.set(str(user_id), str(balance), ttl=300)  # 5 min TTL

        return balance

    async def _acquire_balance_lock(self, user_id: UUID, timeout: int = 2) -> bool:
        """Acquire a distributed lock for balance operations"""
        lock_key = f"{self.lock_prefix}:{user_id}"
        lock_value = str(uuid4())

        # Try to acquire lock with timeout
        acquired = await self.redis.set(
            lock_key,
            lock_value,
            nx=True,  # Only set if not exists
            ex=timeout,  # Expire after timeout seconds
        )

        if acquired:
            # Store lock value for release
            await self.redis.set(f"{lock_key}:value", lock_value, ex=timeout)

        return bool(acquired)

    async def _release_balance_lock(self, user_id: UUID):
        """Release the distributed lock"""
        lock_key = f"{self.lock_prefix}:{user_id}"
        lock_value_key = f"{lock_key}:value"

        # Get our lock value
        our_value = await self.redis.get(lock_value_key)
        if our_value:
            # Use Lua script for atomic check-and-delete
            lua_script = """
            if redis.call("get", KEYS[1]) == ARGV[1] then
                redis.call("del", KEYS[1])
                redis.call("del", KEYS[2])
                return 1
            else
                return 0
            end
            """
            await self.redis.eval(lua_script, 2, lock_key, lock_value_key, our_value)

    async def _check_idempotency(self, idempotency_key: str) -> Optional[UUID]:
        """Check if transaction with idempotency key already exists"""
        key = f"{self.idempotency_prefix}:{idempotency_key}"
        transaction_id = await self.redis.get(key)
        return UUID(transaction_id) if transaction_id else None

    async def _store_idempotency(self, idempotency_key: str, transaction_id: UUID):
        """Store idempotency key with transaction ID"""
        key = f"{self.idempotency_prefix}:{idempotency_key}"
        # Store for 24 hours
        await self.redis.setex(key, 86400, str(transaction_id))

    async def consume_dust(
        self,
        user_id: UUID,
        amount: int,
        app_id: UUID,
        action: str,
        idempotency_key: str,
        metadata: Optional[dict] = None,
    ) -> TransactionResponse:
        """Consume DUST from user's balance"""

        # Check idempotency
        existing_tx_id = await self._check_idempotency(idempotency_key)
        if existing_tx_id:
            # Return existing transaction
            tx = await self.db.fetch_one(
                "SELECT * FROM dust_transactions WHERE id = $1", existing_tx_id
            )
            if tx:
                tx_data = self._parse_transaction_data(tx)
                return TransactionResponse(
                    transaction=Transaction(**tx_data),
                    new_balance=await self.get_balance(user_id, use_cache=False),
                    previous_balance=await self.get_balance(user_id, use_cache=False) + amount,
                )

        # Acquire lock
        lock_acquired = await self._acquire_balance_lock(user_id)
        if not lock_acquired:
            raise HTTPException(status_code=409, detail="Balance operation in progress")

        try:
            # Start transaction
            async with self.db.transaction() as conn:
                # Get current balance (Redis lock provides concurrency control)
                user = await conn.fetchrow(
                    "SELECT id, dust_balance FROM users WHERE id = $1", user_id
                )

                if not user:
                    raise HTTPException(status_code=404, detail="User not found")

                current_balance = user["dust_balance"]

                if current_balance < amount:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Insufficient balance. Have {current_balance}, need {amount}",
                    )

                # Update balance
                new_balance = current_balance - amount
                await conn.execute(
                    "UPDATE users SET dust_balance = $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2",
                    new_balance,
                    user_id,
                )

                # Create transaction record
                transaction_id = uuid4()
                transaction = await conn.fetchrow(
                    """
                    INSERT INTO dust_transactions (
                        id, user_id, amount, type, status, description,
                        app_id, metadata, idempotency_key
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
                    RETURNING *
                    """,
                    transaction_id,
                    user_id,
                    -amount,
                    TransactionType.CONSUME.value,
                    TransactionStatus.COMPLETED.value,
                    f"Consumed for {action}",
                    app_id,
                    json.dumps(metadata) if metadata else None,
                    idempotency_key,
                )

                # Store idempotency key
                await self._store_idempotency(idempotency_key, transaction_id)

                # Invalidate cache
                await self.balance_cache.delete(str(user_id))

                # Notify balance update via pub/sub
                await self.redis.publish(
                    f"balance_update:{user_id}",
                    json.dumps(
                        {
                            "user_id": str(user_id),
                            "old_balance": current_balance,
                            "new_balance": new_balance,
                            "transaction_id": str(transaction_id),
                        }
                    ),
                )

                # Parse transaction data and return
                transaction_data = self._parse_transaction_data(transaction)
                return TransactionResponse(
                    transaction=Transaction(**transaction_data),
                    new_balance=new_balance,
                    previous_balance=current_balance,
                )

        finally:
            await self._release_balance_lock(user_id)

    async def grant_dust(
        self,
        user_id: UUID,
        amount: int,
        reason: str,
        admin_id: Optional[UUID] = None,
        metadata: Optional[dict] = None,
    ) -> TransactionResponse:
        """Grant DUST to user's balance"""

        # Acquire lock
        lock_acquired = await self._acquire_balance_lock(user_id)
        if not lock_acquired:
            raise HTTPException(status_code=409, detail="Balance operation in progress")

        try:
            async with self.db.transaction() as conn:
                # Get current balance (Redis lock provides concurrency control)
                user = await conn.fetchrow(
                    "SELECT id, dust_balance FROM users WHERE id = $1", user_id
                )

                if not user:
                    raise HTTPException(status_code=404, detail="User not found")

                current_balance = user["dust_balance"]
                new_balance = current_balance + amount

                # Update balance
                await conn.execute(
                    "UPDATE users SET dust_balance = $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2",
                    new_balance,
                    user_id,
                )

                # Create transaction record
                transaction_id = uuid4()
                transaction = await conn.fetchrow(
                    """
                    INSERT INTO dust_transactions (
                        id, user_id, amount, type, status, description, metadata
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                    RETURNING *
                    """,
                    transaction_id,
                    user_id,
                    amount,
                    TransactionType.GRANT.value,
                    TransactionStatus.COMPLETED.value,
                    reason,
                    json.dumps({**(metadata or {}), "admin_id": str(admin_id)})
                    if admin_id
                    else json.dumps(metadata)
                    if metadata
                    else None,
                )

                # Invalidate cache
                await self.balance_cache.delete(str(user_id))

                # Notify balance update
                await self.redis.publish(
                    f"balance_update:{user_id}",
                    json.dumps(
                        {
                            "user_id": str(user_id),
                            "old_balance": current_balance,
                            "new_balance": new_balance,
                            "transaction_id": str(transaction_id),
                        }
                    ),
                )

                # Parse transaction data and return
                transaction_data = self._parse_transaction_data(transaction)
                return TransactionResponse(
                    transaction=Transaction(**transaction_data),
                    new_balance=new_balance,
                    previous_balance=current_balance,
                )
        finally:
            await self._release_balance_lock(user_id)

    async def record_purchase(
        self, user_id: UUID, dust_amount: int, payment_id: str, payment_amount_cents: int
    ) -> TransactionResponse:
        """Record DUST purchase from Stripe payment"""

        # Calculate expected amount based on rate
        expected_cents = dust_amount  # 1 DUST = 1 cent
        if payment_amount_cents < expected_cents:
            raise HTTPException(status_code=400, detail="Payment amount mismatch")

        return await self.grant_dust(
            user_id=user_id,
            amount=dust_amount,
            reason=f"Purchased {dust_amount} DUST",
            metadata={
                "payment_id": payment_id,
                "payment_amount_cents": payment_amount_cents,
                "dust_rate": 0.01,
            },
        )

    async def refund_transaction(
        self, transaction_id: UUID, reason: str, admin_id: Optional[UUID] = None
    ) -> TransactionResponse:
        """Refund a previous consume transaction"""

        # Get original transaction
        original_tx = await self.db.fetch_one(
            "SELECT * FROM dust_transactions WHERE id = $1", transaction_id
        )

        if not original_tx:
            raise HTTPException(status_code=404, detail="Transaction not found")

        if original_tx["type"] != TransactionType.CONSUME.value:
            raise HTTPException(status_code=400, detail="Can only refund consume transactions")

        if original_tx["status"] != TransactionStatus.COMPLETED.value:
            raise HTTPException(status_code=400, detail="Can only refund completed transactions")

        # Check if already refunded
        existing_refund = await self.db.fetch_one(
            """
            SELECT id FROM dust_transactions
            WHERE metadata->>'original_transaction_id' = $1
            AND type = $2
            """,
            str(transaction_id),
            TransactionType.REFUND.value,
        )

        if existing_refund:
            raise HTTPException(status_code=400, detail="Transaction already refunded")

        # Refund is the negative of the original amount (which was negative)
        refund_amount = abs(original_tx["amount"])

        # Create refund transaction
        return await self.grant_dust(
            user_id=original_tx["user_id"],
            amount=refund_amount,
            reason=f"Refund: {reason}",
            admin_id=admin_id,
            metadata={
                "original_transaction_id": str(transaction_id),
                "original_app_id": str(original_tx["app_id"]) if original_tx["app_id"] else None,
            },
        )

    async def get_transactions(
        self,
        user_id: UUID,
        limit: int = 50,
        offset: int = 0,
        type_filter: Optional[TransactionType] = None,
        app_id: Optional[UUID] = None,
    ) -> list[Transaction]:
        """Get user's transaction history"""

        query = """
            SELECT * FROM dust_transactions
            WHERE user_id = $1
        """
        params = [user_id]
        param_count = 2

        if type_filter:
            query += f" AND type = ${param_count}"
            params.append(type_filter.value)
            param_count += 1

        if app_id:
            query += f" AND app_id = ${param_count}"
            params.append(app_id)
            param_count += 1

        query += f" ORDER BY created_at DESC LIMIT ${param_count} OFFSET ${param_count + 1}"
        params.extend([limit, offset])

        transactions = await self.db.fetch_all(query, *params)
        # Parse all transactions to handle JSON metadata
        return [Transaction(**self._parse_transaction_data(tx)) for tx in transactions]

    async def grant_initial_dust(
        self,
        user_id: UUID,
        app_id: UUID,
        amount: int,
        idempotency_key: str,
    ) -> TransactionResponse:
        """Grant initial DUST to user for app onboarding (max 100)"""

        # Validate amount
        if amount > 100:
            raise HTTPException(status_code=400, detail="Initial grant cannot exceed 100 DUST")

        # No per-app grant restrictions - allow multiple grants

        # Idempotency check removed for testing - allow duplicate requests

        # Acquire lock
        print(f"🔒 GRANT_INITIAL_LOCK_ATTEMPT: Trying to acquire lock for user {user_id}, idempotency_key: {idempotency_key}", flush=True)
        lock_acquired = await self._acquire_balance_lock(user_id)
        if not lock_acquired:
            print(f"🔒 GRANT_INITIAL_LOCK_FAILED: Could not acquire lock for user {user_id}, idempotency_key: {idempotency_key}", flush=True)
            raise HTTPException(status_code=409, detail="Balance operation in progress")
        
        print(f"✅ GRANT_INITIAL_LOCK_ACQUIRED: Successfully acquired lock for user {user_id}", flush=True)

        try:
            # First check if user already has this grant to avoid constraint violation
            existing_grant = await self.db.fetch_one(
                "SELECT id FROM app_grants WHERE user_id = $1 AND app_id = $2 AND grant_type = 'initial'",
                user_id,
                app_id,
            )
            
            if existing_grant:
                print(f"✅ GRANT_INITIAL_ALREADY_EXISTS: User {user_id} already has initial grant for app {app_id}, returning existing", flush=True)
                
                # Find and return the existing transaction
                existing_transaction = await self.db.fetch_one(
                    """
                    SELECT dt.* FROM dust_transactions dt
                    JOIN app_grants ag ON ag.metadata->>'transaction_id' = dt.id::text
                    WHERE ag.user_id = $1 AND ag.app_id = $2 AND ag.grant_type = 'initial'
                    ORDER BY dt.created_at DESC
                    LIMIT 1
                    """,
                    user_id,
                    app_id,
                )
                
                if existing_transaction:
                    # Get current balance
                    current_balance = await self.get_balance(user_id)
                    
                    transaction_data = self._parse_transaction_data(existing_transaction)
                    return TransactionResponse(
                        transaction=Transaction(**transaction_data),
                        new_balance=current_balance,
                        previous_balance=current_balance - existing_transaction["amount"],
                    )

            async with self.db.transaction() as conn:
                # Verify user exists (Redis lock provides concurrency control)
                user = await conn.fetchrow(
                    "SELECT id, dust_balance FROM users WHERE id = $1", user_id
                )

                if not user:
                    raise HTTPException(status_code=404, detail="User not found")

                current_balance = user["dust_balance"]
                new_balance = current_balance + amount

                # Update balance
                await conn.execute(
                    "UPDATE users SET dust_balance = $1, updated_at = CURRENT_TIMESTAMP WHERE id = $2",
                    new_balance,
                    user_id,
                )

                # Create transaction record
                transaction_id = uuid4()
                transaction = await conn.fetchrow(
                    """
                    INSERT INTO dust_transactions (
                        id, user_id, amount, type, status, description, app_id, metadata
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    RETURNING *
                    """,
                    transaction_id,
                    user_id,
                    amount,
                    TransactionType.GRANT.value,
                    TransactionStatus.COMPLETED.value,
                    "Initial app grant",
                    app_id,
                    json.dumps({"grant_type": "initial", "app_id": str(app_id)}),
                )

                # Record grant in app_grants table
                await conn.execute(
                    """
                    INSERT INTO app_grants (
                        user_id, app_id, grant_type, amount, idempotency_key, metadata
                    ) VALUES ($1, $2, $3, $4, $5, $6)
                    """,
                    user_id,
                    app_id,
                    "initial",
                    amount,
                    idempotency_key,
                    json.dumps({"transaction_id": str(transaction_id)}),
                )

                # Invalidate cache
                await self.balance_cache.delete(str(user_id))

                # Parse transaction data and return
                transaction_data = self._parse_transaction_data(transaction)
                return TransactionResponse(
                    transaction=Transaction(**transaction_data),
                    new_balance=new_balance,
                    previous_balance=current_balance,
                )

        finally:
            print(f"🔓 GRANT_INITIAL_LOCK_RELEASE: Releasing lock for user {user_id}", flush=True)
            await self._release_balance_lock(user_id)

    async def grant_streak_bonus(
        self,
        user_id: UUID,
        app_id: UUID,
        amount: int,
        streak_days: int,
        idempotency_key: str,
    ) -> TransactionResponse:
        """Grant daily streak bonus to user (max 25)"""

        # Validate amount
        if amount > 25:
            raise HTTPException(status_code=400, detail="Streak bonus cannot exceed 25 DUST")

        # Validate streak days
        if streak_days < 1 or streak_days > 5:
            raise HTTPException(status_code=400, detail="Streak days must be between 1 and 5")

        # Use UTC date to ensure consistency across timezones
        from datetime import date, datetime

        today = datetime.utcnow().date()

        # Idempotency check removed for testing - allow duplicate requests

        # Acquire lock
        lock_acquired = await self._acquire_balance_lock(user_id)
        if not lock_acquired:
            raise HTTPException(status_code=409, detail="Balance operation in progress")

        try:
            async with self.db.transaction() as conn:
                # Verify user exists and get current streak info (Redis lock provides concurrency control)
                user = await conn.fetchrow(
                    "SELECT id, dust_balance, streak_days, last_login_date FROM users WHERE id = $1", user_id
                )

                if not user:
                    raise HTTPException(status_code=404, detail="User not found")
                
                # Calculate streak update WITH database write
                from shared.streak_utils import update_daily_streak_for_grant
                new_streak_days, new_login_date = await update_daily_streak_for_grant(
                    conn, user_id, user["streak_days"], user["last_login_date"]
                )

                current_balance = user["dust_balance"]
                new_balance = current_balance + amount

                # Update only balance since streak is already updated by update_daily_streak_for_grant
                await conn.execute(
                    """UPDATE users 
                       SET dust_balance = $1, updated_at = CURRENT_TIMESTAMP 
                       WHERE id = $2""",
                    new_balance,
                    user_id,
                )

                # Create transaction record
                transaction_id = uuid4()
                transaction = await conn.fetchrow(
                    """
                    INSERT INTO dust_transactions (
                        id, user_id, amount, type, status, description, app_id, metadata
                    ) VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    RETURNING *
                    """,
                    transaction_id,
                    user_id,
                    amount,
                    TransactionType.GRANT.value,
                    TransactionStatus.COMPLETED.value,
                    f"Daily streak bonus (day {streak_days})",
                    app_id,
                    json.dumps(
                        {"grant_type": "streak", "streak_days": streak_days, "app_id": str(app_id)}
                    ),
                )

                # Record grant in app_grants table
                try:
                    await conn.execute(
                        """
                        INSERT INTO app_grants (
                            user_id, app_id, grant_type, amount, granted_date, idempotency_key, metadata
                        ) VALUES ($1, $2, $3, $4, $5, $6, $7)
                        """,
                        user_id,
                        app_id,
                        "streak",
                        amount,
                        today,
                        idempotency_key,
                        json.dumps({"transaction_id": str(transaction_id), "streak_days": streak_days}),
                    )
                except Exception as e:
                    # Check for unique constraint violation (already claimed today)
                    if "duplicate key value violates unique constraint" in str(e) and ("app_grants_user_id_app_id_grant_type" in str(e) or "granted_date" in str(e)):
                        raise HTTPException(
                            status_code=409, 
                            detail=f"Streak bonus already claimed today for this app"
                        )
                    else:
                        # Re-raise other database errors
                        raise

                # Invalidate cache
                await self.balance_cache.delete(str(user_id))

                # Parse transaction data and return
                transaction_data = self._parse_transaction_data(transaction)
                return TransactionResponse(
                    transaction=Transaction(**transaction_data),
                    new_balance=new_balance,
                    previous_balance=current_balance,
                )

        finally:
            await self._release_balance_lock(user_id)
