# services/admin/routes/referrals.py
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from auth import get_current_admin_user
from models import (
    ReferralConfig,
    ReferralConfigUpdate,
    ReferralCodesResponse,
    ReferralRedemptionsResponse,
    ReferralSystemStats,
    PromotionalReferralCode,
    PromotionalReferralCodeCreate,
    PromotionalReferralCodeUpdate,
    PromotionalReferralCodesResponse,
    PromotionalReferralRedemptionsResponse,
)
from shared.database import Database, get_db

referrals_router = APIRouter()


@referrals_router.get("/config", response_model=ReferralConfig)
async def get_referral_config(
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Get current referral system configuration"""
    config_data = await db.fetch_one(
        "SELECT * FROM referral_system_config WHERE id = 1"
    )
    
    if not config_data:
        raise HTTPException(status_code=404, detail="Referral configuration not found")
    
    import json
    
    # Parse milestone_rewards if it's a string
    milestone_rewards = config_data["milestone_rewards"]
    if isinstance(milestone_rewards, str):
        milestone_rewards = json.loads(milestone_rewards)
    
    return ReferralConfig(
        referee_bonus=config_data["referee_bonus"],
        referrer_bonus=config_data["referrer_bonus"],
        milestone_rewards=milestone_rewards,
        code_expiry_days=config_data["code_expiry_days"],
        max_referrals_per_user=config_data["max_referrals_per_user"],
        system_enabled=config_data["system_enabled"],
    )


@referrals_router.put("/config", response_model=ReferralConfig)
async def update_referral_config(
    config_update: ReferralConfigUpdate,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Update referral system configuration"""
    import json
    
    # Get current configuration
    current_config_data = await db.fetch_one(
        "SELECT * FROM referral_system_config WHERE id = 1"
    )
    
    if not current_config_data:
        raise HTTPException(status_code=404, detail="Referral configuration not found")
    
    # Build update query
    update_fields = []
    params = []
    param_count = 1
    
    if config_update.referee_bonus is not None:
        update_fields.append(f"referee_bonus = ${param_count}")
        params.append(config_update.referee_bonus)
        param_count += 1
        
    if config_update.referrer_bonus is not None:
        update_fields.append(f"referrer_bonus = ${param_count}")
        params.append(config_update.referrer_bonus)
        param_count += 1
        
    if config_update.milestone_rewards is not None:
        update_fields.append(f"milestone_rewards = ${param_count}")
        params.append(json.dumps(config_update.milestone_rewards))
        param_count += 1
        
    if config_update.code_expiry_days is not None:
        update_fields.append(f"code_expiry_days = ${param_count}")
        params.append(config_update.code_expiry_days)
        param_count += 1
        
    if config_update.max_referrals_per_user is not None:
        update_fields.append(f"max_referrals_per_user = ${param_count}")
        params.append(config_update.max_referrals_per_user)
        param_count += 1
        
    if config_update.system_enabled is not None:
        update_fields.append(f"system_enabled = ${param_count}")
        params.append(config_update.system_enabled)
        param_count += 1
    
    if not update_fields:
        # No updates, return current config
        # Parse milestone_rewards if it's a string
        milestone_rewards = current_config_data["milestone_rewards"]
        if isinstance(milestone_rewards, str):
            milestone_rewards = json.loads(milestone_rewards)
            
        return ReferralConfig(
            referee_bonus=current_config_data["referee_bonus"],
            referrer_bonus=current_config_data["referrer_bonus"],
            milestone_rewards=milestone_rewards,
            code_expiry_days=current_config_data["code_expiry_days"],
            max_referrals_per_user=current_config_data["max_referrals_per_user"],
            system_enabled=current_config_data["system_enabled"],
        )
    
    # Update configuration
    update_fields.append(f"updated_at = CURRENT_TIMESTAMP")
    params.append(1)  # WHERE id = 1
    
    await db.execute(
        f"""
        UPDATE referral_system_config 
        SET {', '.join(update_fields)} 
        WHERE id = ${param_count}
        """,
        *params
    )
    
    # Return updated configuration
    updated_config_data = await db.fetch_one(
        "SELECT * FROM referral_system_config WHERE id = 1"
    )
    
    # Parse milestone_rewards if it's a string
    milestone_rewards = updated_config_data["milestone_rewards"]
    if isinstance(milestone_rewards, str):
        milestone_rewards = json.loads(milestone_rewards)
    
    return ReferralConfig(
        referee_bonus=updated_config_data["referee_bonus"],
        referrer_bonus=updated_config_data["referrer_bonus"],
        milestone_rewards=milestone_rewards,
        code_expiry_days=updated_config_data["code_expiry_days"],
        max_referrals_per_user=updated_config_data["max_referrals_per_user"],
        system_enabled=updated_config_data["system_enabled"],
    )


@referrals_router.get("/stats", response_model=ReferralSystemStats)
async def get_referral_system_stats(
    admin_user: dict = Depends(get_current_admin_user),
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
    admin_user: dict = Depends(get_current_admin_user),
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
    admin_user: dict = Depends(get_current_admin_user),
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


# Promotional referral codes endpoints
@referrals_router.get("/promotional-codes", response_model=PromotionalReferralCodesResponse)
async def get_promotional_codes(
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    status: Optional[str] = Query(None, regex="^(active|expired|inactive)$"),
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """View all promotional referral codes with pagination"""
    offset = (page - 1) * limit

    # Build WHERE conditions
    where_conditions = []
    params = []
    param_count = 1

    if status:
        if status == "active":
            where_conditions.append("is_active = true AND expires_at > CURRENT_TIMESTAMP")
        elif status == "expired":
            where_conditions.append("expires_at <= CURRENT_TIMESTAMP")
        elif status == "inactive":
            where_conditions.append("is_active = false")

    where_clause = "WHERE " + " AND ".join(where_conditions) if where_conditions else ""

    # Get total count
    total_query = f"""
        SELECT COUNT(*) as total
        FROM promotional_referral_codes
        {where_clause}
    """
    total_result = await db.fetch_one(total_query, *params)
    total = total_result["total"]

    # Get codes with pagination
    codes_query = f"""
        SELECT 
            id, code, description, dust_bonus, max_uses, current_uses,
            created_by, created_at, expires_at, is_active
        FROM promotional_referral_codes
        {where_clause}
        ORDER BY created_at DESC
        LIMIT ${param_count} OFFSET ${param_count + 1}
    """
    params.extend([limit, offset])

    codes_data = await db.fetch_all(codes_query, *params)

    codes = [
        PromotionalReferralCode(
            id=r["id"],
            code=r["code"],
            description=r["description"],
            dust_bonus=r["dust_bonus"],
            max_uses=r["max_uses"],
            current_uses=r["current_uses"],
            created_by=r["created_by"],
            created_at=r["created_at"],
            expires_at=r["expires_at"],
            is_active=r["is_active"],
        )
        for r in codes_data
    ]

    return PromotionalReferralCodesResponse(
        codes=codes,
        total=total,
        page=page,
        page_size=limit,
        has_more=(offset + limit) < total,
    )


@referrals_router.post("/promotional-codes-debug")
async def debug_promotional_code_create(request: Request):
    """Debug endpoint to see raw request data"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        body = await request.body()
        import json
        raw_data = json.loads(body) if body else {}
        logger.info(f"Debug - Raw request body: {raw_data}")
        return {"received_data": raw_data}
    except Exception as e:
        logger.error(f"Debug - Could not parse request body: {e}")
        return {"error": str(e)}

@referrals_router.post("/promotional-codes", response_model=PromotionalReferralCode)
async def create_promotional_code(
    code_create: PromotionalReferralCodeCreate,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Create a new promotional referral code"""
    import logging
    logger = logging.getLogger(__name__)
    logger.info(f"Creating promotional code with data: {code_create}")
    logger.info(f"Raw data types: code={type(code_create.code)}, description={type(code_create.description)}, dust_bonus={type(code_create.dust_bonus)}, max_uses={type(code_create.max_uses)}, expires_at={type(code_create.expires_at)}")
    # Check if code already exists
    existing_code = await db.fetch_one(
        "SELECT id FROM promotional_referral_codes WHERE code = $1",
        code_create.code.upper(),
    )
    
    if existing_code:
        raise HTTPException(status_code=400, detail="Promotional code already exists")

    # Insert new promotional code
    result = await db.fetch_one(
        """
        INSERT INTO promotional_referral_codes (
            code, description, dust_bonus, max_uses, created_by, expires_at
        ) VALUES ($1, $2, $3, $4, $5, $6)
        RETURNING id
        """,
        code_create.code.upper(),
        code_create.description,
        code_create.dust_bonus,
        code_create.max_uses,
        admin_user["id"],
        code_create.expires_at,
    )
    
    if not result:
        raise HTTPException(status_code=500, detail="Failed to create promotional code")
    
    code_id = result["id"]

    # Fetch the created code
    created_code = await db.fetch_one(
        """
        SELECT id, code, description, dust_bonus, max_uses, current_uses,
               created_by, created_at, expires_at, is_active
        FROM promotional_referral_codes
        WHERE id = $1
        """,
        code_id,
    )

    return PromotionalReferralCode(
        id=created_code["id"],
        code=created_code["code"],
        description=created_code["description"],
        dust_bonus=created_code["dust_bonus"],
        max_uses=created_code["max_uses"],
        current_uses=created_code["current_uses"],
        created_by=created_code["created_by"],
        created_at=created_code["created_at"],
        expires_at=created_code["expires_at"],
        is_active=created_code["is_active"],
    )


@referrals_router.put("/promotional-codes/{code_id}", response_model=PromotionalReferralCode)
async def update_promotional_code(
    code_id: str,
    code_update: PromotionalReferralCodeUpdate,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Update a promotional referral code"""
    # Check if code exists
    existing_code = await db.fetch_one(
        "SELECT * FROM promotional_referral_codes WHERE id = $1",
        code_id,
    )
    
    if not existing_code:
        raise HTTPException(status_code=404, detail="Promotional code not found")

    # Build update query
    update_fields = []
    params = []
    param_count = 1

    if code_update.description is not None:
        update_fields.append(f"description = ${param_count}")
        params.append(code_update.description)
        param_count += 1

    if code_update.dust_bonus is not None:
        update_fields.append(f"dust_bonus = ${param_count}")
        params.append(code_update.dust_bonus)
        param_count += 1

    if code_update.max_uses is not None:
        update_fields.append(f"max_uses = ${param_count}")
        params.append(code_update.max_uses)
        param_count += 1

    if code_update.expires_at is not None:
        update_fields.append(f"expires_at = ${param_count}")
        params.append(code_update.expires_at)
        param_count += 1

    if code_update.is_active is not None:
        update_fields.append(f"is_active = ${param_count}")
        params.append(code_update.is_active)
        param_count += 1

    if not update_fields:
        raise HTTPException(status_code=400, detail="No fields to update")

    # Update the code
    params.append(code_id)
    await db.execute(
        f"""
        UPDATE promotional_referral_codes
        SET {', '.join(update_fields)}
        WHERE id = ${param_count}
        """,
        *params,
    )

    # Fetch the updated code
    updated_code = await db.fetch_one(
        """
        SELECT id, code, description, dust_bonus, max_uses, current_uses,
               created_by, created_at, expires_at, is_active
        FROM promotional_referral_codes
        WHERE id = $1
        """,
        code_id,
    )

    return PromotionalReferralCode(
        id=updated_code["id"],
        code=updated_code["code"],
        description=updated_code["description"],
        dust_bonus=updated_code["dust_bonus"],
        max_uses=updated_code["max_uses"],
        current_uses=updated_code["current_uses"],
        created_by=updated_code["created_by"],
        created_at=updated_code["created_at"],
        expires_at=updated_code["expires_at"],
        is_active=updated_code["is_active"],
    )


@referrals_router.delete("/promotional-codes/{code_id}")
async def delete_promotional_code(
    code_id: str,
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """Delete a promotional referral code"""
    # Check if code exists
    existing_code = await db.fetch_one(
        "SELECT id FROM promotional_referral_codes WHERE id = $1",
        code_id,
    )
    
    if not existing_code:
        raise HTTPException(status_code=404, detail="Promotional code not found")

    # Delete the code
    await db.execute(
        "DELETE FROM promotional_referral_codes WHERE id = $1",
        code_id,
    )

    return {"message": "Promotional code deleted successfully"}


@referrals_router.get("/promotional-codes/{code_id}/redemptions", response_model=PromotionalReferralRedemptionsResponse)
async def get_promotional_code_redemptions(
    code_id: str,
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    admin_user: dict = Depends(get_current_admin_user),
    db: Database = Depends(get_db),
):
    """View redemptions for a specific promotional code"""
    offset = (page - 1) * limit

    # Get the promotional code
    promo_code = await db.fetch_one(
        "SELECT code FROM promotional_referral_codes WHERE id = $1",
        code_id,
    )
    
    if not promo_code:
        raise HTTPException(status_code=404, detail="Promotional code not found")

    # Get total count
    total_result = await db.fetch_one(
        "SELECT COUNT(*) as total FROM promotional_referral_redemptions WHERE promotional_code = $1",
        promo_code["code"],
    )
    total = total_result["total"]

    # Get redemptions with pagination
    redemptions_query = """
        SELECT 
            prr.id,
            prr.promotional_code,
            prr.user_id,
            u.fairyname as user_name,
            prr.dust_bonus,
            prr.redeemed_at
        FROM promotional_referral_redemptions prr
        JOIN users u ON prr.user_id = u.id
        WHERE prr.promotional_code = $1
        ORDER BY prr.redeemed_at DESC
        LIMIT $2 OFFSET $3
    """
    
    redemptions_data = await db.fetch_all(redemptions_query, promo_code["code"], limit, offset)

    redemptions = [
        {
            "id": r["id"],
            "promotional_code": r["promotional_code"],
            "user_id": r["user_id"],
            "user_name": r["user_name"],
            "dust_bonus": r["dust_bonus"],
            "redeemed_at": r["redeemed_at"],
        }
        for r in redemptions_data
    ]

    return PromotionalReferralRedemptionsResponse(
        redemptions=redemptions,
        total=total,
        page=page,
        page_size=limit,
        has_more=(offset + limit) < total,
    )