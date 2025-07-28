# services/admin/routes/payments.py
import os
from datetime import datetime, timedelta
from typing import Optional
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends, Query
from fastapi.exceptions import HTTPException

from shared.auth_middleware import require_admin
from shared.database import Database, get_db

# Create router
payments_router = APIRouter(dependencies=[Depends(require_admin)])

# Get ledger service URL
environment = os.getenv("ENVIRONMENT", "staging")
base_url_suffix = "production" if environment == "production" else "staging"
ledger_url = f"https://fairydust-ledger-{base_url_suffix}.up.railway.app"


@payments_router.get("/transactions")
async def get_payment_transactions(
    user_id: Optional[str] = Query(None, description="Filter by user ID"),
    status: Optional[str] = Query(None, description="Filter by status"),
    platform: Optional[str] = Query(None, description="Filter by platform"),
    limit: int = Query(100, le=500, description="Number of transactions to return"),
    offset: int = Query(0, ge=0, description="Offset for pagination"),
):
    """Get payment transactions with receipt verification status"""
    
    db = await get_db()
    
    # Build query
    query = """
        SELECT 
            id, user_id, amount, type, status, description,
            payment_id, receipt_verification_status, apple_transaction_id,
            apple_product_id, apple_purchase_date_ms, payment_amount_cents,
            created_at, metadata
        FROM dust_transactions 
        WHERE type = 'purchase'
    """
    
    params = []
    param_count = 0
    
    if user_id:
        param_count += 1
        query += f" AND user_id = ${param_count}"
        params.append(UUID(user_id))
        
    if status:
        param_count += 1
        query += f" AND status = ${param_count}"
        params.append(status)
        
    if platform:
        if platform == "ios":
            query += " AND apple_transaction_id IS NOT NULL"
        elif platform == "android":
            query += " AND payment_id LIKE '%android%'"
        elif platform == "stripe":
            query += " AND payment_id LIKE '%stripe%'"
    
    query += " ORDER BY created_at DESC"
    
    param_count += 1
    query += f" LIMIT ${param_count}"
    params.append(limit)
    
    param_count += 1
    query += f" OFFSET ${param_count}"
    params.append(offset)
    
    try:
        transactions = await db.fetch_all(query, *params)
        
        # Convert to dict format
        transactions_list = []
        for tx in transactions:
            tx_dict = dict(tx)
            # Convert UUID to string for JSON serialization
            tx_dict['id'] = str(tx_dict['id'])
            tx_dict['user_id'] = str(tx_dict['user_id'])
            transactions_list.append(tx_dict)
        
        return {
            "transactions": transactions_list,
            "total": len(transactions_list),
            "limit": limit,
            "offset": offset
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch transactions: {str(e)}")


@payments_router.get("/stats")
async def get_payment_stats():
    """Get payment statistics and analytics"""
    
    db = await get_db()
    
    try:
        # Overall stats
        stats_query = """
            SELECT 
                COUNT(*) as total_transactions,
                COALESCE(SUM(payment_amount_cents), 0) as total_revenue_cents,
                COUNT(CASE WHEN status = 'completed' AND receipt_verification_status = 'verified' THEN 1 END) as successful_purchases,
                COUNT(CASE WHEN receipt_verification_status = 'failed' THEN 1 END) as failed_verifications,
                COUNT(CASE WHEN apple_transaction_id IS NOT NULL THEN 1 END) as apple_transactions
            FROM dust_transactions 
            WHERE type = 'purchase'
        """
        
        stats = await db.fetch_one(stats_query)
        
        # Recent 7 days revenue trend  
        trend_query = """
            SELECT 
                DATE(created_at) as date,
                COUNT(*) as transactions,
                COALESCE(SUM(payment_amount_cents), 0) as revenue_cents
            FROM dust_transactions 
            WHERE type = 'purchase' 
                AND created_at >= CURRENT_DATE - INTERVAL '7 days'
            GROUP BY DATE(created_at)
            ORDER BY date DESC
        """
        
        trend_data = await db.fetch_all(trend_query)
        
        # Top products
        products_query = """
            SELECT 
                apple_product_id,
                COUNT(*) as purchase_count,
                COALESCE(SUM(amount), 0) as total_dust,
                COALESCE(SUM(payment_amount_cents), 0) as total_revenue_cents
            FROM dust_transactions 
            WHERE type = 'purchase' 
                AND apple_product_id IS NOT NULL
                AND created_at >= CURRENT_DATE - INTERVAL '30 days'
            GROUP BY apple_product_id
            ORDER BY purchase_count DESC
            LIMIT 10
        """
        
        top_products = await db.fetch_all(products_query)
        
        return {
            "total_transactions": stats["total_transactions"],
            "total_revenue_cents": stats["total_revenue_cents"],
            "successful_purchases": stats["successful_purchases"],
            "failed_verifications": stats["failed_verifications"],
            "apple_transactions": stats["apple_transactions"],
            "revenue_trend": [dict(row) for row in trend_data],
            "top_products": [dict(row) for row in top_products]
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch payment stats: {str(e)}")


@payments_router.get("/verification-failures")
async def get_verification_failures(
    limit: int = Query(50, le=200, description="Number of failures to return"),
    days: int = Query(7, le=30, description="Number of days to look back")
):
    """Get recent receipt verification failures for debugging"""
    
    db = await get_db()
    
    try:
        query = """
            SELECT 
                id, user_id, apple_product_id, receipt_verification_status,
                receipt_verification_response, created_at, metadata
            FROM dust_transactions 
            WHERE type = 'purchase' 
                AND receipt_verification_status = 'failed'
                AND created_at >= CURRENT_DATE - INTERVAL '%s days'
            ORDER BY created_at DESC
            LIMIT $1
        """ % days
        
        failures = await db.fetch_all(query, limit)
        
        failures_list = []
        for failure in failures:
            failure_dict = dict(failure)
            failure_dict['id'] = str(failure_dict['id'])
            failure_dict['user_id'] = str(failure_dict['user_id'])
            failures_list.append(failure_dict)
        
        return {
            "failures": failures_list,
            "total": len(failures_list),
            "days": days
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch verification failures: {str(e)}")


@payments_router.post("/refund/{transaction_id}")
async def refund_transaction(transaction_id: str, reason: str):
    """Refund a transaction via ledger service"""
    
    try:
        # Call ledger service refund endpoint
        async with httpx.AsyncClient() as client:
            response = await client.post(
                f"{ledger_url}/admin/refund",
                json={
                    "transaction_id": transaction_id,
                    "reason": reason
                },
                timeout=30.0
            )
            
            if response.status_code == 200:
                return response.json()
            else:
                raise HTTPException(
                    status_code=response.status_code, 
                    detail=f"Ledger service error: {response.text}"
                )
                
    except httpx.RequestError as e:
        raise HTTPException(status_code=500, detail=f"Failed to connect to ledger service: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Refund failed: {str(e)}")