import requests
import json
import math
import pandas as pd

API_KEY = ""

# Input configuration
center_lat = 34.849303            # Center latitude
center_lng = -117.085266          # Center longitude
radius_miles = 20               # Search radius in miles
business_categories = ["event_venue"]

# Convert radius to meters for Places API
radius_meters = radius_miles * 1609.34

# Approximation settings
AVG_DRIVING_SPEED_MPH = 40.0    
ROAD_BUFFER_FACTOR = 1.4        

# Haversine distance in miles
def haversine_distance(lat1, lng1, lat2, lng2):
    R = 3958.8  # Earth radius in miles
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = (
        math.sin(dlat / 2) ** 2
        + math.cos(math.radians(lat1))
        * math.cos(math.radians(lat2))
        * math.sin(dlng / 2) ** 2
    )
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# Offsets for multi-center coverage (N/S/E/W + original)
delta_lat = radius_miles / 69.0
delta_lng = radius_miles / (69.0 * math.cos(math.radians(center_lat)))

centers = [
    {"lat": center_lat, "lng": center_lng},
    {"lat": center_lat + delta_lat, "lng": center_lng},
    {"lat": center_lat - delta_lat, "lng": center_lng},
    {"lat": center_lat, "lng": center_lng + delta_lng},
    {"lat": center_lat, "lng": center_lng - delta_lng},
]

# Dedup container
unique_places = {}

# Places API configuration
url = "https://places.googleapis.com/v1/places:searchNearby"
headers = {
    "Content-Type": "application/json",
    "X-Goog-Api-Key": API_KEY,
    "X-Goog-FieldMask": (
        "places.displayName,places.location,places.rating,places.userRatingCount,"
        "places.types,places.websiteUri,places.internationalPhoneNumber,"
        "places.businessStatus,places.googleMapsUri,places.id,places.formattedAddress"
    ),
}
body_template = {
    "locationRestriction": {
        "circle": {
            "center": {"latitude": 0, "longitude": 0},
            "radius": radius_meters,
        }
    },
    "includedTypes": business_categories,
    "maxResultCount": 20,
}

# -------------------------
# 1. Fetch from all centers and dedupe
# -------------------------
for center in centers:
    body = json.loads(json.dumps(body_template))  # deep copy
    body["locationRestriction"]["circle"]["center"]["latitude"] = center["lat"]
    body["locationRestriction"]["circle"]["center"]["longitude"] = center["lng"]

    try:
        response = requests.post(url, headers=headers, json=body)
        response.raise_for_status()
        data = response.json()

        if "places" not in data:
            print(f"No places for center {center}")
            continue

        for place in data["places"]:
            place_id = place.get("id")
            if place_id and place_id not in unique_places:
                unique_places[place_id] = place

        print(f"Fetched {len(data['places'])} places for center {center}")

    except requests.RequestException as e:
        print(f"Request error for center {center}: {e}")
        if getattr(e, "response", None) is not None:
            print(f"Response text: {e.response.text}")
        continue
    except json.JSONDecodeError as e:
        print(f"JSON decode error for center {center}: {e}")
        continue

# Convert unique places to list and filter operational
places = list(unique_places.values())
operational_places = [p for p in places if p.get("businessStatus") == "OPERATIONAL"]

if not operational_places:
    print("No operational places found.")
    exit(0)

# -------------------------
# 2. Compute approx distance & duration, filter by radius
# -------------------------
results = []

for place in operational_places:
    loc = place.get("location") or {}
    place_lat = loc.get("latitude")
    place_lng = loc.get("longitude")
    if place_lat is None or place_lng is None:
        continue

    # Straight-line distance in miles
    straight_miles = haversine_distance(center_lat, center_lng, place_lat, place_lng)

    # Approx driving distance & duration
    driving_miles = straight_miles * ROAD_BUFFER_FACTOR
    duration_minutes = (driving_miles / AVG_DRIVING_SPEED_MPH) * 60

    # Filter: keep only if driving distance <= radius
    if driving_miles > radius_miles:
        continue

    # Format for UI like "0.8 mi" and "3 mins"
    distance_str = f"{round(driving_miles, 1)} mi"
    duration_str = f"{duration_minutes:.0f} mins"

    result = {
        "Business Name": place.get("displayName", {}).get("text", ""),
        "Business Status": place.get("businessStatus", ""),
        "Rating": place.get("rating", ""),
        "Rating Count": place.get("userRatingCount", ""),
        "Business Type": place.get("types", [None])[0] if place.get("types") else "",
        "Google Place URL": place.get("googleMapsUri", ""),
        "Phone Number": place.get("internationalPhoneNumber", ""),
        "Website": place.get("websiteUri", ""),
        "Address": place.get("formattedAddress", ""),
        "distanceInMiles": distance_str,          
        "duration": duration_str,                 
        "placeId": place.get("id", ""),
    }
    results.append(result)

if not results:
    print("No places within the specified driving distance radius.")
    exit(0)

# 3. Output

df = pd.DataFrame(results)
print(df)

try:
    df.to_csv("output.csv", index=False)
    print("Results saved to output.csv")
except PermissionError as e:
    print(f"Permission error saving output.csv: {e}")


