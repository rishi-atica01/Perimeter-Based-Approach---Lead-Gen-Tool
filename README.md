# Perimeter-Based-Approach---Lead-Gen-Tool

This repository contains a Python reference implementation for a perimeter-based lead generation approach using the Google Places API.

The code is intended as a logic reference to be translated and integrated into the production Java codebase.

High-Level Approach

Perimeter-based search using 5 centers (property center + North, South, East, West)

Maximizes lead coverage across the full selected radius

Deduplicates results using place_id

Filters leads within the selected radius

Sorts results by estimated driving distance

Distance & Duration Calculation

The current implementation does not use the Google Distance Matrix API.

Driving duration is estimated using:

Straight-line (Haversine) distance

Configurable average driving speed (MPH)

Configurable road buffer factor to account for road detours

This approach keeps the logic deterministic, cost-efficient, and stable for v1. Distance Matrix API integration can be added later if higher routing accuracy is required.

Output

The script generates a CSV containing:

Business name

Category / business type

Business Name,	Business Status,	Rating,	Rating Count,	Business Type,	Google Place URL,	Phone Number,	Website,	Address,	distanceInMiles,	duration,	placeId

Notes

This is a reference implementation, not production code

Saturation-based expansion is intentionally excluded in v1 to avoid lead loss

Keyword-based industry search is a future enhancement
