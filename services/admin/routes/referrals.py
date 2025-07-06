# services/admin/routes/referrals.py
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query

from models import (
    ReferralConfig,
    ReferralConfigUpdate,
    ReferralCodesResponse,
    ReferralRedemptionsResponse,
    ReferralSystemStats,
)
from shared.auth_middleware import TokenData, require_admin
from shared.database import Database, get_db

referrals_router = APIRouter()


@referrals_router.get("/config", response_model=ReferralConfig)
async def get_referral_config(
    admin_user: TokenData = Depends(require_admin),
    db: Database = Depends(get_db),
):
    """Get current referral system configuration"""
    # For now, return hardcoded defaults
    # In production, these would be stored in a database table
    return ReferralConfig(
        referee_bonus=15,
        referrer_bonus=15,
        milestone_rewards=[
            {"referral_count": 5, "bonus_amount": 25},
            {"referral_count": 10, "bonus_amount": 50},
            {"referral_count": 20, "bonus_amount": 100},
        ],
        code_expiry_days=30,
        max_referrals_per_user=100,
        system_enabled=True,
    )


@referrals_router.put("/config", response_model=ReferralConfig)
async def update_referral_config(
    config_update: ReferralConfigUpdate,
    admin_user: TokenData = Depends(require_admin),
    db: Database = Depends(get_db),
):
    """Update referral system configuration"""
    # For now, just return the updated config
    # In production, this would save to database
    current_config = ReferralConfig(
        referee_bonus=15,
        referrer_bonus=15,
        milestone_rewards=[
            {"referral_count": 5, "bonus_amount": 25},
            {"referral_count": 10, "bonus_amount": 50},
        ],
        code_expiry_days=30,
        max_referrals_per_user=100,
        system_enabled=True,
    )

    # Apply updates
    if config_update.referee_bonus is not None:
        current_config.referee_bonus = config_update.referee_bonus
    if config_update.referrer_bonus is not None:
        current_config.referrer_bonus = config_update.referrer_bonus
    if config_update.milestone_rewards is not None:
        current_config.milestone_rewards = config_update.milestone_rewards
    if config_update.code_expiry_days is not None:
        current_config.code_expiry_days = config_update.code_expiry_days
    if config_update.max_referrals_per_user is not None:
        current_config.max_referrals_per_user = config_update.max_referrals_per_user
    if config_update.system_enabled is not None:
        current_config.system_enabled = config_update.system_enabled

    return current_config


@referrals_router.get("/stats", response_model=ReferralSystemStats)
async def get_referral_system_stats(
    admin_user: TokenData = Depends(require_admin),
    db: Database = Depends(get_db),
):
    """Get system-wide referral statistics"""
    # Get basic stats
    stats = await db.fetch_one(
        """
        SELECT 
            (SELECT COUNT(*) FROM referral_codes) as total_codes_created,
            (SELECT COUNT(*) FROM referral_redemptions) as total_successful_referrals,
            (SELECT COALESCE(SUM(referee_bonus + referrer_bonus + milestone_bonus), 0) 
             FROM referral_redemptions) as total_dust_granted
        """
    )

    total_codes = stats["total_codes_created"] or 0
    total_referrals = stats["total_successful_referrals"] or 0
    conversion_rate = (total_referrals / total_codes) if total_codes > 0 else 0.0

    # Get top referrers
    top_referrers_data = await db.fetch_all(
        """
        SELECT 
            rr.referrer_user_id,
            u.fairyname,
            COUNT(*) as successful_referrals,
            SUM(rr.referrer_bonus + rr.milestone_bonus) as total_dust_earned
        FROM referral_redemptions rr
        JOIN users u ON rr.referrer_user_id = u.id
        GROUP BY rr.referrer_user_id, u.fairyname
        ORDER BY successful_referrals DESC
        LIMIT 10
        """
    )

    top_referrers = [
        {
            "user_id": r["referrer_user_id"],
            "fairyname": r["fairyname"],
            "successful_referrals": r["successful_referrals"],
            "total_dust_earned": r["total_dust_earned"],
        }
        for r in top_referrers_data
    ]

    # Get daily stats for last 30 days
    daily_stats_data = await db.fetch_all(
        """
        WITH date_series AS (
            SELECT date_trunc('day', generate_series(
                CURRENT_DATE - INTERVAL '29 days',
                CURRENT_DATE,
                '1 day'::interval
            )) as date
        ),
        codes_created AS (
            SELECT 
                date_trunc('day', created_at) as date,
                COUNT(*) as codes_created
            FROM referral_codes
            WHERE created_at >= CURRENT_DATE - INTERVAL '29 days'
            GROUP BY date_trunc('day', created_at)
        ),
        referrals_completed AS (
            SELECT 
                date_trunc('day', redeemed_at) as date,
                COUNT(*) as successful_referrals,
                SUM(referee_bonus + referrer_bonus + milestone_bonus) as dust_granted
            FROM referral_redemptions
            WHERE redeemed_at >= CURRENT_DATE - INTERVAL '29 days'
            GROUP BY date_trunc('day', redeemed_at)
        )
        SELECT 
            ds.date::date as date,
            COALESCE(cc.codes_created, 0) as codes_created,
            COALESCE(rc.successful_referrals, 0) as successful_referrals,
            COALESCE(rc.dust_granted, 0) as dust_granted
        FROM date_series ds
        LEFT JOIN codes_created cc ON ds.date = cc.date
        LEFT JOIN referrals_completed rc ON ds.date = rc.date
        ORDER BY ds.date
        """
    )

    daily_stats = [
        {
            "date": r["date"].strftime("%Y-%m-%d"),
            "codes_created": r["codes_created"],
            "successful_referrals": r["successful_referrals"],
            "dust_granted": r["dust_granted"],
        }
        for r in daily_stats_data
    ]

    return ReferralSystemStats(
        total_codes_created=total_codes,
        total_successful_referrals=total_referrals,
        conversion_rate=round(conversion_rate, 3),
        total_dust_granted=stats["total_dust_granted"] or 0,
        top_referrers=top_referrers,
        daily_stats=daily_stats,
    )


@referrals_router.get("/codes", response_model=ReferralCodesResponse)
async def get_referral_codes(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[str] = Query(None, regex="^(active|expired|inactive)$"),
    user_search: Optional[str] = Query(None, min_length=1),
    admin_user: TokenData = Depends(require_admin),
    db: Database = Depends(get_db),
):
    """View all referral codes with pagination"""
    offset = (page - 1) * limit

    # Build WHERE conditions
    where_conditions = []
    params = []
    param_count = 1

    if status:
        if status == "active":
            where_conditions.append(f"rc.is_active = true AND rc.expires_at > CURRENT_TIMESTAMP")
        elif status == "expired":
            where_conditions.append(f"rc.expires_at <= CURRENT_TIMESTAMP")
        elif status == "inactive":
            where_conditions.append(f"rc.is_active = false")

    if user_search:
        where_conditions.append(f"u.fairyname ILIKE ${param_count}")
        params.append(f"%{user_search}%")
        param_count += 1

    where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""

    # Get total count
    total_query = f"""
        SELECT COUNT(*) as total
        FROM referral_codes rc
        JOIN users u ON rc.user_id = u.id
        {where_clause}
    """
    total_result = await db.fetch_one(total_query, *params)
    total = total_result["total"]

    # Get codes with pagination
    codes_query = f"""
        SELECT 
            rc.referral_code,
            rc.user_id,
            u.fairyname as user_name,
            rc.created_at,
            CASE 
                WHEN NOT rc.is_active THEN 'inactive'
                WHEN rc.expires_at <= CURRENT_TIMESTAMP THEN 'expired'
                ELSE 'active'
            END as status,
            (SELECT COUNT(*) FROM referral_redemptions WHERE referral_code = rc.referral_code) as successful_referrals
        FROM referral_codes rc
        JOIN users u ON rc.user_id = u.id
        {where_clause}
        ORDER BY rc.created_at DESC
        LIMIT ${param_count} OFFSET ${param_count + 1}
    """
    params.extend([limit, offset])

    codes_data = await db.fetch_all(codes_query, *params)

    codes = [
        {
            "referral_code": r["referral_code"],
            "user_id": r["user_id"],
            "user_name": r["user_name"],
            "created_at": r["created_at"],
            "status": r["status"],
            "successful_referrals": r["successful_referrals"],
        }
        for r in codes_data
    ]

    return ReferralCodesResponse(
        codes=codes,
        total=total,
        page=page,
        page_size=limit,
        has_more=(offset + limit) < total,
    )


@referrals_router.get("/redemptions", response_model=ReferralRedemptionsResponse)
async def get_referral_redemptions(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    date_from: Optional[str] = Query(None, regex=r"^\d{4}-\d{2}-\d{2}$"),
    admin_user: TokenData = Depends(require_admin),
    db: Database = Depends(get_db),
):
    """View all referral redemptions"""
    offset = (page - 1) * limit

    # Build WHERE conditions
    where_conditions = []
    params = []
    param_count = 1

    if date_from:
        where_conditions.append(f"rr.redeemed_at >= ${param_count}")
        params.append(datetime.strptime(date_from, "%Y-%m-%d").date())
        param_count += 1

    where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""

    # Get total count
    total_query = f"""
        SELECT COUNT(*) as total
        FROM referral_redemptions rr
        {where_clause}
    """
    total_result = await db.fetch_one(total_query, *params)
    total = total_result["total"]

    # Get redemptions with pagination
    redemptions_query = f"""
        SELECT 
            rr.referral_code,
            ur.fairyname as referrer_name,
            ue.fairyname as referee_name,
            rr.redeemed_at,
            rr.referee_bonus,
            rr.referrer_bonus
        FROM referral_redemptions rr
        JOIN users ur ON rr.referrer_user_id = ur.id
        JOIN users ue ON rr.referee_user_id = ue.id
        {where_clause}
        ORDER BY rr.redeemed_at DESC
        LIMIT ${param_count} OFFSET ${param_count + 1}
    """
    params.extend([limit, offset])

    redemptions_data = await db.fetch_all(redemptions_query, *params)

    redemptions = [
        {
            "referral_code": r["referral_code"],
            "referrer_name": r["referrer_name"],
            "referee_name": r["referee_name"],
            "redeemed_at": r["redeemed_at"],
            "referee_bonus": r["referee_bonus"],
            "referrer_bonus": r["referrer_bonus"],
        }
        for r in redemptions_data
    ]

    return ReferralRedemptionsResponse(
        redemptions=redemptions,
        total=total,
        page=page,
        page_size=limit,
        has_more=(offset + limit) < total,
    )