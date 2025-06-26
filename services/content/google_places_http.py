# services/content/google_places_http.py
"""
Google Places API integration using direct HTTP calls instead of googlemaps package
This bypasses any package installation issues
"""

import os
from math import atan2, cos, radians, sin, sqrt
from typing import Any

import httpx


class GooglePlacesHTTPService:
    """Google Places API service using direct HTTP calls"""

    def __init__(self):
        self.api_key = os.getenv("GOOGLE_PLACES_API_KEY")
        if not self.api_key:
            raise ValueError("GOOGLE_PLACES_API_KEY environment variable is required")

        self.base_url = "https://maps.googleapis.com/maps/api"
        print("🔍 GOOGLE_PLACES_HTTP: ✅ GooglePlacesHTTPService initialized successfully")

    def miles_to_meters(self, miles: float) -> int:
        """Convert miles to meters for Google Places API"""
        return int(miles * 1609.34)

    async def search_restaurants(
        self,
        latitude: float,
        longitude: float,
        radius_miles: int = 5,
        cuisine_types: list[str] = None,
        open_now: bool = False,
        min_rating: float = 3.5,
        max_results: int = 20,
        special_occasion: str = None,
    ) -> list[dict[str, Any]]:
        """
        Search for restaurants using Google Places Nearby Search API via HTTP
        """
        print(f"🔍 GOOGLE_PLACES_HTTP: Searching restaurants near {latitude}, {longitude}")

        # Convert miles to meters
        radius_meters = self.miles_to_meters(radius_miles)
        radius_meters = min(radius_meters, 50000)  # Google Places max radius

        # Build request parameters
        params = {
            "location": f"{latitude},{longitude}",
            "radius": radius_meters,
            "type": "restaurant",
            "key": self.api_key,
        }

        # Build keyword search from cuisine types and special occasion
        keywords = []

        if cuisine_types:
            keywords.extend(cuisine_types)

        # Add special occasion keywords to influence search results
        if special_occasion:
            occasion_lower = special_occasion.lower()
            if "anniversary" in occasion_lower or "romantic" in occasion_lower:
                keywords.extend(["romantic", "intimate", "fine dining"])
            elif "birthday" in occasion_lower or "celebration" in occasion_lower:
                keywords.extend(["celebration", "party", "festive"])
            elif "date" in occasion_lower:
                keywords.extend(["romantic", "intimate", "cozy"])
            elif "business" in occasion_lower or "meeting" in occasion_lower:
                keywords.extend(["quiet", "business friendly", "professional"])
            elif "family" in occasion_lower:
                keywords.extend(["family friendly", "kids", "casual"])

        if keywords:
            # Use OR for cuisine types, AND for occasion keywords
            cuisine_part = " OR ".join(cuisine_types) if cuisine_types else ""
            occasion_part = " ".join([k for k in keywords if k not in (cuisine_types or [])])

            if cuisine_part and occasion_part:
                keyword_string = f"({cuisine_part}) {occasion_part}"
            else:
                keyword_string = cuisine_part or occasion_part

            params["keyword"] = keyword_string
            print(f"🔍 GOOGLE_PLACES_HTTP: Adding keyword filter: {keyword_string}")
            print(f"🔍 GOOGLE_PLACES_HTTP: Special occasion '{special_occasion}' influencing search")

        if open_now:
            params["opennow"] = "true"

        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/place/nearbysearch/json", params=params, timeout=10.0
                )
                print(f"🔍 GOOGLE_PLACES_HTTP: API response status: {response.status_code}")

                if response.status_code != 200:
                    print(f"🔍 GOOGLE_PLACES_HTTP: API error: {response.text}")
                    return []

                data = response.json()
                places = data.get("results", [])
                print(f"🔍 GOOGLE_PLACES_HTTP: Found {len(places)} places from API")

                # Convert to our format
                restaurants = []
                for place in places:
                    # Filter by rating
                    rating = place.get("rating", 0)
                    if rating < min_rating:
                        continue

                    # Convert to our restaurant format
                    restaurant = self._convert_place_to_restaurant(place, latitude, longitude)

                    # Additional cuisine filtering as fallback - but trust Google Places API results
                    if cuisine_types:
                        restaurant_cuisine = restaurant["cuisine"].lower()
                        place_name = restaurant["name"].lower()
                        place_types = [t.lower() for t in place.get("types", [])]

                        # Check if any requested cuisine matches restaurant cuisine, name, or types
                        cuisine_match = any(
                            cuisine.lower() in restaurant_cuisine
                            or cuisine.lower() in place_name
                            or any(cuisine.lower() in place_type for place_type in place_types)
                            for cuisine in cuisine_types
                        )

                        # Only filter out if we're very confident it's wrong cuisine AND it's a common mismatch
                        if not cuisine_match and restaurant_cuisine != "restaurant":
                            # Only filter if we detected a different specific cuisine type
                            print(
                                f"🔍 GOOGLE_PLACES_HTTP: Filtering out {restaurant['name']} - detected cuisine '{restaurant['cuisine']}' doesn't match requested {cuisine_types}"
                            )
                            continue
                        elif not cuisine_match and restaurant_cuisine == "restaurant":
                            # If we couldn't detect cuisine but Google returned it, trust Google
                            print(
                                f"🔍 GOOGLE_PLACES_HTTP: Keeping {restaurant['name']} - trusting Google Places API result (cuisine detection failed)"
                            )
                            # Update cuisine to match what was requested since Google found it
                            restaurant["cuisine"] = (
                                cuisine_types[0] if cuisine_types else "Restaurant"
                            )

                    restaurants.append(restaurant)

                    if len(restaurants) >= max_results:
                        break

                print(f"🔍 GOOGLE_PLACES_HTTP: Returning {len(restaurants)} restaurants")
                return restaurants

        except Exception as e:
            print(f"🔍 GOOGLE_PLACES_HTTP: ❌ Error: {e}")
            return []

    def _convert_place_to_restaurant(
        self, place: dict[str, Any], user_lat: float, user_lng: float
    ) -> dict[str, Any]:
        """Convert Google Places API result to our restaurant format"""

        # Calculate distance
        geometry = place.get("geometry", {})
        location = geometry.get("location", {})
        place_lat = location.get("lat", 0)
        place_lng = location.get("lng", 0)
        distance_miles = self._calculate_distance(user_lat, user_lng, place_lat, place_lng)

        # Map price level to our format
        price_level_map = {0: "$", 1: "$", 2: "$$", 3: "$$$", 4: "$$$"}
        price_level = price_level_map.get(place.get("price_level", 1), "$$")

        # Extract cuisine type from place types and name
        try:
            restaurant_name = place.get("name", "")
            place_types = place.get("types", [])
            cuisine = self._extract_cuisine_type(place_types, restaurant_name)
            print(
                f"🔍 GOOGLE_PLACES_HTTP: Restaurant '{restaurant_name}' → types: {place_types} → cuisine: '{cuisine}'"
            )
        except Exception as e:
            print(f"🔍 GOOGLE_PLACES_HTTP: ❌ Error extracting cuisine: {e}")
            cuisine = "Restaurant"

        return {
            "id": f"gp_{place['place_id']}",
            "name": place.get("name", "Unknown Restaurant"),
            "cuisine": cuisine,
            "address": place.get("vicinity", place.get("formatted_address", "")),
            "distance_miles": round(distance_miles, 1),
            "price_level": price_level,
            "rating": place.get("rating", 0),
            "phone": place.get("formatted_phone_number", place.get("international_phone_number")),
            "google_place_id": place["place_id"],
            "google_place_data": place,
        }

    def _extract_cuisine_type(self, place_types: list[str], restaurant_name: str = "") -> str:
        """Extract cuisine type from Google Places types and restaurant name"""
        # First try Google Places types
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
            "steakhouse": "Steakhouse",
            "pizza_restaurant": "Pizza",
            "sushi_restaurant": "Japanese",
            "mediterranean_restaurant": "Mediterranean",
        }

        for place_type in place_types:
            if place_type in cuisine_map:
                return cuisine_map[place_type]

        # If Google Places types don't work, analyze restaurant name
        name_lower = restaurant_name.lower()

        # Chinese cuisine indicators
        if any(
            keyword in name_lower
            for keyword in [
                "china",
                "chinese",
                "chopstick",
                "wok",
                "panda",
                "dragon",
                "golden",
                "garden",
                "express",
                "house",
                "bao",
                "szechuan",
                "hunan",
                "canton",
            ]
        ):
            return "Chinese"

        # Italian cuisine indicators
        if any(
            keyword in name_lower
            for keyword in [
                "pizza",
                "italiano",
                "pasta",
                "luigi",
                "mario",
                "tony",
                "bella",
                "roma",
                "milano",
                "italian",
                "tuscany",
                "tuscan",
                "ristorante",
                "bistro",
                "buca",
                "fornaio",
                "caffe",
                "via",
                "fabian",
                "rubino",
            ]
        ):
            return "Italian"

        # Mexican cuisine indicators
        if any(
            keyword in name_lower
            for keyword in [
                "taco",
                "mexican",
                "burrito",
                "cantina",
                "maria",
                "jose",
                "salsa",
                "amigo",
                "fiesta",
            ]
        ):
            return "Mexican"

        # Japanese cuisine indicators
        if any(
            keyword in name_lower
            for keyword in [
                "sushi",
                "japanese",
                "ramen",
                "tokyo",
                "sakura",
                "zen",
                "ninja",
                "samurai",
                "bento",
            ]
        ):
            return "Japanese"

        # Indian cuisine indicators
        if any(
            keyword in name_lower
            for keyword in [
                "indian",
                "curry",
                "tandoor",
                "maharaja",
                "taj",
                "spice",
                "bombay",
                "delhi",
            ]
        ):
            return "Indian"

        # Thai cuisine indicators
        if any(
            keyword in name_lower
            for keyword in ["thai", "pad", "bangkok", "lemongrass", "basil", "coconut"]
        ):
            return "Thai"

        # Vietnamese cuisine indicators
        if any(
            keyword in name_lower
            for keyword in [
                "pho",
                "vietnamese",
                "viet",
                "saigon",
                "banh",
                "rolls",
                "spring",
                "urban",
                "nam",
                "bun",
                "com",
            ]
        ):
            return "Vietnamese"

        # American/Steakhouse indicators
        if any(
            keyword in name_lower
            for keyword in ["steak", "grill", "burger", "bbq", "american", "diner"]
        ):
            return "American"

        # Seafood indicators
        if any(
            keyword in name_lower
            for keyword in ["seafood", "fish", "crab", "lobster", "oyster", "shrimp"]
        ):
            return "Seafood"

        # Default based on common types
        if "restaurant" in place_types:
            return "Restaurant"
        elif "food" in place_types:
            return "Food"

        return "Restaurant"

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
_places_http_service = None


def get_google_places_http_service() -> GooglePlacesHTTPService:
    """Get singleton Google Places HTTP service instance"""
    global _places_http_service
    if _places_http_service is None:
        _places_http_service = GooglePlacesHTTPService()
    return _places_http_service
