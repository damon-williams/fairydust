# services/content/google_places_service.py
import os
import hashlib
from typing import List, Dict, Any, Optional
from datetime import datetime, timedelta

try:
    import googlemaps
    GOOGLEMAPS_AVAILABLE = True
    print("🔍 GOOGLE_PLACES_DEBUG: ✅ googlemaps package imported successfully")
except ImportError as e:
    GOOGLEMAPS_AVAILABLE = False
    googlemaps = None
    print(f"🔍 GOOGLE_PLACES_DEBUG: ❌ googlemaps package not available: {e}")

class GooglePlacesService:
    """Service for interacting with Google Places API"""
    
    def __init__(self):
        print("🔍 GOOGLE_PLACES_DEBUG: Initializing GooglePlacesService...")
        if not GOOGLEMAPS_AVAILABLE:
            print("🔍 GOOGLE_PLACES_DEBUG: ❌ googlemaps package not available")
            raise ImportError("googlemaps package is not installed. Please install it with: pip install googlemaps")
        
        self.api_key = os.getenv("GOOGLE_PLACES_API_KEY")
        print(f"🔍 GOOGLE_PLACES_DEBUG: API key {'✅ found' if self.api_key else '❌ missing'}")
        if not self.api_key:
            raise ValueError("GOOGLE_PLACES_API_KEY environment variable is required")
        
        print("🔍 GOOGLE_PLACES_DEBUG: Creating googlemaps client...")
        self.client = googlemaps.Client(key=self.api_key)
        print("🔍 GOOGLE_PLACES_DEBUG: ✅ GooglePlacesService initialized successfully")
        
    def generate_location_hash(self, latitude: float, longitude: float, radius_miles: int) -> str:
        """Generate a hash for location-based caching"""
        # Round coordinates to ~0.1 mile precision for caching
        lat_rounded = round(latitude, 3)
        lng_rounded = round(longitude, 3)
        cache_key = f"{lat_rounded},{lng_rounded},{radius_miles}"
        return hashlib.md5(cache_key.encode()).hexdigest()
    
    def miles_to_meters(self, miles: float) -> int:
        """Convert miles to meters for Google Places API"""
        return int(miles * 1609.34)
    
    def search_restaurants(
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
        Search for restaurants using Google Places Nearby Search API
        
        Args:
            latitude: Latitude coordinate
            longitude: Longitude coordinate  
            radius_miles: Search radius in miles (max 31 miles)
            cuisine_types: List of cuisine types to filter by
            open_now: Whether to only return currently open restaurants
            min_rating: Minimum rating filter
            max_results: Maximum number of results to return
            
        Returns:
            List of restaurant data dictionaries
        """
        if not self.api_key:
            raise ValueError("Google Places API key not configured")
        
        # Convert miles to meters (Google Places API uses meters)
        radius_meters = self.miles_to_meters(radius_miles)
        
        # Google Places API has a max radius of 50km (31 miles)
        radius_meters = min(radius_meters, 50000)
        
        try:
            # Perform the nearby search
            places_result = self.client.places_nearby(
                location=(latitude, longitude),
                radius=radius_meters,
                type='restaurant',
                open_now=open_now,
                min_price=0,  # Include all price levels
                max_price=4   # 0-4 scale
            )
            
            restaurants = []
            for place in places_result.get('results', []):
                # Filter by rating
                rating = place.get('rating', 0)
                if rating < min_rating:
                    continue
                
                # Filter by cuisine if specified
                if cuisine_types:
                    place_types = place.get('types', [])
                    # Simple cuisine matching - could be enhanced
                    cuisine_match = any(
                        cuisine.lower() in ' '.join(place_types).lower() 
                        for cuisine in cuisine_types
                    )
                    if not cuisine_match:
                        continue
                
                # Convert to our restaurant format
                restaurant = self._convert_place_to_restaurant(place, latitude, longitude)
                restaurants.append(restaurant)
                
                if len(restaurants) >= max_results:
                    break
            
            return restaurants
            
        except Exception as e:
            print(f"Google Places API error: {e}")
            return []
    
    def _convert_place_to_restaurant(self, place: Dict[str, Any], user_lat: float, user_lng: float) -> Dict[str, Any]:
        """Convert Google Places API result to our restaurant format"""
        
        # Calculate distance
        place_lat = place['geometry']['location']['lat']
        place_lng = place['geometry']['location']['lng']
        distance_miles = self._calculate_distance(user_lat, user_lng, place_lat, place_lng)
        
        # Map price level to our format
        price_level_map = {0: "$", 1: "$", 2: "$$", 3: "$$$", 4: "$$$"}
        price_level = price_level_map.get(place.get('price_level', 1), "$$")
        
        # Extract cuisine type from place types
        cuisine = self._extract_cuisine_type(place.get('types', []))
        
        # Format phone number
        phone = place.get('formatted_phone_number', place.get('international_phone_number'))
        
        return {
            'id': f"gp_{place['place_id']}",
            'name': place['name'],
            'cuisine': cuisine,
            'address': place.get('vicinity', place.get('formatted_address', '')),
            'distance_miles': round(distance_miles, 1),
            'price_level': price_level,
            'rating': place.get('rating', 0),
            'phone': phone,
            'google_place_id': place['place_id'],
            'google_place_data': place  # Store full data for future use
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
        from math import radians, sin, cos, sqrt, atan2
        
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
_places_service = None

def get_google_places_service() -> GooglePlacesService:
    """Get singleton Google Places service instance"""
    print("🔍 GOOGLE_PLACES_DEBUG: get_google_places_service() called")
    global _places_service
    if _places_service is None:
        print("🔍 GOOGLE_PLACES_DEBUG: Creating new GooglePlacesService instance...")
        if not GOOGLEMAPS_AVAILABLE:
            print("🔍 GOOGLE_PLACES_DEBUG: ❌ googlemaps package not available, raising ImportError")
            raise ImportError("googlemaps package is not available. Falling back to mock data.")
        _places_service = GooglePlacesService()
        print("🔍 GOOGLE_PLACES_DEBUG: ✅ Singleton instance created")
    else:
        print("🔍 GOOGLE_PLACES_DEBUG: ✅ Returning existing singleton instance")
    return _places_service