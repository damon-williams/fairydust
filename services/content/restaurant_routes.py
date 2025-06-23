# services/content/restaurant_routes.py
import json
import random
import httpx
from datetime import datetime, timedelta
from typing import Optional, List
from uuid import UUID, uuid4
from fastapi import APIRouter, HTTPException, Depends, status
from fastapi.security import HTTPBearer

from models import (
    RestaurantGenerateRequest, RestaurantRegenerateRequest, Restaurant, 
    RestaurantResponse, OpenTableInfo, UserRestaurantPreferences,
    UserRestaurantPreferencesUpdate, PersonRestaurantPreferences,
    ErrorResponse
)
from shared.database import get_db, Database
from shared.auth_middleware import get_current_user, TokenData
from shared.json_utils import safe_json_dumps, parse_jsonb_field
from rate_limiting import check_api_rate_limit_only

security = HTTPBearer()
router = APIRouter()

# Mock restaurant data for top 20 US cities
MOCK_RESTAURANTS = {
    "san_francisco": [
        {
            "id": "mock_sf_001",
            "name": "Tony's Italian Bistro",
            "cuisine": "Italian",
            "address": "1234 Columbus Ave, San Francisco, CA 94133",
            "rating": 4.5,
            "price_level": "$$",
            "phone": "(415) 555-0123",
            "google_place_id": "mock_place_id_001",
        },
        {
            "id": "mock_sf_002", 
            "name": "Golden Dragon",
            "cuisine": "Chinese",
            "address": "567 Grant Ave, San Francisco, CA 94108",
            "rating": 4.2,
            "price_level": "$",
            "phone": "(415) 555-0234",
            "google_place_id": "mock_place_id_002",
        },
        {
            "id": "mock_sf_003",
            "name": "Coastal Seafood",
            "cuisine": "Seafood",
            "address": "890 Fisherman's Wharf, San Francisco, CA 94133",
            "rating": 4.7,
            "price_level": "$$$",
            "phone": "(415) 555-0345",
            "google_place_id": "mock_place_id_003",
        }
    ],
    "new_york": [
        {
            "id": "mock_ny_001",
            "name": "Little Italy Trattoria",
            "cuisine": "Italian", 
            "address": "123 Mulberry St, New York, NY 10013",
            "rating": 4.6,
            "price_level": "$$",
            "phone": "(212) 555-0123",
            "google_place_id": "mock_place_id_004",
        },
        {
            "id": "mock_ny_002",
            "name": "Brooklyn Burger Co",
            "cuisine": "American",
            "address": "456 Atlantic Ave, Brooklyn, NY 11217", 
            "rating": 4.3,
            "price_level": "$",
            "phone": "(718) 555-0234",
            "google_place_id": "mock_place_id_005",
        },
        {
            "id": "mock_ny_003",
            "name": "Sushi Zen",
            "cuisine": "Japanese",
            "address": "789 Madison Ave, New York, NY 10065",
            "rating": 4.8,
            "price_level": "$$$",
            "phone": "(212) 555-0345",
            "google_place_id": "mock_place_id_006",
        }
    ],
    "los_angeles": [
        {
            "id": "mock_la_001",
            "name": "Sunset Tacos",
            "cuisine": "Mexican",
            "address": "1234 Sunset Blvd, Los Angeles, CA 90026",
            "rating": 4.4,
            "price_level": "$",
            "phone": "(323) 555-0123",
            "google_place_id": "mock_place_id_007",
        },
        {
            "id": "mock_la_002",
            "name": "Beverly Hills Steakhouse", 
            "cuisine": "Steakhouse",
            "address": "567 Rodeo Dr, Beverly Hills, CA 90210",
            "rating": 4.9,
            "price_level": "$$$",
            "phone": "(310) 555-0234",
            "google_place_id": "mock_place_id_008",
        },
        {
            "id": "mock_la_003",
            "name": "Venice Beach Cafe",
            "cuisine": "Cafe",
            "address": "890 Ocean Front Walk, Venice, CA 90291",
            "rating": 4.1,
            "price_level": "$$",
            "phone": "(310) 555-0345",
            "google_place_id": "mock_place_id_009",
        }
    ]
}

# Add more cities with similar mock data structure
MOCK_RESTAURANTS.update({
    "chicago": [
        {"id": "mock_chi_001", "name": "Deep Dish Palace", "cuisine": "Pizza", "address": "123 Michigan Ave, Chicago, IL 60601", "rating": 4.5, "price_level": "$$", "phone": "(312) 555-0123", "google_place_id": "mock_place_id_010"},
        {"id": "mock_chi_002", "name": "Windy City Grill", "cuisine": "American", "address": "456 State St, Chicago, IL 60654", "rating": 4.2, "price_level": "$", "phone": "(312) 555-0234", "google_place_id": "mock_place_id_011"},
        {"id": "mock_chi_003", "name": "Lakefront Seafood", "cuisine": "Seafood", "address": "789 Lake Shore Dr, Chicago, IL 60611", "rating": 4.7, "price_level": "$$$", "phone": "(312) 555-0345", "google_place_id": "mock_place_id_012"}
    ],
    "miami": [
        {"id": "mock_mia_001", "name": "South Beach Bistro", "cuisine": "Cuban", "address": "123 Ocean Dr, Miami Beach, FL 33139", "rating": 4.3, "price_level": "$$", "phone": "(305) 555-0123", "google_place_id": "mock_place_id_013"},
        {"id": "mock_mia_002", "name": "Little Havana", "cuisine": "Cuban", "address": "456 Calle Ocho, Miami, FL 33135", "rating": 4.6, "price_level": "$", "phone": "(305) 555-0234", "google_place_id": "mock_place_id_014"},
        {"id": "mock_mia_003", "name": "Biscayne Steakhouse", "cuisine": "Steakhouse", "address": "789 Biscayne Blvd, Miami, FL 33132", "rating": 4.8, "price_level": "$$$", "phone": "(305) 555-0345", "google_place_id": "mock_place_id_015"}
    ]
})

def get_city_key(address: str) -> str:
    """Extract city key from address for mock data lookup"""
    address_lower = address.lower()
    if "san francisco" in address_lower or "sf" in address_lower:
        return "san_francisco"
    elif "new york" in address_lower or "brooklyn" in address_lower or "manhattan" in address_lower:
        return "new_york"
    elif "los angeles" in address_lower or "la" in address_lower or "beverly hills" in address_lower or "venice" in address_lower:
        return "los_angeles"
    elif "chicago" in address_lower:
        return "chicago"
    elif "miami" in address_lower:
        return "miami"
    else:
        # Default to San Francisco for other locations
        return "san_francisco"

def calculate_distance(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Calculate approximate distance in miles between two coordinates"""
    # Simple approximation for mock data
    return round(random.uniform(0.5, 5.0), 1)

def generate_opentable_info(restaurant_name: str, city: str, time_preference: str = None) -> OpenTableInfo:
    """Generate OpenTable information for a restaurant"""
    # Most upscale restaurants accept reservations
    has_reservations = random.choice([True, True, True, False])  # 75% chance
    
    available_times = []
    if has_reservations and time_preference != "now":
        # Generate realistic available times
        if time_preference == "tonight":
            times = ["6:00 PM", "6:30 PM", "7:30 PM", "8:00 PM", "8:30 PM"]
        else:
            times = ["5:30 PM", "6:00 PM", "6:30 PM", "7:00 PM", "7:30 PM", "8:00 PM", "8:30 PM", "9:00 PM"]
        available_times = random.sample(times, random.randint(2, 4))
    
    # Generate OpenTable deep link
    city_clean = city.replace("_", " ").title()
    booking_url = f"https://www.opentable.com/s?query={restaurant_name.replace(' ', '%20')}&location={city_clean.replace(' ', '%20')}"
    
    return OpenTableInfo(
        has_reservations=has_reservations,
        available_times=available_times,
        booking_url=booking_url
    )

async def generate_ai_highlights(restaurant: dict, preferences: dict, people_data: List[dict]) -> List[str]:
    """Generate AI-powered restaurant highlights based on preferences and people data"""
    highlights = []
    
    # Basic highlights based on restaurant type
    cuisine = restaurant["cuisine"].lower()
    price_level = restaurant["price_level"]
    party_size = preferences.get("party_size", 2)
    
    if party_size >= 6:
        highlights.append("Great for large groups")
    elif party_size >= 4:
        highlights.append("Perfect for small groups")
    
    if price_level == "$":
        highlights.append("Budget-friendly")
    elif price_level == "$$$":
        highlights.append("Upscale dining experience")
    
    # Cuisine-specific highlights
    if "italian" in cuisine:
        highlights.append("Authentic Italian cuisine")
        if any("vegetarian" in person.get("notes", "").lower() for person in people_data):
            highlights.append("Vegetarian pasta options")
    elif "chinese" in cuisine or "asian" in cuisine:
        highlights.append("Traditional flavors")
        highlights.append("Shareable dishes")
    elif "mexican" in cuisine:
        highlights.append("Fresh ingredients")
        highlights.append("Vibrant atmosphere")
    elif "seafood" in cuisine:
        highlights.append("Fresh catch daily")
        highlights.append("Ocean-to-table dining")
    
    # Special occasion handling
    special_occasion = preferences.get("special_occasion", "").lower()
    if "birthday" in special_occasion:
        highlights.append("Birthday-friendly atmosphere")
    elif "anniversary" in special_occasion:
        highlights.append("Romantic setting")
    elif "date" in special_occasion:
        highlights.append("Perfect for dates")
    
    # People preferences
    for person in people_data:
        notes = person.get("notes", "").lower()
        if "high chair" in notes or "kids" in notes:
            highlights.append("Family-friendly")
        if "vegetarian" in notes or "vegan" in notes:
            highlights.append("Vegetarian options")
        if "gluten" in notes:
            highlights.append("Gluten-free options")
    
    return highlights[:3]  # Limit to 3 highlights

async def consume_dust_for_restaurant_search(user_id: UUID) -> bool:
    """Consume DUST for restaurant search via Ledger Service"""
    try:
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://fairydust-ledger-production.up.railway.app/transactions/consume",
                json={
                    "user_id": str(user_id),
                    "amount": 3,
                    "app_id": "fairydust-restaurant",
                    "description": "Restaurant search"
                },
                timeout=10.0
            )
            return response.status_code == 200
    except Exception as e:
        print(f"Failed to consume DUST: {e}")
        return False

async def get_people_data(user_id: UUID, selected_people: List[UUID]) -> List[dict]:
    """Fetch people data from Identity Service"""
    if not selected_people:
        return []
    
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://fairydust-identity-production.up.railway.app/users/{user_id}/people",
                timeout=10.0
            )
            if response.status_code == 200:
                all_people = response.json().get("people", [])
                # Filter to selected people and include relevant preference data
                selected_people_data = []
                for person in all_people:
                    if person["id"] in [str(pid) for pid in selected_people]:
                        # Get dining preferences from profile data
                        dining_prefs = {}
                        for profile_item in person.get("profile_data", []):
                            if profile_item.get("category") in ["dining_preferences", "favorite_restaurants"]:
                                dining_prefs[profile_item["category"]] = profile_item.get("field_value", {})
                        
                        selected_people_data.append({
                            "id": person["id"],
                            "name": person["name"],
                            "relationship": person["relationship"],
                            "notes": dining_prefs.get("dining_preferences", {}).get("notes", ""),
                            "favorite_restaurants": dining_prefs.get("favorite_restaurants", {}).get("restaurants", [])
                        })
                return selected_people_data
    except Exception as e:
        print(f"Failed to fetch people data: {e}")
    
    return []

@router.post("/generate", response_model=RestaurantResponse)
async def generate_restaurants(
    request: RestaurantGenerateRequest,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Generate restaurant recommendations based on location and preferences"""
    
    # Verify user matches the request
    if str(current_user.user_id) != str(request.user_id):
        raise HTTPException(status_code=403, detail="Cannot generate restaurants for other users")
    
    # Rate limiting check
    await check_api_rate_limit_only(current_user.user_id, "restaurant_generate", db)
    
    # Consume DUST for the search
    dust_consumed = await consume_dust_for_restaurant_search(request.user_id)
    if not dust_consumed:
        raise HTTPException(
            status_code=402, 
            detail="Insufficient DUST balance or payment processing failed"
        )
    
    # Get people data for personalization
    people_data = await get_people_data(request.user_id, request.selected_people)
    
    # Create or get session
    session_id = request.session_id or uuid4()
    session_expires = datetime.utcnow() + timedelta(hours=24)
    
    # Store session in database
    await db.execute("""
        INSERT INTO restaurant_sessions (id, user_id, session_data, excluded_restaurants, expires_at)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (id) DO UPDATE SET
            session_data = EXCLUDED.session_data,
            expires_at = EXCLUDED.expires_at
    """, session_id, request.user_id, 
        safe_json_dumps({"location": request.location.dict(), "preferences": request.preferences.dict()}),
        [], session_expires)
    
    # Get mock restaurants based on location
    city_key = get_city_key(request.location.address)
    available_restaurants = MOCK_RESTAURANTS.get(city_key, MOCK_RESTAURANTS["san_francisco"])
    
    # Filter based on preferences
    filtered_restaurants = available_restaurants.copy()
    
    if request.preferences.cuisine_types:
        cuisine_types_lower = [c.lower() for c in request.preferences.cuisine_types]
        filtered_restaurants = [
            r for r in filtered_restaurants 
            if any(cuisine.lower() in r["cuisine"].lower() for cuisine in cuisine_types_lower)
        ]
    
    # Select 3 diverse restaurants
    selected_restaurants = random.sample(
        filtered_restaurants if len(filtered_restaurants) >= 3 else available_restaurants,
        min(3, len(filtered_restaurants) if filtered_restaurants else len(available_restaurants))
    )
    
    # Build restaurant response objects
    restaurants = []
    for restaurant_data in selected_restaurants:
        # Calculate distance
        distance = calculate_distance(
            request.location.latitude, request.location.longitude,
            0, 0  # Mock coordinates
        )
        
        # Generate OpenTable info
        opentable_info = generate_opentable_info(
            restaurant_data["name"], 
            city_key,
            request.preferences.time_preference
        )
        
        # Generate AI highlights
        highlights = await generate_ai_highlights(
            restaurant_data,
            request.preferences.dict(),
            people_data
        )
        
        restaurant = Restaurant(
            id=restaurant_data["id"],
            name=restaurant_data["name"],
            cuisine=restaurant_data["cuisine"],
            address=restaurant_data["address"],
            distance_miles=distance,
            price_level=restaurant_data["price_level"],
            rating=restaurant_data["rating"],
            phone=restaurant_data["phone"],
            google_place_id=restaurant_data["google_place_id"],
            opentable=opentable_info,
            highlights=highlights
        )
        restaurants.append(restaurant)
    
    return RestaurantResponse(
        restaurants=restaurants,
        session_id=session_id,
        generated_at=datetime.utcnow()
    )

@router.post("/regenerate", response_model=RestaurantResponse)
async def regenerate_restaurants(
    request: RestaurantRegenerateRequest,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Regenerate restaurants within an existing session (free)"""
    
    # Get existing session
    session = await db.fetch_one("""
        SELECT * FROM restaurant_sessions 
        WHERE id = $1 AND user_id = $2 AND expires_at > CURRENT_TIMESTAMP
    """, request.session_id, current_user.user_id)
    
    if not session:
        raise HTTPException(status_code=404, detail="Session not found or expired")
    
    # Rate limiting check
    await check_api_rate_limit_only(current_user.user_id, "restaurant_regenerate", db)
    
    # Parse session data
    session_data = session["session_data"]
    location_data = session_data["location"]
    preferences_data = session_data["preferences"]
    
    # Update excluded restaurants
    current_excluded = session.get("excluded_restaurants", [])
    updated_excluded = list(set(current_excluded + request.exclude_restaurants))
    
    await db.execute("""
        UPDATE restaurant_sessions 
        SET excluded_restaurants = $1
        WHERE id = $2
    """, updated_excluded, request.session_id)
    
    # Get mock restaurants based on original location
    city_key = get_city_key(location_data["address"])
    available_restaurants = MOCK_RESTAURANTS.get(city_key, MOCK_RESTAURANTS["san_francisco"])
    
    # Filter out excluded restaurants
    filtered_restaurants = [
        r for r in available_restaurants 
        if r["id"] not in updated_excluded
    ]
    
    if len(filtered_restaurants) < 3:
        # If we've excluded too many, reset and show different ones
        filtered_restaurants = available_restaurants
    
    # Apply cuisine preferences if they exist
    if preferences_data.get("cuisine_types"):
        cuisine_types_lower = [c.lower() for c in preferences_data["cuisine_types"]]
        cuisine_filtered = [
            r for r in filtered_restaurants 
            if any(cuisine.lower() in r["cuisine"].lower() for cuisine in cuisine_types_lower)
        ]
        if cuisine_filtered:
            filtered_restaurants = cuisine_filtered
    
    # Select 3 different restaurants
    selected_restaurants = random.sample(
        filtered_restaurants,
        min(3, len(filtered_restaurants))
    )
    
    # Get people data for highlights
    selected_people = []  # Would need to store this in session for full implementation
    people_data = await get_people_data(current_user.user_id, selected_people)
    
    # Build restaurant response objects
    restaurants = []
    for restaurant_data in selected_restaurants:
        distance = calculate_distance(
            location_data["latitude"], location_data["longitude"],
            0, 0  # Mock coordinates
        )
        
        opentable_info = generate_opentable_info(
            restaurant_data["name"], 
            city_key,
            preferences_data.get("time_preference")
        )
        
        highlights = await generate_ai_highlights(
            restaurant_data,
            preferences_data,
            people_data
        )
        
        restaurant = Restaurant(
            id=restaurant_data["id"],
            name=restaurant_data["name"],
            cuisine=restaurant_data["cuisine"],
            address=restaurant_data["address"],
            distance_miles=distance,
            price_level=restaurant_data["price_level"],
            rating=restaurant_data["rating"],
            phone=restaurant_data["phone"],
            google_place_id=restaurant_data["google_place_id"],
            opentable=opentable_info,
            highlights=highlights
        )
        restaurants.append(restaurant)
    
    return RestaurantResponse(
        restaurants=restaurants,
        session_id=request.session_id,
        generated_at=datetime.utcnow()
    )

@router.get("/preferences/{user_id}", response_model=UserRestaurantPreferences)
async def get_restaurant_preferences(
    user_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Get user's restaurant preferences"""
    
    # Verify user access
    if str(current_user.user_id) != str(user_id):
        raise HTTPException(status_code=403, detail="Cannot access other users' preferences")
    
    # Get people data from Identity Service
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://fairydust-identity-production.up.railway.app/users/{user_id}/people",
                timeout=10.0
            )
            people_data = response.json().get("people", []) if response.status_code == 200 else []
    except Exception as e:
        print(f"Failed to fetch people data: {e}")
        people_data = []
    
    # Build people preferences from profile data
    people_preferences = []
    for person in people_data:
        favorite_restaurants = []
        notes = ""
        
        # Extract dining preferences from profile data
        for profile_item in person.get("profile_data", []):
            if profile_item.get("category") == "favorite_restaurants":
                favorite_restaurants = profile_item.get("field_value", {}).get("restaurants", [])
            elif profile_item.get("category") == "dining_preferences":
                notes = profile_item.get("field_value", {}).get("notes", "")
        
        people_preferences.append(PersonRestaurantPreferences(
            person_id=UUID(person["id"]),
            favorite_restaurants=favorite_restaurants,
            notes=notes
        ))
    
    # Get personal preferences (you could store these in user profile or separate table)
    # For now, return defaults
    personal_preferences = {
        "default_radius": "10mi",
        "preferred_cuisines": []
    }
    
    return UserRestaurantPreferences(
        personal_preferences=personal_preferences,
        people_preferences=people_preferences
    )

@router.put("/preferences/{user_id}", response_model=UserRestaurantPreferences)
async def update_restaurant_preferences(
    user_id: UUID,
    preferences: UserRestaurantPreferencesUpdate,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Update user's restaurant preferences"""
    
    # Verify user access
    if str(current_user.user_id) != str(user_id):
        raise HTTPException(status_code=403, detail="Cannot update other users' preferences")
    
    # Update people preferences via Identity Service
    if preferences.people_preferences:
        for person_pref in preferences.people_preferences:
            try:
                async with httpx.AsyncClient() as client:
                    # Update favorite restaurants
                    if person_pref.favorite_restaurants:
                        await client.put(
                            f"https://fairydust-identity-production.up.railway.app/users/{user_id}/people/{person_pref.person_id}/profile",
                            json={
                                "category": "favorite_restaurants",
                                "field_name": "restaurants",
                                "field_value": {"restaurants": person_pref.favorite_restaurants}
                            },
                            timeout=10.0
                        )
                    
                    # Update dining notes
                    if person_pref.notes:
                        await client.put(
                            f"https://fairydust-identity-production.up.railway.app/users/{user_id}/people/{person_pref.person_id}/profile",
                            json={
                                "category": "dining_preferences",
                                "field_name": "notes",
                                "field_value": {"notes": person_pref.notes}
                            },
                            timeout=10.0
                        )
            except Exception as e:
                print(f"Failed to update people preferences: {e}")
    
    # Return updated preferences
    return await get_restaurant_preferences(user_id, current_user, db)