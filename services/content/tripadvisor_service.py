# services/content/tripadvisor_service.py
from typing import Optional

import httpx
import math
from models import ActivityHours


class TripAdvisorService:
    def __init__(self, api_key: str):
        self.api_key = api_key
        self.base_url = "https://api.content.tripadvisor.com/api/v1"
        self.headers = {"X-API-KEY": api_key}

    async def search_nearby_activities(
        self, latitude: float, longitude: float, radius_miles: int, location_type: str = "both"
    ) -> tuple[list[dict], int]:
        """
        Search for nearby activities using TripAdvisor API
        Returns (activities_list, total_count)
        """
        print(
            f"🏛️ ACTIVITY_SEARCH: Searching TripAdvisor near {latitude},{longitude} radius={radius_miles}mi",
            flush=True,
        )

        # Convert miles to km for TripAdvisor API
        radius_km = int(radius_miles * 1.609344)

        # Determine category based on location_type
        categories = self._get_search_categories(location_type)

        all_activities = []
        total_found = 0

        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                for category in categories:
                    print(f"🔍 ACTIVITY_SEARCH: Searching category '{category}'", flush=True)

                    params = {
                        "latLong": f"{latitude},{longitude}",
                        "radius": radius_km,
                        "radiusUnit": "km",
                        "category": category,
                        "limit": 30,  # Get more results to filter and prioritize
                    }

                    print(f"🔍 TRIPADVISOR_DEBUG: API Key: {self.api_key[:10]}...", flush=True)
                    print(f"🔍 TRIPADVISOR_DEBUG: Headers: {self.headers}", flush=True)
                    print(f"🔍 TRIPADVISOR_DEBUG: URL: {self.base_url}/location/nearby_search", flush=True)
                    print(f"🔍 TRIPADVISOR_DEBUG: Params: {params}", flush=True)

                    response = await client.get(
                        f"{self.base_url}/location/nearby_search",
                        headers=self.headers,
                        params=params,
                    )

                    if response.status_code == 200:
                        data = response.json()
                        locations = data.get("data", [])
                        print(
                            f"✅ ACTIVITY_SEARCH: Found {len(locations)} {category} results",
                            flush=True,
                        )

                        for location in locations:
                            activity_data = await self._enrich_location_data(
                                location, latitude, longitude
                            )
                            if activity_data:
                                all_activities.append(activity_data)

                        total_found += len(locations)
                    else:
                        print(
                            f"❌ ACTIVITY_SEARCH: TripAdvisor API error {response.status_code}: {response.text}",
                            flush=True,
                        )
                        
                        # Temporary fallback while waiting for TripAdvisor API access
                        if response.status_code == 401:
                            print("🔄 ACTIVITY_SEARCH: Using fallback mock data due to API authentication issue", flush=True)
                            mock_activities = self._get_mock_activities(latitude, longitude, category)
                            all_activities.extend(mock_activities)
                            total_found += len(mock_activities)

        except Exception as e:
            print(f"❌ ACTIVITY_SEARCH: Error searching TripAdvisor: {str(e)}", flush=True)
            raise

        print(f"📊 ACTIVITY_SEARCH: Total activities found: {len(all_activities)}", flush=True)
        return all_activities, total_found

    def _get_search_categories(self, location_type: str) -> list[str]:
        """Map location_type to TripAdvisor categories"""
        if location_type == "attractions":
            return ["attractions"]
        elif location_type == "destinations":
            return ["geos"]  # Geographic locations like parks, beaches
        else:  # both
            return ["attractions", "geos"]

    async def _enrich_location_data(
        self, location: dict, search_lat: float, search_lng: float
    ) -> Optional[dict]:
        """Enrich basic location data with details and photos"""
        try:
            location_id = location.get("location_id")
            if not location_id:
                return None

            # Get detailed information
            details = await self._get_location_details(location_id)
            photos = await self._get_location_photos(location_id)

            # Calculate distance using simple haversine formula
            lat1, lon1 = search_lat, search_lng
            lat2, lon2 = float(location.get("latitude", 0)), float(location.get("longitude", 0))
            distance_miles = self._calculate_distance_miles(lat1, lon1, lat2, lon2)

            # Determine activity type
            activity_type = self._determine_activity_type(location, details)

            return {
                "tripadvisor_id": location_id,
                "name": location.get("name", ""),
                "type": activity_type,
                "address": location.get("address_obj", {}).get("address_string", ""),
                "latitude": float(location.get("latitude", 0)),
                "longitude": float(location.get("longitude", 0)),
                "distance_miles": round(distance_miles, 1),
                "rating": float(location.get("rating", 0)) if location.get("rating") else None,
                "num_reviews": int(location.get("num_reviews", 0))
                if location.get("num_reviews")
                else None,
                "price_level": self._convert_price_level(location.get("price_level")),
                "photos": photos[:5],  # Limit to 5 photos
                "hours": self._parse_hours(details.get("hours")),
                "current_status": self._determine_current_status(details.get("hours")),
                "phone": details.get("phone"),
                "website": details.get("website"),
                "raw_details": details,  # Keep for AI context generation
            }

        except Exception as e:
            print(
                f"⚠️ ACTIVITY_SEARCH: Error enriching location {location.get('location_id')}: {str(e)}",
                flush=True,
            )
            return None

    async def _get_location_details(self, location_id: str) -> dict:
        """Get detailed information for a location"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self.base_url}/location/{location_id}/details", headers=self.headers
                )

                if response.status_code == 200:
                    return response.json()
                else:
                    print(
                        f"⚠️ ACTIVITY_DETAILS: Error getting details for {location_id}: {response.status_code}",
                        flush=True,
                    )
                    return {}

        except Exception as e:
            print(
                f"⚠️ ACTIVITY_DETAILS: Exception getting details for {location_id}: {str(e)}",
                flush=True,
            )
            return {}

    async def _get_location_photos(self, location_id: str) -> list[str]:
        """Get photo URLs for a location"""
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                response = await client.get(
                    f"{self.base_url}/location/{location_id}/photos",
                    headers=self.headers,
                    params={"limit": 5},
                )

                if response.status_code == 200:
                    data = response.json()
                    photos = []
                    for photo in data.get("data", []):
                        # Get the largest available image
                        images = photo.get("images", {})
                        if "large" in images:
                            photos.append(images["large"]["url"])
                        elif "medium" in images:
                            photos.append(images["medium"]["url"])
                        elif "small" in images:
                            photos.append(images["small"]["url"])
                    return photos
                else:
                    print(
                        f"⚠️ ACTIVITY_PHOTOS: Error getting photos for {location_id}: {response.status_code}",
                        flush=True,
                    )
                    return []

        except Exception as e:
            print(
                f"⚠️ ACTIVITY_PHOTOS: Exception getting photos for {location_id}: {str(e)}",
                flush=True,
            )
            return []

    def _determine_activity_type(self, location: dict, details: dict) -> str:
        """Determine if location is attraction or destination"""
        # Check subcategory or category information
        subcategories = location.get("subcategory", [])
        category = location.get("category", {}).get("name", "").lower()

        # Nature/outdoor locations are destinations
        nature_keywords = [
            "park",
            "beach",
            "trail",
            "nature",
            "outdoor",
            "scenic",
            "garden",
            "lake",
            "mountain",
        ]
        if any(keyword in category for keyword in nature_keywords):
            return "destination"

        # Museums, tours, entertainment are attractions
        attraction_keywords = [
            "museum",
            "tour",
            "entertainment",
            "theater",
            "gallery",
            "aquarium",
            "zoo",
        ]
        if any(keyword in category for keyword in attraction_keywords):
            return "attraction"

        # Default based on subcategories
        if subcategories:
            return "attraction"
        else:
            return "destination"

    def _convert_price_level(self, price_level: str) -> Optional[str]:
        """Convert TripAdvisor price level to our format"""
        if not price_level:
            return None

        price_map = {"$": "$", "$$": "$$", "$$$": "$$$", "$$$$": "$$$$"}
        return price_map.get(price_level)

    def _parse_hours(self, hours_data: dict) -> Optional[ActivityHours]:
        """Parse TripAdvisor hours format to our format"""
        if not hours_data or not isinstance(hours_data, dict):
            return None

        try:
            # TripAdvisor hours format varies, try to parse common formats
            week_ranges = hours_data.get("week_ranges", [])
            if not week_ranges:
                return None

            # Map day numbers to day names (0=Sunday, 1=Monday, etc.)
            day_names = [
                "sunday",
                "monday",
                "tuesday",
                "wednesday",
                "thursday",
                "friday",
                "saturday",
            ]
            parsed_hours = {}

            for week_range in week_ranges:
                open_time = week_range.get("open_time")
                close_time = week_range.get("close_time")
                days = week_range.get("days", [])

                if open_time and close_time and days:
                    time_str = f"{open_time} - {close_time}"
                    for day_num in days:
                        if 0 <= day_num < len(day_names):
                            parsed_hours[day_names[day_num]] = time_str

            return ActivityHours(**parsed_hours) if parsed_hours else None

        except Exception as e:
            print(f"⚠️ ACTIVITY_HOURS: Error parsing hours: {str(e)}", flush=True)
            return None

    def _determine_current_status(self, hours_data: dict) -> Optional[str]:
        """Determine if location is currently open/closed"""
        if not hours_data:
            return None

        try:
            # This is a simplified implementation
            # In a real app, you'd check current time against parsed hours
            # and consider timezone of the location

            # For now, return None to indicate unknown status
            return None

        except Exception:
            return None

    def _calculate_distance_miles(self, lat1: float, lon1: float, lat2: float, lon2: float) -> float:
        """Calculate distance between two coordinates using haversine formula"""
        # Convert latitude and longitude from degrees to radians
        lat1, lon1, lat2, lon2 = map(math.radians, [lat1, lon1, lat2, lon2])
        
        # Haversine formula
        dlat = lat2 - lat1
        dlon = lon2 - lon1
        a = math.sin(dlat/2)**2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon/2)**2
        c = 2 * math.asin(math.sqrt(a))
        
        # Radius of earth in miles
        r = 3956
        
        return round(c * r, 1)

    def get_location_address(self, latitude: float, longitude: float) -> str:
        """Get human-readable address from coordinates (simplified)"""
        # In a real implementation, you'd use reverse geocoding
        # For now, return a basic coordinate string
        return f"{latitude:.4f}, {longitude:.4f}"
    
    def _get_mock_activities(self, latitude: float, longitude: float, category: str) -> list[dict]:
        """Temporary mock data while waiting for TripAdvisor API access"""
        base_activities = []
        
        if category == "attractions":
            base_activities = [
                {
                    "tripadvisor_id": "mock_museum_1",
                    "name": "Local History Museum",
                    "type": "attraction",
                    "address": "123 Main Street",
                    "latitude": latitude + 0.01,
                    "longitude": longitude + 0.01,
                    "distance_miles": 1.2,
                    "rating": 4.3,
                    "num_reviews": 156,
                    "price_level": "$",
                    "photos": ["https://example.com/museum1.jpg"],
                    "hours": None,
                    "current_status": None,
                    "phone": "(555) 123-4567",
                    "website": "https://example.com",
                    "raw_details": {}
                },
                {
                    "tripadvisor_id": "mock_theater_1",
                    "name": "Community Theater",
                    "type": "attraction", 
                    "address": "456 Arts Avenue",
                    "latitude": latitude - 0.02,
                    "longitude": longitude + 0.02,
                    "distance_miles": 2.8,
                    "rating": 4.7,
                    "num_reviews": 89,
                    "price_level": "$$",
                    "photos": ["https://example.com/theater1.jpg"],
                    "hours": None,
                    "current_status": None,
                    "phone": "(555) 234-5678",
                    "website": "https://example.com",
                    "raw_details": {}
                }
            ]
        elif category == "geos":
            base_activities = [
                {
                    "tripadvisor_id": "mock_park_1",
                    "name": "Riverside Park",
                    "type": "destination",
                    "address": "789 River Road",
                    "latitude": latitude + 0.03,
                    "longitude": longitude - 0.01,
                    "distance_miles": 3.5,
                    "rating": 4.1,
                    "num_reviews": 203,
                    "price_level": None,
                    "photos": ["https://example.com/park1.jpg"],
                    "hours": None,
                    "current_status": None,
                    "phone": None,
                    "website": None,
                    "raw_details": {}
                },
                {
                    "tripadvisor_id": "mock_trail_1", 
                    "name": "Nature Walking Trail",
                    "type": "destination",
                    "address": "Mountain View Drive",
                    "latitude": latitude - 0.01,
                    "longitude": longitude - 0.03,
                    "distance_miles": 4.2,
                    "rating": 4.5,
                    "num_reviews": 67,
                    "price_level": None,
                    "photos": ["https://example.com/trail1.jpg"],
                    "hours": None,
                    "current_status": None,
                    "phone": None,
                    "website": None,
                    "raw_details": {}
                }
            ]
        
        return base_activities
