import requests
import json
import math
import pandas as pd

API_KEY = "AIzaSyAt4l5Fz_YUkhuhhJS7cXtb-oApW4TimIc"

# Input configuration
center_lat = 34.849303            # Center latitude
center_lng = -117.085266          # Center longitude
radius_miles = 20                 # Search radius in miles
business_categories = ["event_venue"]

# Dynamic expansion settings
SATURATION_THRESHOLD = 20         # If results == this, add more centers
MIN_UNIQUE_LEADS = 100            # Minimum unique leads before stopping
DISTANCE_SPREAD_THRESHOLD = 0.5   # If >50% of results within 50% of radius, expand

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

# Generate centers dynamically (max 5: center + N/S/E/W)
def generate_centers_dynamic(center_lat, center_lng, radius_miles, expansion_level=1):
    """
    expansion_level 1: Original center only
    expansion_level 2: Add N/S/E/W (total 5)
    Max expansion is 5 centers only.
    """
    delta_lat = radius_miles / 69.0
    delta_lng = radius_miles / (69.0 * math.cos(math.radians(center_lat)))
    
    centers = [{"lat": center_lat, "lng": center_lng}]
    
    if expansion_level >= 2:
        centers.extend([
            {"lat": center_lat + delta_lat, "lng": center_lng},
            {"lat": center_lat - delta_lat, "lng": center_lng},
            {"lat": center_lat, "lng": center_lng + delta_lng},
            {"lat": center_lat, "lng": center_lng - delta_lng},
        ])
    
    return centers

# Check if results are saturated (API returned max count)
def is_search_saturated(result_count, max_result_count=20):
    """True if we got max results, indicating more data might exist."""
    return result_count >= max_result_count

# Check distance spread of results
def check_distance_spread(places, center_lat, center_lng, radius_miles, threshold_ratio=0.5):
    """
    Returns True if results are clustered close to center (expansion needed).
    threshold_ratio: If >50% of results within 50% of radius, return True.
    """
    if not places:
        return False
    
    threshold_distance = radius_miles * threshold_ratio
    close_results = 0
    
    for place in places:
        loc = place.get("location") or {}
        place_lat = loc.get("latitude")
        place_lng = loc.get("longitude")
        if place_lat is None or place_lng is None:
            continue
        
        straight_miles = haversine_distance(center_lat, center_lng, place_lat, place_lng)
        if straight_miles <= threshold_distance:
            close_results += 1
    
    # If more than 50% of results are clustered, we need to expand
    return (close_results / len(places)) > 0.5 if places else False

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
# DYNAMIC EXPANSION LOOP
# -------------------------
expansion_level = 1
max_expansion_level = 2  # Only 1 and 2 (center only, or center + N/S/E/W = 5 total)
iteration = 0

while expansion_level <= max_expansion_level:
    iteration += 1
    print(f"\n--- Iteration {iteration} (Expansion Level {expansion_level}) ---")
    
    centers = generate_centers_dynamic(center_lat, center_lng, radius_miles, expansion_level)
    print(f"Searching with {len(centers)} centers")
    
    iteration_new_results = 0
    all_iteration_results = []
    saturation_count = 0
    
    # Fetch from all centers at current expansion level
    for center in centers:
        body = json.loads(json.dumps(body_template))  # deep copy
        body["locationRestriction"]["circle"]["center"]["latitude"] = center["lat"]
        body["locationRestriction"]["circle"]["center"]["longitude"] = center["lng"]

        try:
            response = requests.post(url, headers=headers, json=body)
            response.raise_for_status()
            data = response.json()

            if "places" not in data:
                print(f"  No places for center ({center['lat']:.4f}, {center['lng']:.4f})")
                continue

            places_count = len(data["places"])
            all_iteration_results.extend(data["places"])
            
            # Track saturation
            if is_search_saturated(places_count):
                saturation_count += 1
            
            # Count new unique results
            for place in data["places"]:
                place_id = place.get("id")
                if place_id and place_id not in unique_places:
                    unique_places[place_id] = place
                    iteration_new_results += 1

            print(f"  Center ({center['lat']:.4f}, {center['lng']:.4f}): {places_count} results")

        except requests.RequestException as e:
            print(f"  Request error for center {center}: {e}")
            if getattr(e, "response", None) is not None:
                print(f"  Response text: {e.response.text}")
            continue
        except json.JSONDecodeError as e:
            print(f"  JSON decode error for center {center}: {e}")
            continue
    
    print(f"New results this iteration: {iteration_new_results}")
    print(f"Unique leads so far: {len(unique_places)}")
    
    # --- DECISION LOGIC FOR EXPANSION ---
    should_expand = False
    expansion_reason = ""
    
    # Only consider expansion if we're not at max level
    if expansion_level < max_expansion_level:
        # 1. Saturation Check: Any center hit max results?
        if saturation_count > 0:
            should_expand = True
            expansion_reason = f"SATURATION: {saturation_count} center(s) maxed out at 20 results"
        
        # 2. Distance Spread Check: Are results clustered?
        elif all_iteration_results and check_distance_spread(all_iteration_results, center_lat, center_lng, radius_miles, DISTANCE_SPREAD_THRESHOLD):
            should_expand = True
            expansion_reason = "CLUSTERING: Results clustered near center (>50% within 50% radius)"
    
    # 3. Lead Threshold Check: Have we hit minimum?
    if len(unique_places) >= MIN_UNIQUE_LEADS:
        print(f"✓ Reached minimum lead threshold ({MIN_UNIQUE_LEADS})")
        break
    
    # Decide to expand
    if should_expand:
        print(f"→ Expanding search ({expansion_reason})")
        expansion_level += 1
    elif expansion_level >= max_expansion_level:
        print(f"✓ Reached maximum expansion level (5 centers)")
        break
    else:
        print(f"✓ Stopping expansion (no saturation/clustering detected)")
        break

# Convert unique places to list and filter operational
places = list(unique_places.values())
operational_places = [p for p in places if p.get("businessStatus") == "OPERATIONAL"]

print(f"\nTotal unique places found: {len(unique_places)}")
print(f"Operational places: {len(operational_places)}")

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
print(f"\n{'='*60}")
print(f"Final Results: {len(df)} places within {radius_miles} mile radius")
print(f"{'='*60}\n")
print(df)

try:
    df.to_csv("output.csv", index=False)
    print(f"\nResults saved to output.csv")
except PermissionError as e:
    print(f"Permission error saving output.csv: {e}")
