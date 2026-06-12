import os
import requests
import urllib3
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
from typing import Optional

GOOGLE_MAPS_API_KEY = os.getenv("GOOGLE_MAPS_API_KEY", "").strip()

DEFAULT_CITY_CONTEXT = "Gqeberha, Eastern Cape, South Africa"

def normalize_local_address(address: str) -> str:
    address = address.strip()
    lowered = address.lower()

    has_sa_context = any(x in lowered for x in [
        "gqeberha",
        "port elizabeth",
        "eastern cape",
        "south africa",
        "kariega",
        "uitenhage",
        "despatch",
        "nelson mandela bay",
    ])

    if not has_sa_context:
        return f"{address}, {DEFAULT_CITY_CONTEXT}"

    return address

def build_search_queries(query: str) -> list[str]:
    query = query.strip()
    queries = []

    def add(value: str):
        value = value.strip()
        if value and value not in queries:
            queries.append(value)

    add(query)
    add(normalize_local_address(query))

    normalized = normalize_local_address(query)

    # Some map data still uses Port Elizabeth instead of Gqeberha.
    if "Gqeberha" in normalized:
        add(normalized.replace("Gqeberha", "Port Elizabeth"))

    if "Port Elizabeth" in normalized:
        add(normalized.replace("Port Elizabeth", "Gqeberha"))

    return queries

def suggest_addresses(query: str) -> list[dict]:
    query = query.strip()
    if len(query) < 3:
        return []

    results = []
    seen = set()

    def add_items(items):
        for item in items:
            key = f"{item.get('lat')}|{item.get('lon')}|{item.get('label')}"
            if key in seen:
                continue
            seen.add(key)
            results.append(item)

    if GOOGLE_MAPS_API_KEY:
        add_items(suggest_with_google(query))

    add_items(suggest_with_osm(query))
    add_items(suggest_with_photon(query))
    add_items(suggest_with_local_fallback(query))

    if not results:
        add_items(typed_address_fallback(query))

    return results[:10]


def suggest_with_google(query: str) -> list[dict]:
    url = "https://maps.googleapis.com/maps/api/place/autocomplete/json"
    params = {
        "input": query,
        "components": "country:za",
        "key": GOOGLE_MAPS_API_KEY,
    }

    try:
        res = requests.get(url, params=params, timeout=15)
        res.raise_for_status()
        data = res.json()

        suggestions = []
        for item in data.get("predictions", [])[:8]:
            suggestions.append({
                "label": item.get("description"),
                "value": item.get("description"),
                "provider": "google_places",
                "place_id": item.get("place_id"),
                "lat": None,
                "lon": None,
            })

        return suggestions

    except Exception:
        return []

def suggest_with_osm(query: str) -> list[dict]:
    headers = {
        "User-Agent": "MoveangoQuoteGenerator/1.1 contact: hello@moveango.co.za"
    }

    suggestions = []
    seen = set()

    for q in build_search_queries(query):
        url = "https://nominatim.openstreetmap.org/search"
        params = {
            "q": q,
            "format": "json",
            "addressdetails": 1,
            "limit": 10,
            "countrycodes": "za",
        }

        try:
            try:
                res = requests.get(url, params=params, headers=headers, timeout=15)
                res.raise_for_status()
            except requests.exceptions.SSLError:
                res = requests.get(url, params=params, headers=headers, timeout=15, verify=False)
                res.raise_for_status()
            data = res.json()

            for item in data:
                label = item.get("display_name")
                if not label or label in seen:
                    continue

                seen.add(label)
                suggestions.append({
                    "label": label,
                    "value": label,
                    "provider": "osm_nominatim",
                    "place_id": item.get("place_id"),
                    "lat": float(item["lat"]),
                    "lon": float(item["lon"]),
                })

                if len(suggestions) >= 10:
                    return suggestions

        except Exception:
            continue

    return suggestions

def suggest_with_photon(query: str) -> list[dict]:
    """
    Photon is a second OSM-based search provider.
    It often finds places that Nominatim misses.
    """
    suggestions = []
    seen = set()

    for q in build_search_queries(query):
        url = "https://photon.komoot.io/api/"
        params = {
            "q": q,
            "limit": 10,
            "lang": "en",
            # Bias towards Gqeberha / Port Elizabeth coordinates
            "lat": -33.9608,
            "lon": 25.6022,
        }

        try:
            try:
                res = requests.get(url, params=params, timeout=15)
                res.raise_for_status()
            except requests.exceptions.SSLError:
                res = requests.get(url, params=params, timeout=15, verify=False)
                res.raise_for_status()
            data = res.json()

            for feature in data.get("features", []):
                props = feature.get("properties", {})
                coords = feature.get("geometry", {}).get("coordinates", [])
                if len(coords) < 2:
                    continue

                lon, lat = coords[0], coords[1]

                name = props.get("name")
                street = props.get("street")
                housenumber = props.get("housenumber")
                suburb = props.get("district") or props.get("suburb") or props.get("locality")
                city = props.get("city") or props.get("county")
                state = props.get("state")

                bits = []
                if housenumber and street:
                    bits.append(f"{housenumber} {street}")
                elif street:
                    bits.append(street)
                elif name:
                    bits.append(name)

                for value in [suburb, city, state, "South Africa"]:
                    if value and value not in bits:
                        bits.append(value)

                label = ", ".join(bits)
                if not label or label in seen:
                    continue

                seen.add(label)

                suggestions.append({
                    "label": label,
                    "value": label,
                    "provider": "photon",
                    "place_id": props.get("osm_id"),
                    "lat": float(lat),
                    "lon": float(lon),
                })

                if len(suggestions) >= 10:
                    return suggestions

        except Exception:
            continue

    return suggestions

def calculate_route_distance(
    pickup: str,
    dropoff: str,
    pickup_lat: Optional[float] = None,
    pickup_lon: Optional[float] = None,
    dropoff_lat: Optional[float] = None,
    dropoff_lon: Optional[float] = None,
) -> dict:
    if all(v is not None for v in [pickup_lat, pickup_lon, dropoff_lat, dropoff_lon]):
        return calculate_with_osrm_coords(pickup_lon, pickup_lat, dropoff_lon, dropoff_lat)

    if GOOGLE_MAPS_API_KEY:
        return calculate_with_google(pickup, dropoff)

    return calculate_with_osm_osrm(pickup, dropoff)

def calculate_route_between(
    origin: str,
    destination: str,
    origin_lat: Optional[float] = None,
    origin_lon: Optional[float] = None,
    destination_lat: Optional[float] = None,
    destination_lon: Optional[float] = None,
) -> dict:
    return calculate_route_distance(
        pickup=origin,
        dropoff=destination,
        pickup_lat=origin_lat,
        pickup_lon=origin_lon,
        dropoff_lat=destination_lat,
        dropoff_lon=destination_lon,
    )

def calculate_with_google(pickup: str, dropoff: str) -> dict:
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": normalize_local_address(pickup),
        "destinations": normalize_local_address(dropoff),
        "mode": "driving",
        "units": "metric",
        "key": GOOGLE_MAPS_API_KEY,
    }

    try:
        res = requests.get(url, params=params, timeout=15)
        res.raise_for_status()
        data = res.json()

        if data.get("status") != "OK":
            return {"success": False, "error": f"Google Maps error: {data.get('status')}"}

        element = data["rows"][0]["elements"][0]
        if element.get("status") != "OK":
            return {"success": False, "error": f"Could not calculate route: {element.get('status')}"}

        distance_m = element["distance"]["value"]
        duration_s = element["duration"]["value"]

        return {
            "success": True,
            "provider": "google",
            "distance_km": round(distance_m / 1000, 1),
            "duration_minutes": round(duration_s / 60),
        }

    except Exception as exc:
        return {"success": False, "error": str(exc)}

def geocode_osm(address: str) -> tuple[float, float] | None:
    # Try suggestions first because it uses both OSM and Photon.
    candidates = suggest_addresses(address)
    for candidate in candidates:
        if candidate.get("lat") is not None and candidate.get("lon") is not None:
            return float(candidate["lon"]), float(candidate["lat"])

    return None

def calculate_with_osrm_coords(p_lon: float, p_lat: float, d_lon: float, d_lat: float) -> dict:
    try:
        route_url = (
            "https://router.project-osrm.org/route/v1/driving/"
            f"{p_lon},{p_lat};{d_lon},{d_lat}"
        )

        params = {
            "overview": "false",
            "alternatives": "false",
            "steps": "false",
        }

        try:
            res = requests.get(route_url, params=params, timeout=20)
            res.raise_for_status()
        except requests.exceptions.SSLError:
            # Some hosting/network environments inject a self-signed certificate.
            # Retry without verification so quote generation is not blocked.
            res = requests.get(route_url, params=params, timeout=20, verify=False)
            res.raise_for_status()
        data = res.json()

        if data.get("code") != "Ok" or not data.get("routes"):
            return {"success": False, "error": "Could not calculate driving route."}

        route = data["routes"][0]

        return {
            "success": True,
            "provider": "osm_osrm",
            "distance_km": round(route["distance"] / 1000, 1),
            "duration_minutes": round(route["duration"] / 60),
        }

    except Exception as exc:
        return {"success": False, "error": str(exc)}

def calculate_with_osm_osrm(pickup: str, dropoff: str) -> dict:
    try:
        pickup_coords = geocode_osm(pickup)
        dropoff_coords = geocode_osm(dropoff)

        if not pickup_coords:
            return {"success": False, "error": f"Could not find pickup address: {normalize_local_address(pickup)}"}

        if not dropoff_coords:
            return {"success": False, "error": f"Could not find drop-off address: {normalize_local_address(dropoff)}"}

        p_lon, p_lat = pickup_coords
        d_lon, d_lat = dropoff_coords

        return calculate_with_osrm_coords(p_lon, p_lat, d_lon, d_lat)

    except Exception as exc:
        return {"success": False, "error": str(exc)}



LOCAL_AREA_SUGGESTIONS = [
    {"name": "Port Elizabeth, Gqeberha, Eastern Cape, South Africa", "lat": -33.9608, "lon": 25.6022},
    {"name": "Gqeberha, Eastern Cape, South Africa", "lat": -33.9608, "lon": 25.6022},
    {"name": "Broadwood, Gqeberha, Eastern Cape, South Africa", "lat": -33.9789, "lon": 25.5465},
    {"name": "Bridgemead, Gqeberha, Eastern Cape, South Africa", "lat": -33.9043, "lon": 25.5706},
    {"name": "Walmer, Gqeberha, Eastern Cape, South Africa", "lat": -33.9816, "lon": 25.5849},
    {"name": "Lorraine, Gqeberha, Eastern Cape, South Africa", "lat": -33.9626, "lon": 25.5125},
    {"name": "Summerstrand, Gqeberha, Eastern Cape, South Africa", "lat": -33.9912, "lon": 25.6636},
    {"name": "Newton Park, Gqeberha, Eastern Cape, South Africa", "lat": -33.9490, "lon": 25.5676},
    {"name": "Greenacres, Gqeberha, Eastern Cape, South Africa", "lat": -33.9448, "lon": 25.5716},
    {"name": "North End, Gqeberha, Eastern Cape, South Africa", "lat": -33.9324, "lon": 25.6071},
    {"name": "Central, Gqeberha, Eastern Cape, South Africa", "lat": -33.9614, "lon": 25.6225},
    {"name": "Humewood, Gqeberha, Eastern Cape, South Africa", "lat": -33.9796, "lon": 25.6453},
    {"name": "Mount Pleasant, Gqeberha, Eastern Cape, South Africa", "lat": -34.0126, "lon": 25.5316},
    {"name": "Sherwood, Gqeberha, Eastern Cape, South Africa", "lat": -33.9386, "lon": 25.5086},
    {"name": "Rowallan Park, Gqeberha, Eastern Cape, South Africa", "lat": -33.9111, "lon": 25.5235},
    {"name": "Bluewater Bay, Gqeberha, Eastern Cape, South Africa", "lat": -33.8614, "lon": 25.6356},
    {"name": "Motherwell, Gqeberha, Eastern Cape, South Africa", "lat": -33.7990, "lon": 25.5858},
    {"name": "KwaZakhele, Gqeberha, Eastern Cape, South Africa", "lat": -33.8849, "lon": 25.5809},
    {"name": "New Brighton, Gqeberha, Eastern Cape, South Africa", "lat": -33.8884, "lon": 25.6041},
    {"name": "Kariega, Eastern Cape, South Africa", "lat": -33.7653, "lon": 25.3971},
    {"name": "Despatch, Eastern Cape, South Africa", "lat": -33.8002, "lon": 25.4629},
]

def suggest_with_local_fallback(query: str) -> list[dict]:
    q = query.lower().strip()
    results = []

    for area in LOCAL_AREA_SUGGESTIONS:
        if q in area["name"].lower() or any(part in area["name"].lower() for part in q.split() if len(part) >= 4):
            results.append({
                "label": area["name"],
                "value": area["name"],
                "provider": "local_fallback",
                "place_id": None,
                "lat": area["lat"],
                "lon": area["lon"],
            })

    return results[:8]

def typed_address_fallback(query: str) -> list[dict]:
    """
    Last-resort option.
    Uses Port Elizabeth/Gqeberha centre coordinates as an approximation.
    This prevents the operator from being blocked, but it should be reviewed.
    """
    return [{
        "label": f"Use typed address: {normalize_local_address(query)}",
        "value": normalize_local_address(query),
        "provider": "typed_fallback_review_required",
        "place_id": None,
        "lat": -33.9608,
        "lon": 25.6022,
    }]

def provider_diagnostics(query: str) -> dict:
    return {
        "query": query,
        "normalized": normalize_local_address(query),
        "google_enabled": bool(GOOGLE_MAPS_API_KEY),
        "osm_results": len(suggest_with_osm(query)),
        "photon_results": len(suggest_with_photon(query)),
        "local_results": len(suggest_with_local_fallback(query)),
    }
