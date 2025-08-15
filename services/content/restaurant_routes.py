# services/content/restaurant_routes.py
# Service URL configuration based on environment
import os
import random
from datetime import datetime, timedelta
from uuid import UUID
from shared.uuid_utils import generate_uuid7

import httpx

environment = os.getenv("ENVIRONMENT", "staging")
base_url_suffix = "production" if environment == "production" else "staging"
ledger_url = f"https://fairydust-ledger-{base_url_suffix}.up.railway.app"
identity_url = f"https://fairydust-identity-{base_url_suffix}.up.railway.app"
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPBearer
from google_places_http import get_google_places_http_service
from google_places_new_api import get_google_places_new_api_service

# from google_places_service import get_google_places_service  # Removed - using HTTP implementation only
from models import (
    EnhancedRestaurant,
    OpenTableInfo,
    PersonRestaurantPreferences,
    Restaurant,
    RestaurantGenerateRequest,
    RestaurantRegenerateRequest,
    RestaurantResponse,
    RestaurantTextSearchRequest,
    RestaurantTextSearchResponse,
    UserRestaurantPreferences,
    UserRestaurantPreferencesUpdate,
)
from rate_limiting import check_api_rate_limit_only

from shared.auth_middleware import TokenData, get_current_user
from shared.database import Database, get_db
from shared.json_utils import safe_json_dumps

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
        },
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
        },
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
        },
    ],
}

# Add more cities with similar mock data structure
MOCK_RESTAURANTS.update(
    {
        "chicago": [
            {
                "id": "mock_chi_001",
                "name": "Deep Dish Palace",
                "cuisine": "Pizza",
                "address": "123 Michigan Ave, Chicago, IL 60601",
                "rating": 4.5,
                "price_level": "$$",
                "phone": "(312) 555-0123",
                "google_place_id": "mock_place_id_010",
            },
            {
                "id": "mock_chi_002",
                "name": "Windy City Grill",
                "cuisine": "American",
                "address": "456 State St, Chicago, IL 60654",
                "rating": 4.2,
                "price_level": "$",
                "phone": "(312) 555-0234",
                "google_place_id": "mock_place_id_011",
            },
            {
                "id": "mock_chi_003",
                "name": "Lakefront Seafood",
                "cuisine": "Seafood",
                "address": "789 Lake Shore Dr, Chicago, IL 60611",
                "rating": 4.7,
                "price_level": "$$$",
                "phone": "(312) 555-0345",
                "google_place_id": "mock_place_id_012",
            },
        ],
        "miami": [
            {
                "id": "mock_mia_001",
                "name": "South Beach Bistro",
                "cuisine": "Cuban",
                "address": "123 Ocean Dr, Miami Beach, FL 33139",
                "rating": 4.3,
                "price_level": "$$",
                "phone": "(305) 555-0123",
                "google_place_id": "mock_place_id_013",
            },
            {
                "id": "mock_mia_002",
                "name": "Little Havana",
                "cuisine": "Cuban",
                "address": "456 Calle Ocho, Miami, FL 33135",
                "rating": 4.6,
                "price_level": "$",
                "phone": "(305) 555-0234",
                "google_place_id": "mock_place_id_014",
            },
            {
                "id": "mock_mia_003",
                "name": "Biscayne Steakhouse",
                "cuisine": "Steakhouse",
                "address": "789 Biscayne Blvd, Miami, FL 33132",
                "rating": 4.8,
                "price_level": "$$$",
                "phone": "(305) 555-0345",
                "google_place_id": "mock_place_id_015",
            },
        ],
    }
)


def get_city_key(address: str) -> str:
    """Extract city key from address for mock data lookup"""
    address_lower = address.lower()
    if "san francisco" in address_lower or "sf" in address_lower:
        return "san_francisco"
    elif "new york" in address_lower or "brooklyn" in address_lower or "manhattan" in address_lower:
        return "new_york"
    elif (
        "los angeles" in address_lower
        or "la" in address_lower
        or "beverly hills" in address_lower
        or "venice" in address_lower
    ):
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


def generate_opentable_info(
    restaurant_name: str, city: str, time_preference: str = None, party_size: int = 2
) -> OpenTableInfo:
    """Generate OpenTable information for a restaurant"""
    # Most upscale restaurants accept reservations, fast food typically doesn't
    restaurant_name_lower = restaurant_name.lower()

    # Determine if restaurant likely takes reservations based on name/type
    fast_food_indicators = [
        "mcdonald",
        "burger king",
        "taco bell",
        "subway",
        "kfc",
        "pizza hut",
        "domino",
    ]
    casual_indicators = ["cafe", "diner", "counter", "bar", "pub"]

    if any(indicator in restaurant_name_lower for indicator in fast_food_indicators):
        has_reservations = False
    elif any(indicator in restaurant_name_lower for indicator in casual_indicators):
        has_reservations = random.choice([True, False])  # 50% chance
    else:
        has_reservations = random.choice(
            [True, True, True, False]
        )  # 75% chance for sit-down restaurants

    available_times = []
    if has_reservations and time_preference != "now":
        # Generate realistic available times based on time preference
        if time_preference == "tonight":
            times = ["6:00 PM", "6:30 PM", "7:30 PM", "8:00 PM", "8:30 PM"]
        elif time_preference == "weekend":
            times = [
                "11:30 AM",
                "12:00 PM",
                "12:30 PM",
                "5:30 PM",
                "6:00 PM",
                "6:30 PM",
                "7:00 PM",
                "7:30 PM",
                "8:00 PM",
            ]
        else:
            times = [
                "5:30 PM",
                "6:00 PM",
                "6:30 PM",
                "7:00 PM",
                "7:30 PM",
                "8:00 PM",
                "8:30 PM",
                "9:00 PM",
            ]
        available_times = random.sample(times, random.randint(2, 4))

    # Generate enhanced OpenTable deep links
    city_clean = city.replace("_", " ").title()
    restaurant_query = restaurant_name.replace(" ", "%20").replace("&", "%26")
    location_query = city_clean.replace(" ", "%20")

    # Multiple booking URL formats for better compatibility
    booking_url = f"https://www.opentable.com/s?query={restaurant_query}&location={location_query}&covers={party_size}"

    return OpenTableInfo(
        has_reservations=has_reservations, available_times=available_times, booking_url=booking_url
    )


async def get_restaurants_from_google_places(
    location: dict, preferences: dict, people_data: list[dict], excluded_ids: list[str] = None
) -> list[Restaurant]:
    """Get restaurants from Google Places API with fallback to mock data"""
    print("🔍 RESTAURANT_DEBUG: Starting Google Places search")
    print(f"🔍 RESTAURANT_DEBUG: Location data: {location}")
    print(f"🔍 RESTAURANT_DEBUG: Preferences: {preferences}")
    print(f"🔍 RESTAURANT_DEBUG: Excluded IDs: {excluded_ids}")

    # Defensive programming - ensure we have valid dictionaries
    if not isinstance(location, dict):
        print(
            f"🔍 RESTAURANT_DEBUG: ❌ Invalid location type: {type(location)}, falling back to mock data"
        )
        location = {}

    if not isinstance(preferences, dict):
        print(
            f"🔍 RESTAURANT_DEBUG: ❌ Invalid preferences type: {type(preferences)}, using defaults"
        )
        preferences = {}

    if not isinstance(people_data, list):
        print(
            f"🔍 RESTAURANT_DEBUG: ❌ Invalid people_data type: {type(people_data)}, using empty list"
        )
        people_data = []

    try:
        print("🔍 RESTAURANT_DEBUG: Initializing Google Places HTTP service...")

        # Use HTTP implementation directly (no googlemaps package dependency)
        places_service = get_google_places_http_service()
        print("🔍 RESTAURANT_DEBUG: ✅ Google Places HTTP service initialized successfully")
        use_http_service = True

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
            print(
                f"🔍 RESTAURANT_DEBUG: Location address field: {location.get('address', 'NO ADDRESS PROVIDED')}"
            )
            return await get_mock_restaurants(location, preferences, people_data, excluded_ids)

        # Enhance search with pet-friendly terms if pets are present
        special_occasion = preferences.get("special_occasion", "")
        pets_present = [p for p in people_data if p.get("entry_type") == "pet"]
        if pets_present:
            pet_terms = []
            for pet in pets_present:
                species = pet.get("species", "").lower()
                if "dog" in species:
                    pet_terms.append("dog-friendly")
                else:
                    pet_terms.append("pet-friendly")

            # Add unique pet terms to special occasion
            unique_pet_terms = list(set(pet_terms))
            if unique_pet_terms:
                enhanced_occasion = f"{special_occasion} {' '.join(unique_pet_terms)}".strip()
                print(
                    f"🐾 RESTAURANT_DEBUG: Enhanced search for {len(pets_present)} pets: '{enhanced_occasion}'"
                )
            else:
                enhanced_occasion = special_occasion
        else:
            enhanced_occasion = special_occasion

        # Get restaurants from Google Places
        print("🔍 RESTAURANT_DEBUG: Calling Google Places API...")
        print(
            f"🔍 RESTAURANT_DEBUG: API Parameters - cuisine_types: {preferences.get('cuisine_types', [])}, open_now: {preferences.get('time_preference') == 'now'}, special_occasion: '{enhanced_occasion}'"
        )

        if use_http_service:
            google_restaurants = await places_service.search_restaurants(
                latitude=latitude,
                longitude=longitude,
                radius_miles=radius_miles,
                cuisine_types=preferences.get("cuisine_types", []),
                open_now=preferences.get("time_preference") == "now",
                min_rating=3.5,
                max_results=20,
                special_occasion=enhanced_occasion,
            )
        else:
            google_restaurants = places_service.search_restaurants(
                latitude=latitude,
                longitude=longitude,
                radius_miles=radius_miles,
                cuisine_types=preferences.get("cuisine_types", []),
                open_now=preferences.get("time_preference") == "now",
                min_rating=3.5,
                max_results=20,
                special_occasion=enhanced_occasion,
            )

        print(
            f"🔍 RESTAURANT_DEBUG: Google Places returned {len(google_restaurants) if google_restaurants else 0} restaurants"
        )

        if not google_restaurants:
            print(
                "🔍 RESTAURANT_DEBUG: ❌ No restaurants found via Google Places, falling back to mock data"
            )
            return await get_mock_restaurants(location, preferences, people_data, excluded_ids)

        print(
            f"🔍 RESTAURANT_DEBUG: ✅ Using Google Places data for {len(google_restaurants)} restaurants"
        )

        # Filter out excluded restaurants
        if excluded_ids and google_restaurants:
            print(f"🔍 RESTAURANT_DEBUG: Filtering out {len(excluded_ids)} excluded restaurants")
            google_restaurants = [
                r for r in google_restaurants if r and r.get("id") not in excluded_ids
            ]

        # Convert to Restaurant objects with highlights
        restaurants = []
        max_restaurants_to_return = preferences.get("max_results", 10)
        print(f"🔍 RESTAURANT_DEBUG: Client requested max_results={max_restaurants_to_return}")
        for restaurant_data in google_restaurants[:max_restaurants_to_return]:
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
                restaurant_name, get_city_key(city_address), time_pref, party_size
            )

            # Generate AI highlights
            try:
                highlights = await generate_ai_highlights(
                    restaurant_data, preferences or {}, people_data or []
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
                    highlights=highlights,
                )
                print(
                    f"🔍 RESTAURANT_DEBUG: ✅ Successfully created restaurant object for {restaurant_name}"
                )
            except Exception as e:
                print(f"🔍 RESTAURANT_DEBUG: ❌ Error creating restaurant object: {e}")
                continue
            restaurants.append(restaurant)

        # Apply opentable_only filter if requested
        if preferences.get("opentable_only", False):
            print("🔍 RESTAURANT_DEBUG: Applying opentable_only filter")
            opentable_restaurants = []
            for restaurant in restaurants:
                if restaurant.opentable and restaurant.opentable.has_reservations:
                    opentable_restaurants.append(restaurant)
                else:
                    print(
                        f"🔍 RESTAURANT_DEBUG: Filtering out {restaurant.name} - no OpenTable reservations"
                    )
            restaurants = opentable_restaurants
            print(
                f"🔍 RESTAURANT_DEBUG: After opentable_only filter: {len(restaurants)} restaurants remain"
            )

        print(
            f"🔍 RESTAURANT_DEBUG: ✅ Successfully processed {len(restaurants)} restaurants from Google Places"
        )
        return restaurants

    except Exception as e:
        print(f"🔍 RESTAURANT_DEBUG: ❌ Exception occurred: {type(e).__name__}: {e}")
        import traceback

        print(f"🔍 RESTAURANT_DEBUG: Full traceback: {traceback.format_exc()}")
        return await get_mock_restaurants(location, preferences, people_data, excluded_ids)


async def get_mock_restaurants(
    location: dict, preferences: dict, people_data: list[dict], excluded_ids: list[str] = None
) -> list[Restaurant]:
    """Get mock restaurants as fallback"""
    print("🔍 RESTAURANT_DEBUG: 🎭 Using MOCK restaurant data")
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
            r
            for r in filtered_restaurants
            if any(cuisine.lower() in r["cuisine"].lower() for cuisine in cuisine_types_lower)
        ]

    # Filter out excluded restaurants
    if excluded_ids:
        filtered_restaurants = [r for r in filtered_restaurants if r["id"] not in excluded_ids]

    # Select diverse restaurants based on client preference
    max_mock_restaurants = preferences.get("max_results", 10)
    print(
        f"🔍 RESTAURANT_DEBUG: Mock restaurants - client requested max_results={max_mock_restaurants}"
    )
    selected_restaurants = random.sample(
        filtered_restaurants
        if len(filtered_restaurants) >= max_mock_restaurants
        else available_restaurants,
        min(
            max_mock_restaurants,
            len(filtered_restaurants) if filtered_restaurants else len(available_restaurants),
        ),
    )

    # Build restaurant response objects
    restaurants = []
    print(f"🔍 RESTAURANT_DEBUG: Building {len(selected_restaurants)} restaurant objects...")

    for i, restaurant_data in enumerate(selected_restaurants):
        print(
            f"🔍 RESTAURANT_DEBUG: Processing restaurant {i+1}: {restaurant_data.get('name', 'Unknown')}"
        )
        # Calculate distance (mock calculation)
        distance = calculate_distance(
            location.get("latitude", 37.7749),
            location.get("longitude", -122.4194),
            0,
            0,  # Mock coordinates
        )

        try:
            # Generate OpenTable info
            print("🔍 RESTAURANT_DEBUG: Generating OpenTable info...")
            opentable_info = generate_opentable_info(
                restaurant_data.get("name", "Unknown"),
                city_key,
                preferences.get("time_preference") if preferences else None,
                preferences.get("party_size", 2) if preferences else 2,
            )
            print("🔍 RESTAURANT_DEBUG: ✅ OpenTable info generated")

            # Generate AI highlights
            print("🔍 RESTAURANT_DEBUG: Generating AI highlights...")
            highlights = await generate_ai_highlights(
                restaurant_data, preferences or {}, people_data or []
            )
            print(f"🔍 RESTAURANT_DEBUG: ✅ AI highlights generated: {len(highlights)} items")

            # Create restaurant object
            print("🔍 RESTAURANT_DEBUG: Creating Restaurant object...")
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
                highlights=highlights,
            )
            print("🔍 RESTAURANT_DEBUG: ✅ Restaurant object created successfully")
            restaurants.append(restaurant)

        except Exception as e:
            print(f"🔍 RESTAURANT_DEBUG: ❌ Error processing restaurant {i+1}: {e}")
            import traceback

            print(f"🔍 RESTAURANT_DEBUG: Traceback: {traceback.format_exc()}")
            continue

    # Apply opentable_only filter if requested
    if preferences.get("opentable_only", False):
        print("🔍 RESTAURANT_DEBUG: Applying opentable_only filter to mock restaurants")
        opentable_restaurants = []
        for restaurant in restaurants:
            if restaurant.opentable and restaurant.opentable.has_reservations:
                opentable_restaurants.append(restaurant)
            else:
                print(
                    f"🔍 RESTAURANT_DEBUG: Filtering out {restaurant.name} - no OpenTable reservations"
                )
        restaurants = opentable_restaurants
        print(
            f"🔍 RESTAURANT_DEBUG: After opentable_only filter: {len(restaurants)} mock restaurants remain"
        )

    return restaurants


async def generate_ai_highlights(
    restaurant: dict, preferences: dict, people_data: list[dict]
) -> list[str]:
    """Generate AI-powered restaurant highlights based on preferences and people data"""
    highlights = []

    # Defensive programming for None values
    if not isinstance(restaurant, dict):
        return highlights
    if not isinstance(preferences, dict):
        preferences = {}
    if not isinstance(people_data, list):
        people_data = []

    # Basic highlights based on restaurant type
    cuisine_raw = restaurant.get("cuisine") or "Restaurant"
    cuisine = cuisine_raw.lower() if cuisine_raw else "restaurant"
    price_level = restaurant.get("price_level") or "$$"
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
    special_occasion_raw = preferences.get("special_occasion")
    special_occasion = special_occasion_raw.lower() if special_occasion_raw else ""
    if "birthday" in special_occasion:
        highlights.append("Birthday-friendly atmosphere")
    elif "anniversary" in special_occasion:
        highlights.append("Romantic setting")
    elif "date" in special_occasion:
        highlights.append("Perfect for dates")

    # People and pets preferences
    has_pets = False
    for person in people_data:
        if isinstance(person, dict):
            # Check if this is a pet
            if person.get("entry_type") == "pet":
                has_pets = True
                species = person.get("species", "").lower()
                if "dog" in species:
                    highlights.append("Dog-friendly patio")
                elif "cat" in species:
                    highlights.append("Pet-friendly seating")
                else:
                    highlights.append("Pet-friendly venue")

            # Check dining preferences notes
            notes_raw = person.get("notes")
            notes = notes_raw.lower() if notes_raw else ""
            if "high chair" in notes or "kids" in notes:
                highlights.append("Family-friendly")
            if "vegetarian" in notes or "vegan" in notes:
                highlights.append("Vegetarian options")
            if "gluten" in notes:
                highlights.append("Gluten-free options")

    # General pet-friendly highlight if pets are present but no specific species highlights added
    if has_pets and not any("pet" in h.lower() or "dog" in h.lower() for h in highlights):
        highlights.append("Pet-friendly venue")

    return highlights[:3]  # Limit to 3 highlights


# DUST consumption removed - handled by app client, not content service


async def get_people_data(user_id: UUID, selected_people: list[UUID]) -> list[dict]:
    """Fetch people data from Identity Service"""
    print(f"🔍 PEOPLE_DEBUG: Getting people data for user {user_id}, selected: {selected_people}")

    if not selected_people:
        print("🔍 PEOPLE_DEBUG: No selected people, returning empty list")
        return []

    try:
        print("🔍 PEOPLE_DEBUG: Making request to Identity Service...")
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{identity_url}/users/{user_id}/people",
                timeout=10.0,
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
                            if profile_item.get("category") in [
                                "dining_preferences",
                                "favorite_restaurants",
                            ]:
                                dining_prefs[profile_item["category"]] = profile_item.get(
                                    "field_value", {}
                                )

                        selected_people_data.append(
                            {
                                "id": person.get("id", ""),
                                "name": person.get("name", ""),
                                "relationship": person.get("relationship", ""),
                                "entry_type": person.get(
                                    "entry_type", "person"
                                ),  # Include pet type
                                "species": person.get("species"),  # Pet species info
                                "notes": dining_prefs.get("dining_preferences", {}).get(
                                    "notes", ""
                                ),
                                "favorite_restaurants": dining_prefs.get(
                                    "favorite_restaurants", {}
                                ).get("restaurants", []),
                            }
                        )
                print(f"🔍 PEOPLE_DEBUG: Filtered to {len(selected_people_data)} selected people")
                return selected_people_data
            else:
                print(
                    f"🔍 PEOPLE_DEBUG: Identity Service returned {response.status_code}, returning empty list"
                )
                return []
    except Exception as e:
        print(f"🔍 PEOPLE_DEBUG: Exception fetching people data: {e}")

    return []


@router.post("/generate", response_model=RestaurantResponse)
async def generate_restaurants(
    request: RestaurantGenerateRequest,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Generate restaurant recommendations based on location and preferences"""

    print("🚨 RESTAURANT_ENDPOINT: /restaurant/generate endpoint reached!")
    print(f"🚨 RESTAURANT_ENDPOINT: Request user_id: {request.user_id}")
    print(f"🚨 RESTAURANT_ENDPOINT: Current user: {current_user.user_id}")
    print(f"🚨 RESTAURANT_ENDPOINT: Location: {request.location}")
    print(f"🚨 RESTAURANT_ENDPOINT: Preferences: {request.preferences}", flush=True)
    print("🔍 RESTAURANT_ENDPOINT: Parameter implementation status:", flush=True)
    print("  • cuisine_types: ✅ Google Places keyword + client-side filtering", flush=True)
    print("  • opentable_only: ✅ Post-processing filter by has_reservations", flush=True)
    print("  • time_preference: ✅ Google Places open_now + OpenTable times", flush=True)
    print("  • party_size: ✅ OpenTable booking URL + group size highlights", flush=True)
    print("  • special_occasion: ✅ Google Places keyword search + AI highlights", flush=True)
    print("  • max_results: ✅ Client-configurable result limit (1-20, default: 10)", flush=True)

    # Verify user matches the request
    if str(current_user.user_id) != str(request.user_id):
        print("🚨 RESTAURANT_ENDPOINT: ❌ User mismatch!")
        raise HTTPException(status_code=403, detail="Cannot generate restaurants for other users")

    # Rate limiting check
    await check_api_rate_limit_only(current_user.user_id)

    # DUST consumption - temporarily disabled for testing since app already handles it
    print("🔍 DUST_DEBUG: Skipping DUST consumption - assuming app already handled it")
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
    session_id = request.session_id or generate_uuid7()
    session_expires = datetime.utcnow() + timedelta(hours=24)

    # Store session in database
    await db.execute(
        """
        INSERT INTO restaurant_sessions (id, user_id, session_data, excluded_restaurants, expires_at)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (id) DO UPDATE SET
            session_data = EXCLUDED.session_data,
            expires_at = EXCLUDED.expires_at
    """,
        session_id,
        request.user_id,
        safe_json_dumps(
            {"location": request.location.dict(), "preferences": request.preferences.dict()}
        ),
        [],
        session_expires,
    )

    # Get restaurants using Google Places API with fallback to mock data
    print("🚨 RESTAURANT_ENDPOINT: Calling get_restaurants_from_google_places...")
    restaurants = await get_restaurants_from_google_places(
        request.location.dict(), request.preferences.dict(), people_data, excluded_ids=[]
    )

    print(f"🚨 RESTAURANT_ENDPOINT: Got {len(restaurants)} restaurants, creating response...")

    try:
        response = RestaurantResponse(
            restaurants=restaurants, session_id=session_id, generated_at=datetime.utcnow()
        )
        print("🚨 RESTAURANT_ENDPOINT: ✅ Response created successfully")
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
    db: Database = Depends(get_db),
):
    """Regenerate restaurants within an existing session (free)"""
    print(
        f"🍽️ RESTAURANT_REGENERATE: Starting regeneration for session {request.session_id}, excluding {len(request.exclude_restaurants)} restaurants",
        flush=True,
    )

    # Get existing session
    session = await db.fetch_one(
        """
        SELECT * FROM restaurant_sessions
        WHERE id = $1 AND user_id = $2 AND expires_at > CURRENT_TIMESTAMP
    """,
        request.session_id,
        current_user.user_id,
    )

    if not session:
        print(
            f"🚨 RESTAURANT_REGENERATE: Session {request.session_id} not found or expired for user {current_user.user_id}",
            flush=True,
        )
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

    await db.execute(
        """
        UPDATE restaurant_sessions
        SET excluded_restaurants = $1
        WHERE id = $2
    """,
        updated_excluded,
        request.session_id,
    )

    # Get people data for highlights (for now, use empty array - could be stored in session)
    people_data = await get_people_data(current_user.user_id, [])

    # Get restaurants using Google Places API with exclusions
    print(
        f"🔍 RESTAURANT_REGENERATE: Calling Google Places API with {len(updated_excluded)} exclusions",
        flush=True,
    )
    restaurants = await get_restaurants_from_google_places(
        location_data, preferences_data, people_data, excluded_ids=updated_excluded
    )

    print(
        f"✅ RESTAURANT_REGENERATE: Successfully regenerated {len(restaurants)} restaurants for session {request.session_id}",
        flush=True,
    )
    return RestaurantResponse(
        restaurants=restaurants, session_id=request.session_id, generated_at=datetime.utcnow()
    )


@router.get("/preferences/{user_id}", response_model=UserRestaurantPreferences)
async def get_restaurant_preferences(
    user_id: UUID,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Get user's restaurant preferences"""
    print(f"🍽️ RESTAURANT_PREFS_GET: Getting preferences for user {user_id}", flush=True)

    # Verify user access
    if str(current_user.user_id) != str(user_id):
        print(
            f"🚨 RESTAURANT_PREFS_GET: Access denied for user {current_user.user_id} trying to access {user_id}'s preferences",
            flush=True,
        )
        raise HTTPException(status_code=403, detail="Cannot access other users' preferences")

    # Get people data from Identity Service
    print(
        f"🔍 RESTAURANT_PREFS_GET: Fetching people data from Identity Service for user {user_id}",
        flush=True,
    )
    try:
        async with httpx.AsyncClient() as client:
            response = await client.get(
                f"{identity_url}/users/{user_id}/people",
                timeout=10.0,
            )
            people_data = response.json().get("people", []) if response.status_code == 200 else []
            print(
                f"✅ RESTAURANT_PREFS_GET: Successfully fetched {len(people_data)} people from Identity Service",
                flush=True,
            )
    except Exception as e:
        print(f"🚨 RESTAURANT_PREFS_GET: Failed to fetch people data: {e}", flush=True)
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

        people_preferences.append(
            PersonRestaurantPreferences(
                person_id=UUID(person["id"]), favorite_restaurants=favorite_restaurants, notes=notes
            )
        )

    # Get personal preferences (you could store these in user profile or separate table)
    # For now, return defaults
    personal_preferences = {"default_radius": "10mi", "preferred_cuisines": []}

    print(
        f"✅ RESTAURANT_PREFS_GET: Successfully built preferences for user {user_id}, people_count={len(people_preferences)}",
        flush=True,
    )
    return UserRestaurantPreferences(
        personal_preferences=personal_preferences, people_preferences=people_preferences
    )


@router.put("/preferences/{user_id}", response_model=UserRestaurantPreferences)
async def update_restaurant_preferences(
    user_id: UUID,
    preferences: UserRestaurantPreferencesUpdate,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """Update user's restaurant preferences"""
    print(
        f"🍽️ RESTAURANT_PREFS_UPDATE: Updating preferences for user {user_id}, people_updates={len(preferences.people_preferences) if preferences.people_preferences else 0}",
        flush=True,
    )

    # Verify user access
    if str(current_user.user_id) != str(user_id):
        print(
            f"🚨 RESTAURANT_PREFS_UPDATE: Access denied for user {current_user.user_id} trying to update {user_id}'s preferences",
            flush=True,
        )
        raise HTTPException(status_code=403, detail="Cannot update other users' preferences")

    # Update people preferences via Identity Service
    if preferences.people_preferences:
        print(
            f"🔄 RESTAURANT_PREFS_UPDATE: Updating {len(preferences.people_preferences)} people preferences via Identity Service",
            flush=True,
        )
        for person_pref in preferences.people_preferences:
            try:
                async with httpx.AsyncClient() as client:
                    # Update favorite restaurants
                    if person_pref.favorite_restaurants:
                        await client.put(
                            f"{identity_url}/users/{user_id}/people/{person_pref.person_id}/profile",
                            json={
                                "category": "favorite_restaurants",
                                "field_name": "restaurants",
                                "field_value": {"restaurants": person_pref.favorite_restaurants},
                            },
                            timeout=10.0,
                        )

                    # Update dining notes
                    if person_pref.notes:
                        await client.put(
                            f"{identity_url}/users/{user_id}/people/{person_pref.person_id}/profile",
                            json={
                                "category": "dining_preferences",
                                "field_name": "notes",
                                "field_value": {"notes": person_pref.notes},
                            },
                            timeout=10.0,
                        )
            except Exception as e:
                print(
                    f"🚨 RESTAURANT_PREFS_UPDATE: Failed to update people preferences for person {person_pref.person_id}: {e}",
                    flush=True,
                )

    # Return updated preferences
    print(
        f"✅ RESTAURANT_PREFS_UPDATE: Successfully updated preferences for user {user_id}",
        flush=True,
    )
    return await get_restaurant_preferences(user_id, current_user, db)


# ============================================================================
# NEW PLACES API TEXT SEARCH ENDPOINT
# ============================================================================


@router.post("/search-text", response_model=RestaurantTextSearchResponse)
async def search_restaurants_with_text(
    request: RestaurantTextSearchRequest,
    current_user: TokenData = Depends(get_current_user),
    db: Database = Depends(get_db),
):
    """
    Search restaurants using natural language queries with the new Google Places API

    Examples:
    - "kid-friendly italian restaurants with outdoor seating"
    - "romantic dinner spots for anniversary"
    - "casual brunch places with vegetarian options"
    - "budget-friendly tacos near me"
    """
    print("🚨 RESTAURANT_TEXT_SEARCH: /restaurant/search-text endpoint reached!")
    print(f"🚨 RESTAURANT_TEXT_SEARCH: User: {request.user_id}")
    print(f"🚨 RESTAURANT_TEXT_SEARCH: Query: '{request.text_query}'")
    print(f"🚨 RESTAURANT_TEXT_SEARCH: Location: {request.location}")
    print(f"🚨 RESTAURANT_TEXT_SEARCH: Max results: {request.max_results}")

    # Verify user matches the request
    if str(current_user.user_id) != str(request.user_id):
        print("🚨 RESTAURANT_TEXT_SEARCH: ❌ User mismatch!")
        raise HTTPException(status_code=403, detail="Cannot search restaurants for other users")

    # Rate limiting check
    await check_api_rate_limit_only(current_user.user_id)

    try:
        # Get people data for personalization
        people_data = await get_people_data(request.user_id, request.selected_people)
        print(f"🔍 RESTAURANT_TEXT_SEARCH: Got {len(people_data)} people for personalization")

        # Create or get session
        session_id = request.session_id or generate_uuid7()
        session_expires = datetime.utcnow() + timedelta(hours=24)

        # Store session in database
        await db.execute(
            """
            INSERT INTO restaurant_sessions (id, user_id, session_data, excluded_restaurants, expires_at)
            VALUES ($1, $2, $3, $4, $5)
            ON CONFLICT (id) DO UPDATE SET
                session_data = EXCLUDED.session_data,
                expires_at = EXCLUDED.expires_at
        """,
            session_id,
            request.user_id,
            safe_json_dumps(
                {
                    "location": request.location.dict(),
                    "text_query": request.text_query,
                    "search_params": {
                        "max_results": request.max_results,
                        "min_rating": request.min_rating,
                        "price_levels": request.price_levels,
                        "open_now": request.open_now,
                    },
                }
            ),
            [],
            session_expires,
        )

        # Enhance query with pet-friendly terms if pets are present
        enhanced_query = request.text_query
        pets_present = [p for p in people_data if p.get("entry_type") == "pet"]
        if pets_present:
            pet_terms = []
            for pet in pets_present:
                species = pet.get("species", "").lower()
                if "dog" in species:
                    pet_terms.append("dog-friendly")
                else:
                    pet_terms.append("pet-friendly")

            # Add unique pet terms to the query
            unique_pet_terms = list(set(pet_terms))
            if unique_pet_terms:
                enhanced_query = f"{request.text_query} {' '.join(unique_pet_terms)}"
                print(
                    f"🐾 RESTAURANT_TEXT_SEARCH: Enhanced query for {len(pets_present)} pets: '{enhanced_query}'"
                )

        # Use new Places API for text search
        places_service = get_google_places_new_api_service()
        print("🔍 RESTAURANT_TEXT_SEARCH: Using Google Places API (New) for text search")

        restaurants_data = await places_service.search_restaurants_text(
            text_query=enhanced_query,
            latitude=request.location.latitude,
            longitude=request.location.longitude,
            radius_miles=5,  # Default 5 mile radius
            max_results=request.max_results,
            min_rating=request.min_rating,
            price_levels=request.price_levels,
            open_now=request.open_now,
        )

        print(
            f"🔍 RESTAURANT_TEXT_SEARCH: Got {len(restaurants_data)} restaurants from New Places API"
        )
        if not restaurants_data:
            print(
                "🔍 RESTAURANT_TEXT_SEARCH: ⚠️ No restaurants returned from New Places API - this could be:"
            )
            print("  1. New Places API not enabled in Google Console")
            print("  2. Invalid query or location")
            print("  3. API quota/billing issues")
            print("  4. Too restrictive filters")

        # Convert to enhanced restaurant objects
        restaurants = []
        for restaurant_data in restaurants_data:
            # Generate OpenTable info
            restaurant_name = restaurant_data.get("name", "Unknown Restaurant")
            city_address = request.location.address
            party_size = 2  # Default since not specified in text search

            opentable_info = generate_opentable_info(
                restaurant_name, get_city_key(city_address), None, party_size
            )

            # Generate AI highlights using existing function
            try:
                highlights = await generate_ai_highlights(
                    restaurant_data, {"party_size": party_size}, people_data
                )
            except Exception as e:
                print(f"🔍 RESTAURANT_TEXT_SEARCH: ⚠️ Error generating highlights: {e}")
                highlights = []

            # Create enhanced restaurant object
            try:
                restaurant = EnhancedRestaurant(
                    id=restaurant_data.get("id", f"unknown_{len(restaurants)}"),
                    name=restaurant_data.get("name", "Unknown Restaurant"),
                    cuisine=restaurant_data.get("cuisine", "Restaurant"),
                    address=restaurant_data.get("address", "Address not available"),
                    distance_miles=restaurant_data.get("distance_miles", 0.0),
                    price_level=restaurant_data.get("price_level", "$$"),
                    rating=restaurant_data.get("rating", 0.0),
                    user_rating_count=restaurant_data.get("user_rating_count", 0),
                    phone=restaurant_data.get("phone"),
                    google_place_id=restaurant_data.get("google_place_id"),
                    opentable=opentable_info,
                    highlights=highlights,
                    features=restaurant_data.get("features", []),  # New API features
                )
                restaurants.append(restaurant)
                print(f"🔍 RESTAURANT_TEXT_SEARCH: ✅ Created enhanced restaurant: {restaurant_name}")
            except Exception as e:
                print(f"🔍 RESTAURANT_TEXT_SEARCH: ❌ Error creating restaurant object: {e}")
                continue

        print(f"🚨 RESTAURANT_TEXT_SEARCH: Returning {len(restaurants)} restaurants")

        # Create response
        response = RestaurantTextSearchResponse(
            restaurants=restaurants,
            session_id=session_id,
            generated_at=datetime.utcnow(),
            search_query=request.text_query,
            api_version="new",
        )

        print("🚨 RESTAURANT_TEXT_SEARCH: ✅ Response created successfully")
        return response

    except Exception as e:
        print(f"🚨 RESTAURANT_TEXT_SEARCH: ❌ Error: {e}")
        import traceback

        print(f"🚨 RESTAURANT_TEXT_SEARCH: Traceback: {traceback.format_exc()}")

        # Fallback to legacy endpoint if new API fails
        print("🚨 RESTAURANT_TEXT_SEARCH: Falling back to legacy API with basic query parsing")
        try:
            # Basic parsing of text query to legacy format
            fallback_preferences = _parse_text_query_to_legacy_format(request.text_query)

            # Create legacy request
            legacy_request = RestaurantGenerateRequest(
                user_id=request.user_id,
                location=request.location,
                preferences=fallback_preferences,
                selected_people=request.selected_people,
                session_id=request.session_id,
            )

            # Use legacy endpoint logic
            legacy_response = await generate_restaurants(legacy_request, current_user, db)

            # Convert to new format
            enhanced_restaurants = [
                EnhancedRestaurant(
                    id=r.id,
                    name=r.name,
                    cuisine=r.cuisine,
                    address=r.address,
                    distance_miles=r.distance_miles,
                    price_level=r.price_level,
                    rating=r.rating,
                    user_rating_count=0,  # Legacy doesn't have this
                    phone=r.phone,
                    google_place_id=r.google_place_id,
                    opentable=r.opentable,
                    highlights=r.highlights,
                    features=[],  # Legacy doesn't have features
                )
                for r in legacy_response.restaurants
            ]

            return RestaurantTextSearchResponse(
                restaurants=enhanced_restaurants,
                session_id=legacy_response.session_id,
                generated_at=legacy_response.generated_at,
                search_query=request.text_query,
                api_version="legacy_fallback",
            )

        except Exception as fallback_error:
            print(f"🚨 RESTAURANT_TEXT_SEARCH: ❌ Fallback also failed: {fallback_error}")
            raise HTTPException(
                status_code=500,
                detail="Restaurant search failed. Please try again or use the standard search.",
            )


def _parse_text_query_to_legacy_format(text_query: str) -> "RestaurantPreferences":
    """
    Basic parsing of text query to legacy RestaurantPreferences format
    This is a simple fallback - the new API is much better at understanding queries
    """
    from models import RestaurantPreferences

    query_lower = text_query.lower()

    # Extract cuisine types
    cuisine_types = []
    cuisine_keywords = [
        "italian",
        "chinese",
        "mexican",
        "japanese",
        "indian",
        "thai",
        "french",
        "american",
        "seafood",
    ]
    for cuisine in cuisine_keywords:
        if cuisine in query_lower:
            cuisine_types.append(cuisine)

    # Extract party size indicators
    party_size = 2  # default
    if any(word in query_lower for word in ["family", "group", "large"]):
        party_size = 6
    elif any(word in query_lower for word in ["couple", "date", "romantic"]):
        party_size = 2

    # Extract special occasions
    special_occasion = None
    if any(word in query_lower for word in ["romantic", "date", "anniversary"]):
        special_occasion = "romantic dinner"
    elif any(word in query_lower for word in ["birthday", "celebration"]):
        special_occasion = "birthday"
    elif any(word in query_lower for word in ["family", "kid"]):
        special_occasion = "family"

    # Extract time preferences
    time_preference = None
    if "now" in query_lower or "open" in query_lower:
        time_preference = "now"

    return RestaurantPreferences(
        party_size=party_size,
        cuisine_types=cuisine_types,
        opentable_only=False,
        time_preference=time_preference,
        special_occasion=special_occasion,
        max_results=20,
    )
