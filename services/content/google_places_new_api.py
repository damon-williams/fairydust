# services/content/google_places_new_api.py
"""
Google Places API (New) integration using Text Search
Supports natural language queries like "kid-friendly restaurants with outdoor seating"
"""

import os
from math import atan2, cos, radians, sin, sqrt
from typing import Any, Optional

import httpx


class GooglePlacesNewAPIService:
    """Google Places API (New) service using Text Search endpoint"""

    def __init__(self):
        self.api_key = os.getenv("GOOGLE_PLACES_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_PLACES_API_KEY environment variable is required")

        self.base_url = "https://places.googleapis.com/v1"
        print("🔍 GOOGLE_PLACES_NEW: ✅ GooglePlacesNewAPIService initialized successfully")

    def miles_to_meters(self, miles: float) -> float:
        """Convert miles to meters for Google Places API"""
        return miles * 1609.34

    async def search_restaurants_text(
        self,
        text_query: str,
        latitude: float,
        longitude: float,
        radius_miles: int = 5,
        max_results: int = 20,
        min_rating: Optional[float] = None,
        price_levels: Optional[list[str]] = None,
        open_now: bool = False,
    ) -> list[dict[str, Any]]:
        """
        Search for restaurants using Google Places Text Search API
        
        Args:
            text_query: Natural language query like "kid-friendly italian restaurants with outdoor seating"
            latitude: User's latitude
            longitude: User's longitude  
            radius_miles: Search radius in miles
            max_results: Maximum number of results (1-20)
            min_rating: Minimum rating filter (optional)
            price_levels: Price level filters like ["PRICE_LEVEL_MODERATE"] (optional)
            open_now: Filter for currently open restaurants
        """
        print(f"🔍 GOOGLE_PLACES_NEW: Searching with text query: '{text_query}'")
        print(f"🔍 GOOGLE_PLACES_NEW: Location: {latitude}, {longitude} within {radius_miles} miles")

        # Build request body
        request_body = {
            "textQuery": f"{text_query} restaurants",
            "locationBias": {
                "circle": {
                    "center": {
                        "latitude": latitude,
                        "longitude": longitude
                    },
                    "radius": self.miles_to_meters(radius_miles)
                }
            },
            "includedType": "restaurant",
            "maxResultCount": min(max_results, 20),  # API limit is 20
            "rankPreference": "RELEVANCE",
            "languageCode": "en",
        }

        # Add optional filters
        if open_now:
            request_body["openNow"] = True

        if price_levels:
            request_body["includedPriceLevels"] = price_levels

        if min_rating:
            request_body["minRating"] = min_rating

        # Define fields to return (for efficiency and cost optimization)
        field_mask = [
            "places.id",
            "places.displayName", 
            "places.formattedAddress",
            "places.location",
            "places.rating",
            "places.userRatingCount",
            "places.priceLevel",
            "places.primaryType",
            "places.types",
            "places.nationalPhoneNumber",
            "places.internationalPhoneNumber",
            "places.currentOpeningHours",
            "places.outdoorSeating",
            "places.goodForChildren",
            "places.reservable",
            "places.servesVegetarianFood",
            "places.accessibilityOptions"
        ]

        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": self.api_key,
            "X-Goog-FieldMask": ",".join(field_mask)
        }

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.base_url}/places:searchText",
                    json=request_body,
                    headers=headers,
                    timeout=15.0
                )
                
                print(f"🔍 GOOGLE_PLACES_NEW: API response status: {response.status_code}")

                if response.status_code != 200:
                    print(f"🔍 GOOGLE_PLACES_NEW: API error: {response.text}")
                    return []

                data = response.json()
                places = data.get("places", [])
                print(f"🔍 GOOGLE_PLACES_NEW: Found {len(places)} places from API")

                # Convert to our format
                restaurants = []
                for place in places:
                    restaurant = self._convert_place_to_restaurant(place, latitude, longitude)
                    
                    # Additional filtering if needed
                    if min_rating and restaurant.get("rating", 0) < min_rating:
                        continue
                        
                    restaurants.append(restaurant)

                print(f"🔍 GOOGLE_PLACES_NEW: Returning {len(restaurants)} restaurants")
                return restaurants

        except Exception as e:
            print(f"🔍 GOOGLE_PLACES_NEW: ❌ Error: {e}")
            return []

    def _convert_place_to_restaurant(
        self, place: dict[str, Any], user_lat: float, user_lng: float
    ) -> dict[str, Any]:
        """Convert Google Places API (New) result to our restaurant format"""
        
        # Extract location
        location = place.get("location", {})
        place_lat = location.get("latitude", 0)
        place_lng = location.get("longitude", 0)
        distance_miles = self._calculate_distance(user_lat, user_lng, place_lat, place_lng)

        # Map price level (new API uses enum strings)
        price_level_map = {
            "PRICE_LEVEL_FREE": "$",
            "PRICE_LEVEL_INEXPENSIVE": "$", 
            "PRICE_LEVEL_MODERATE": "$$",
            "PRICE_LEVEL_EXPENSIVE": "$$$",
            "PRICE_LEVEL_VERY_EXPENSIVE": "$$$"
        }
        price_level = price_level_map.get(place.get("priceLevel", "PRICE_LEVEL_MODERATE"), "$$")

        # Extract display name
        display_name = place.get("displayName", {})
        restaurant_name = display_name.get("text", "Unknown Restaurant") if display_name else "Unknown Restaurant"

        # Extract cuisine from primary type and types
        primary_type = place.get("primaryType", "")
        place_types = place.get("types", [])
        cuisine = self._extract_cuisine_from_types(primary_type, place_types, restaurant_name)

        # Get phone numbers
        phone = (
            place.get("nationalPhoneNumber") or 
            place.get("internationalPhoneNumber") or 
            None
        )

        # Extract enhanced features from new API
        features = self._extract_restaurant_features(place)

        return {
            "id": f"gpnew_{place['id']}",
            "name": restaurant_name,
            "cuisine": cuisine,
            "address": place.get("formattedAddress", "Address not available"),
            "distance_miles": round(distance_miles, 1),
            "price_level": price_level,
            "rating": place.get("rating", 0),
            "user_rating_count": place.get("userRatingCount", 0),
            "phone": phone,
            "google_place_id": place["id"],
            "google_place_data": place,
            "features": features  # Enhanced features from new API
        }

    def _extract_cuisine_from_types(self, primary_type: str, place_types: list[str], restaurant_name: str) -> str:
        """Extract cuisine type from new API types and restaurant name"""
        
        # New API type mappings
        cuisine_map = {
            "italian_restaurant": "Italian",
            "chinese_restaurant": "Chinese", 
            "japanese_restaurant": "Japanese",
            "mexican_restaurant": "Mexican",
            "indian_restaurant": "Indian",
            "thai_restaurant": "Thai",
            "french_restaurant": "French",
            "american_restaurant": "American",
            "seafood_restaurant": "Seafood",
            "steak_house": "Steakhouse",
            "pizza_restaurant": "Pizza",
            "sushi_restaurant": "Japanese",
            "mediterranean_restaurant": "Mediterranean",
            "korean_restaurant": "Korean",
            "vietnamese_restaurant": "Vietnamese",
            "greek_restaurant": "Greek",
            "lebanese_restaurant": "Lebanese"
        }

        # Check primary type first
        if primary_type in cuisine_map:
            return cuisine_map[primary_type]

        # Check all types
        for place_type in place_types:
            if place_type in cuisine_map:
                return cuisine_map[place_type]

        # Fallback to name analysis (reuse logic from legacy service)
        return self._extract_cuisine_from_name(restaurant_name)

    def _extract_cuisine_from_name(self, restaurant_name: str) -> str:
        """Extract cuisine from restaurant name using keyword analysis"""
        name_lower = restaurant_name.lower()
        
        # Cuisine keyword mappings
        cuisine_keywords = {
            "Italian": ["pizza", "italiano", "pasta", "luigi", "mario", "tony", "bella", "roma", "milano", "italian", "tuscany", "ristorante", "bistro"],
            "Chinese": ["china", "chinese", "chopstick", "wok", "panda", "dragon", "golden garden", "express", "bao", "szechuan", "hunan"],
            "Mexican": ["taco", "mexican", "burrito", "cantina", "maria", "jose", "salsa", "amigo", "fiesta"],
            "Japanese": ["sushi", "japanese", "ramen", "tokyo", "sakura", "zen", "ninja", "samurai", "bento"],
            "Indian": ["indian", "curry", "tandoor", "maharaja", "taj", "spice", "bombay", "delhi"],
            "Thai": ["thai", "pad", "bangkok", "lemongrass", "basil"],
            "Vietnamese": ["pho", "vietnamese", "viet", "saigon", "banh"],
            "American": ["steak", "grill", "burger", "bbq", "american", "diner"],
            "Seafood": ["seafood", "fish", "crab", "lobster", "oyster", "shrimp"]
        }
        
        for cuisine, keywords in cuisine_keywords.items():
            if any(keyword in name_lower for keyword in keywords):
                return cuisine
                
        return "Restaurant"

    def _extract_restaurant_features(self, place: dict) -> list[str]:
        """Extract special features from new API place data"""
        features = []
        
        # Outdoor seating
        if place.get("outdoorSeating"):
            features.append("outdoor seating")
            
        # Good for children
        if place.get("goodForChildren"):
            features.append("kid-friendly")
            
        # Reservations
        if place.get("reservable"):
            features.append("reservations available")
            
        # Vegetarian options
        if place.get("servesVegetarianFood"):
            features.append("vegetarian options")
            
        # Accessibility 
        accessibility = place.get("accessibilityOptions", {})
        if accessibility.get("wheelchairAccessibleEntrance"):
            features.append("wheelchair accessible")
            
        return features

    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two coordinates in miles using Haversine formula"""
        # Convert to radians
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])

        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat / 2) ** 2 + cos(lat1) * cos(lat2) * sin(dlon / 2) ** 2
        c = 2 * atan2(sqrt(a), sqrt(1 - a))

        # Earth's radius in miles
        earth_radius_miles = 3959
        distance = earth_radius_miles * c

        return distance


# Singleton instance
_places_new_api_service = None


def get_google_places_new_api_service() -> GooglePlacesNewAPIService:
    """Get singleton Google Places New API service instance"""
    global _places_new_api_service
    if _places_new_api_service is None:
        _places_new_api_service = GooglePlacesNewAPIService()
    return _places_new_api_service