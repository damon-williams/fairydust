# services/content/google_places_http.py
"""
Google Places API integration using direct HTTP calls instead of googlemaps package
This bypasses any package installation issues
"""

import os
import json
import httpx
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta
from math import radians, sin, cos, sqrt, atan2

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
        cuisine_types: List[str] = None,
        open_now: bool = False,
        min_rating: float = 3.5,
        max_results: int = 20
    ) -> List[Dict[str, Any]]:
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
            "key": self.api_key
        }
        
        if open_now:
            params["opennow"] = "true"
        
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.base_url}/place/nearbysearch/json",
                    params=params,
                    timeout=10.0
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
                    restaurants.append(restaurant)
                    
                    if len(restaurants) >= max_results:
                        break
                
                print(f"🔍 GOOGLE_PLACES_HTTP: Returning {len(restaurants)} restaurants")
                return restaurants
                
        except Exception as e:
            print(f"🔍 GOOGLE_PLACES_HTTP: ❌ Error: {e}")
            return []
    
    def _convert_place_to_restaurant(self, place: Dict[str, Any], user_lat: float, user_lng: float) -> Dict[str, Any]:
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
        
        # Extract cuisine type from place types
        cuisine = self._extract_cuisine_type(place.get("types", []))
        
        return {
            'id': f"gp_{place['place_id']}",
            'name': place.get('name', 'Unknown Restaurant'),
            'cuisine': cuisine,
            'address': place.get('vicinity', place.get('formatted_address', '')),
            'distance_miles': round(distance_miles, 1),
            'price_level': price_level,
            'rating': place.get('rating', 0),
            'phone': place.get('formatted_phone_number', place.get('international_phone_number')),
            'google_place_id': place['place_id'],
            'google_place_data': place
        }
    
    def _extract_cuisine_type(self, place_types: List[str]) -> str:
        """Extract cuisine type from Google Places types"""
        cuisine_map = {
            'italian_restaurant': 'Italian',
            'chinese_restaurant': 'Chinese', 
            'japanese_restaurant': 'Japanese',
            'mexican_restaurant': 'Mexican',
            'indian_restaurant': 'Indian',
            'thai_restaurant': 'Thai',
            'french_restaurant': 'French',
            'american_restaurant': 'American',
            'seafood_restaurant': 'Seafood',
            'steakhouse': 'Steakhouse',
            'pizza_restaurant': 'Pizza',
            'sushi_restaurant': 'Japanese',
            'mediterranean_restaurant': 'Mediterranean'
        }
        
        for place_type in place_types:
            if place_type in cuisine_map:
                return cuisine_map[place_type]
        
        # Default based on common types
        if 'restaurant' in place_types:
            return 'Restaurant'
        elif 'food' in place_types:
            return 'Food'
        
        return 'Restaurant'
    
    def _calculate_distance(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two coordinates in miles using Haversine formula"""
        # Convert to radians
        lat1, lon1, lat2, lon2 = map(radians, [lat1, lon1, lat2, lon2])
        
        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = sin(dlat/2)**2 + cos(lat1) * cos(lat2) * sin(dlon/2)**2
        c = 2 * atan2(sqrt(a), sqrt(1-a))
        
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