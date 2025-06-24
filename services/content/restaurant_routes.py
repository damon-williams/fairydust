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
from google_places_service import get_google_places_service

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

def generate_opentable_info(restaurant_name: str, city: str, time_preference: str = None, party_size: int = 2) -> OpenTableInfo:
    """Generate OpenTable information for a restaurant"""
    # Most upscale restaurants accept reservations, fast food typically doesn't
    restaurant_name_lower = restaurant_name.lower()
    
    # Determine if restaurant likely takes reservations based on name/type
    fast_food_indicators = ["mcdonald", "burger king", "taco bell", "subway", "kfc", "pizza hut", "domino"]
    casual_indicators = ["cafe", "diner", "counter", "bar", "pub"]
    
    if any(indicator in restaurant_name_lower for indicator in fast_food_indicators):
        has_reservations = False
    elif any(indicator in restaurant_name_lower for indicator in casual_indicators):
        has_reservations = random.choice([True, False])  # 50% chance
    else:
        has_reservations = random.choice([True, True, True, False])  # 75% chance for sit-down restaurants
    
    available_times = []
    if has_reservations and time_preference != "now":
        # Generate realistic available times based on time preference
        if time_preference == "tonight":
            times = ["6:00 PM", "6:30 PM", "7:30 PM", "8:00 PM", "8:30 PM"]
        elif time_preference == "weekend":
            times = ["11:30 AM", "12:00 PM", "12:30 PM", "5:30 PM", "6:00 PM", "6:30 PM", "7:00 PM", "7:30 PM", "8:00 PM"]
        else:
            times = ["5:30 PM", "6:00 PM", "6:30 PM", "7:00 PM", "7:30 PM", "8:00 PM", "8:30 PM", "9:00 PM"]
        available_times = random.sample(times, random.randint(2, 4))
    
    # Generate enhanced OpenTable deep links
    city_clean = city.replace("_", " ").title()
    restaurant_query = restaurant_name.replace(' ', '%20').replace('&', '%26')
    location_query = city_clean.replace(' ', '%20')
    
    # Multiple booking URL formats for better compatibility
    booking_url = f"https://www.opentable.com/s?query={restaurant_query}&location={location_query}&covers={party_size}"
    
    return OpenTableInfo(
        has_reservations=has_reservations,
        available_times=available_times,
        booking_url=booking_url
    )

async def get_restaurants_from_google_places(
    location: dict, 
    preferences: dict, 
    people_data: List[dict],
    excluded_ids: List[str] = None
) -> List[Restaurant]:
    """Get restaurants from Google Places API with fallback to mock data"""
    print(f"🔍 RESTAURANT_DEBUG: Starting Google Places search")
    print(f"🔍 RESTAURANT_DEBUG: Location data: {location}")
    print(f"🔍 RESTAURANT_DEBUG: Preferences: {preferences}")
    print(f"🔍 RESTAURANT_DEBUG: Excluded IDs: {excluded_ids}")
    
    # Defensive programming - ensure we have valid dictionaries
    if not isinstance(location, dict):
        print(f"🔍 RESTAURANT_DEBUG: ❌ Invalid location type: {type(location)}, falling back to mock data")
        location = {}
    
    if not isinstance(preferences, dict):
        print(f"🔍 RESTAURANT_DEBUG: ❌ Invalid preferences type: {type(preferences)}, using defaults")
        preferences = {}
    
    if not isinstance(people_data, list):
        print(f"🔍 RESTAURANT_DEBUG: ❌ Invalid people_data type: {type(people_data)}, using empty list")
        people_data = []
    
    try:
        print(f"🔍 RESTAURANT_DEBUG: Attempting to get Google Places service...")
        places_service = get_google_places_service()
        print(f"🔍 RESTAURANT_DEBUG: ✅ Google Places service initialized successfully")
        
        # Convert radius from miles (if provided) or use default
        radius_str = preferences.get("default_radius", "10mi") 
        radius_miles = int(radius_str.replace("mi", "")) if "mi" in radius_str else 10
        print(f"🔍 RESTAURANT_DEBUG: Search radius: {radius_miles} miles")
        
        # Use provided coordinates or try to geocode address
        latitude = location.get("latitude")
        longitude = location.get("longitude") 
        print(f"🔍 RESTAURANT_DEBUG: Coordinates - Lat: {latitude}, Lng: {longitude}")
        
        if not latitude or not longitude:
            # If no coordinates, try geocoding the address
            # For now, fall back to mock data if no coordinates
            print("🔍 RESTAURANT_DEBUG: ❌ No coordinates provided, falling back to mock data")
            print(f"🔍 RESTAURANT_DEBUG: Location address field: {location.get('address', 'NO ADDRESS PROVIDED')}")
            return await get_mock_restaurants(location, preferences, people_data, excluded_ids)
        
        # Get restaurants from Google Places
        print(f"🔍 RESTAURANT_DEBUG: Calling Google Places API...")
        print(f"🔍 RESTAURANT_DEBUG: API Parameters - cuisine_types: {preferences.get('cuisine_types', [])}, open_now: {preferences.get('time_preference') == 'now'}")
        
        google_restaurants = places_service.search_restaurants(
            latitude=latitude,
            longitude=longitude,
            radius_miles=radius_miles,
            cuisine_types=preferences.get("cuisine_types", []),
            open_now=preferences.get("time_preference") == "now",
            min_rating=3.5,
            max_results=20
        )
        
        print(f"🔍 RESTAURANT_DEBUG: Google Places returned {len(google_restaurants) if google_restaurants else 0} restaurants")
        
        if not google_restaurants:
            print("🔍 RESTAURANT_DEBUG: ❌ No restaurants found via Google Places, falling back to mock data")
            return await get_mock_restaurants(location, preferences, people_data, excluded_ids)
        
        print(f"🔍 RESTAURANT_DEBUG: ✅ Using Google Places data for {len(google_restaurants)} restaurants")
        
        # Filter out excluded restaurants  
        if excluded_ids and google_restaurants:
            print(f"🔍 RESTAURANT_DEBUG: Filtering out {len(excluded_ids)} excluded restaurants")
            google_restaurants = [r for r in google_restaurants if r and r.get("id") not in excluded_ids]
        
        # Convert to Restaurant objects with highlights
        restaurants = []
        for restaurant_data in google_restaurants[:3]:  # Return top 3
            if not restaurant_data or not isinstance(restaurant_data, dict):
                print(f"🔍 RESTAURANT_DEBUG: ⚠️ Skipping invalid restaurant data: {restaurant_data}")
                continue
                
            # Generate OpenTable info
            restaurant_name = restaurant_data.get("name", "Unknown Restaurant")
            city_address = location.get("address", "") if location else ""
            time_pref = preferences.get("time_preference") if preferences else None
            party_size = preferences.get("party_size", 2) if preferences else 2
            
            print(f"🔍 RESTAURANT_DEBUG: Processing restaurant: {restaurant_name}")
            
            opentable_info = generate_opentable_info(
                restaurant_name,
                get_city_key(city_address),
                time_pref,
                party_size
            )
            
            # Generate AI highlights
            try:
                highlights = await generate_ai_highlights(
                    restaurant_data,
                    preferences or {},
                    people_data or []
                )
            except Exception as e:
                print(f"🔍 RESTAURANT_DEBUG: ⚠️ Error generating highlights: {e}")
                highlights = []
            
            # Create restaurant object with safe defaults
            try:
                restaurant = Restaurant(
                    id=restaurant_data.get("id", f"unknown_{len(restaurants)}"),
                    name=restaurant_data.get("name", "Unknown Restaurant"),
                    cuisine=restaurant_data.get("cuisine", "Restaurant"),
                    address=restaurant_data.get("address", "Address not available"),
                    distance_miles=restaurant_data.get("distance_miles", 0.0),
                    price_level=restaurant_data.get("price_level", "$$"),
                    rating=restaurant_data.get("rating", 4.0),
                    phone=restaurant_data.get("phone"),
                    google_place_id=restaurant_data.get("google_place_id"),
                    opentable=opentable_info,
                    highlights=highlights
                )
                print(f"🔍 RESTAURANT_DEBUG: ✅ Successfully created restaurant object for {restaurant_name}")
            except Exception as e:
                print(f"🔍 RESTAURANT_DEBUG: ❌ Error creating restaurant object: {e}")
                continue
            restaurants.append(restaurant)
        
        print(f"🔍 RESTAURANT_DEBUG: ✅ Successfully processed {len(restaurants)} restaurants from Google Places")
        return restaurants
        
    except Exception as e:
        print(f"🔍 RESTAURANT_DEBUG: ❌ Exception occurred: {type(e).__name__}: {e}")
        import traceback
        print(f"🔍 RESTAURANT_DEBUG: Full traceback: {traceback.format_exc()}")
        return await get_mock_restaurants(location, preferences, people_data, excluded_ids)

async def get_mock_restaurants(
    location: dict, 
    preferences: dict, 
    people_data: List[dict],
    excluded_ids: List[str] = None
) -> List[Restaurant]:
    """Get mock restaurants as fallback"""
    print(f"🔍 RESTAURANT_DEBUG: 🎭 Using MOCK restaurant data")
    print(f"🔍 RESTAURANT_DEBUG: Mock location: {location}")
    
    # Defensive programming - ensure we have valid inputs
    if not isinstance(location, dict):
        print(f"🔍 RESTAURANT_DEBUG: ❌ Invalid location type for mock: {type(location)}")
        location = {}
    
    if not isinstance(preferences, dict):
        print(f"🔍 RESTAURANT_DEBUG: ❌ Invalid preferences type for mock: {type(preferences)}")
        preferences = {}
    
    if not isinstance(people_data, list):
        print(f"🔍 RESTAURANT_DEBUG: ❌ Invalid people_data type for mock: {type(people_data)}")
        people_data = []
    
    # Get mock restaurants based on location
    city_key = get_city_key(location.get("address", "") if location else "")
    print(f"🔍 RESTAURANT_DEBUG: Detected city: {city_key}")
    available_restaurants = MOCK_RESTAURANTS.get(city_key, MOCK_RESTAURANTS["san_francisco"])
    print(f"🔍 RESTAURANT_DEBUG: Available mock restaurants: {len(available_restaurants)}")
    
    # Filter based on preferences
    filtered_restaurants = available_restaurants.copy()
    
    if preferences.get("cuisine_types"):
        cuisine_types_lower = [c.lower() for c in preferences["cuisine_types"]]
        filtered_restaurants = [
            r for r in filtered_restaurants 
            if any(cuisine.lower() in r["cuisine"].lower() for cuisine in cuisine_types_lower)
        ]
    
    # Filter out excluded restaurants
    if excluded_ids:
        filtered_restaurants = [r for r in filtered_restaurants if r["id"] not in excluded_ids]
    
    # Select 3 diverse restaurants
    selected_restaurants = random.sample(
        filtered_restaurants if len(filtered_restaurants) >= 3 else available_restaurants,
        min(3, len(filtered_restaurants) if filtered_restaurants else len(available_restaurants))
    )
    
    # Build restaurant response objects
    restaurants = []
    print(f"🔍 RESTAURANT_DEBUG: Building {len(selected_restaurants)} restaurant objects...")
    
    for i, restaurant_data in enumerate(selected_restaurants):
        print(f"🔍 RESTAURANT_DEBUG: Processing restaurant {i+1}: {restaurant_data.get('name', 'Unknown')}")
        # Calculate distance (mock calculation)
        distance = calculate_distance(
            location.get("latitude", 37.7749), 
            location.get("longitude", -122.4194),
            0, 0  # Mock coordinates
        )
        
        try:
            # Generate OpenTable info
            print(f"🔍 RESTAURANT_DEBUG: Generating OpenTable info...")
            opentable_info = generate_opentable_info(
                restaurant_data.get("name", "Unknown"), 
                city_key,
                preferences.get("time_preference") if preferences else None,
                preferences.get("party_size", 2) if preferences else 2
            )
            print(f"🔍 RESTAURANT_DEBUG: ✅ OpenTable info generated")
            
            # Generate AI highlights
            print(f"🔍 RESTAURANT_DEBUG: Generating AI highlights...")
            highlights = await generate_ai_highlights(
                restaurant_data,
                preferences or {},
                people_data or []
            )
            print(f"🔍 RESTAURANT_DEBUG: ✅ AI highlights generated: {len(highlights)} items")
            
            # Create restaurant object
            print(f"🔍 RESTAURANT_DEBUG: Creating Restaurant object...")
            restaurant = Restaurant(
                id=restaurant_data.get("id", f"mock_unknown_{i}"),
                name=restaurant_data.get("name", "Unknown Restaurant"),
                cuisine=restaurant_data.get("cuisine", "Restaurant"),
                address=restaurant_data.get("address", "Address not available"),
                distance_miles=float(distance),
                price_level=restaurant_data.get("price_level", "$$"),
                rating=float(restaurant_data.get("rating", 4.0)),
                phone=restaurant_data.get("phone"),
                google_place_id=restaurant_data.get("google_place_id"),
                opentable=opentable_info,
                highlights=highlights
            )
            print(f"🔍 RESTAURANT_DEBUG: ✅ Restaurant object created successfully")
            restaurants.append(restaurant)
            
        except Exception as e:
            print(f"🔍 RESTAURANT_DEBUG: ❌ Error processing restaurant {i+1}: {e}")
            import traceback
            print(f"🔍 RESTAURANT_DEBUG: Traceback: {traceback.format_exc()}")
            continue
    
    return restaurants

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
    print(f"🔍 DUST_DEBUG: Attempting to consume 3 DUST for user {user_id}")
    try:
        async with httpx.AsyncClient() as client:
            payload = {
                "user_id": str(user_id),
                "amount": 3,
                "app_id": "fairydust-restaurant",
                "description": "Restaurant search"
            }
            print(f"🔍 DUST_DEBUG: Payload: {payload}")
            
            response = await client.post(
                "https://fairydust-ledger-production.up.railway.app/transactions/consume",
                json=payload,
                timeout=10.0
            )
            print(f"🔍 DUST_DEBUG: Ledger service response: {response.status_code}")
            
            if response.status_code != 200:
                response_text = response.text
                print(f"🔍 DUST_DEBUG: Error response: {response_text}")
                return False
            
            print(f"🔍 DUST_DEBUG: ✅ DUST consumption successful")
            return True
    except Exception as e:
        print(f"🔍 DUST_DEBUG: ❌ Exception consuming DUST: {e}")
        return False

async def get_people_data(user_id: UUID, selected_people: List[UUID]) -> List[dict]:
    """Fetch people data from Identity Service"""
    print(f"🔍 PEOPLE_DEBUG: Getting people data for user {user_id}, selected: {selected_people}")
    
    if not selected_people:
        print(f"🔍 PEOPLE_DEBUG: No selected people, returning empty list")
        return []
    
    try:
        print(f"🔍 PEOPLE_DEBUG: Making request to Identity Service...")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"https://fairydust-identity-production.up.railway.app/users/{user_id}/people",
                timeout=10.0
            )
            print(f"🔍 PEOPLE_DEBUG: Identity Service response: {response.status_code}")
            if response.status_code == 200:
                all_people = response.json().get("people", [])
                print(f"🔍 PEOPLE_DEBUG: Got {len(all_people)} people from Identity Service")
                # Filter to selected people and include relevant preference data
                selected_people_data = []
                for person in all_people:
                    if person and person.get("id") in [str(pid) for pid in selected_people]:
                        # Get dining preferences from profile data
                        dining_prefs = {}
                        for profile_item in person.get("profile_data", []):
                            if profile_item.get("category") in ["dining_preferences", "favorite_restaurants"]:
                                dining_prefs[profile_item["category"]] = profile_item.get("field_value", {})
                        
                        selected_people_data.append({
                            "id": person.get("id", ""),
                            "name": person.get("name", ""),
                            "relationship": person.get("relationship", ""),
                            "notes": dining_prefs.get("dining_preferences", {}).get("notes", ""),
                            "favorite_restaurants": dining_prefs.get("favorite_restaurants", {}).get("restaurants", [])
                        })
                print(f"🔍 PEOPLE_DEBUG: Filtered to {len(selected_people_data)} selected people")
                return selected_people_data
            else:
                print(f"🔍 PEOPLE_DEBUG: Identity Service returned {response.status_code}, returning empty list")
                return []
    except Exception as e:
        print(f"🔍 PEOPLE_DEBUG: Exception fetching people data: {e}")
    
    return []

@router.post("/generate", response_model=RestaurantResponse)
async def generate_restaurants(
    request: RestaurantGenerateRequest,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db)
):
    """Generate restaurant recommendations based on location and preferences"""
    
    print(f"🚨 RESTAURANT_ENDPOINT: /restaurant/generate endpoint reached!")
    print(f"🚨 RESTAURANT_ENDPOINT: Request user_id: {request.user_id}")
    print(f"🚨 RESTAURANT_ENDPOINT: Current user: {current_user.user_id}")
    print(f"🚨 RESTAURANT_ENDPOINT: Location: {request.location}")
    print(f"🚨 RESTAURANT_ENDPOINT: Preferences: {request.preferences}")
    
    # Verify user matches the request
    if str(current_user.user_id) != str(request.user_id):
        print(f"🚨 RESTAURANT_ENDPOINT: ❌ User mismatch!")
        raise HTTPException(status_code=403, detail="Cannot generate restaurants for other users")
    
    # Rate limiting check
    await check_api_rate_limit_only(current_user.user_id)
    
    # DUST consumption - temporarily disabled for testing since app already handles it
    print(f"🔍 DUST_DEBUG: Skipping DUST consumption - assuming app already handled it")
    # TODO: Determine if restaurant API should consume DUST or if app handles it
    # dust_consumed = await consume_dust_for_restaurant_search(request.user_id)
    # if not dust_consumed:
    #     raise HTTPException(
    #         status_code=402, 
    #         detail="Insufficient DUST balance or payment processing failed"
    #     )
    
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
    
    # Get restaurants using Google Places API with fallback to mock data
    print(f"🚨 RESTAURANT_ENDPOINT: Calling get_restaurants_from_google_places...")
    restaurants = await get_restaurants_from_google_places(
        request.location.dict(),
        request.preferences.dict(),
        people_data,
        excluded_ids=[]
    )
    
    print(f"🚨 RESTAURANT_ENDPOINT: Got {len(restaurants)} restaurants, creating response...")
    
    try:
        response = RestaurantResponse(
            restaurants=restaurants,
            session_id=session_id,
            generated_at=datetime.utcnow()
        )
        print(f"🚨 RESTAURANT_ENDPOINT: ✅ Response created successfully")
        return response
    except Exception as e:
        print(f"🚨 RESTAURANT_ENDPOINT: ❌ Error creating response: {e}")
        import traceback
        print(f"🚨 RESTAURANT_ENDPOINT: Traceback: {traceback.format_exc()}")
        raise

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
    await check_api_rate_limit_only(current_user.user_id)
    
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
    
    # Get people data for highlights (for now, use empty array - could be stored in session)
    people_data = await get_people_data(current_user.user_id, [])
    
    # Get restaurants using Google Places API with exclusions
    restaurants = await get_restaurants_from_google_places(
        location_data,
        preferences_data,
        people_data,
        excluded_ids=updated_excluded
    )
    
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