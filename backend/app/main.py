from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from typing import Literal, Optional, Dict, Any
from datetime import datetime, timedelta
from pathlib import Path
from urllib.parse import quote_plus

from .pricing import calculate_quote, PRICING_CONFIG, SERVICE_TYPES, LOAD_TYPES
from .distance import calculate_route_between, suggest_addresses, provider_diagnostics
from .pdf_generator import generate_quote_pdf
from .storage import init_db, save_quote, list_quotes, get_quote, update_quote_status

DEPOT_ADDRESS = "13 Hankey Avenue, Bridgemead, Gqeberha, Eastern Cape, South Africa"
DEPOT_LAT = -33.9043
DEPOT_LON = 25.5706

app = FastAPI(title="Moveango Internal Quote Tool API", version="1.7.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

GENERATED_DIR = Path("/app/generated_quotes")
GENERATED_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/quotes", StaticFiles(directory=str(GENERATED_DIR)), name="quotes")

@app.on_event("startup")
def startup_event():
    init_db()


ServiceType = Literal[
    "purchase_collection",
    "store_pickup",
    "document_courier",
    "furniture_appliance_delivery",
    "home_office_relocation",
    "same_day_delivery",
]

LoadType = Literal[
    "documents",
    "small_parcel",
    "retail_bags",
    "single_small_item",
    "single_large_item",
    "multiple_items",
    "appliance",
    "furniture",
    "home_office_load",
]

LoadSize = Literal["small", "medium", "large", "extra_large"]
Urgency = Literal["standard", "same_day", "immediate"]
AccessDifficulty = Literal["easy", "moderate", "difficult"]

class QuoteRequest(BaseModel):
    customer_name: str = "Customer"
    customer_phone: str = ""

    pickup: str = Field(..., min_length=3)
    dropoff: str = Field(..., min_length=3)

    pickup_lat: Optional[float] = None
    pickup_lon: Optional[float] = None
    dropoff_lat: Optional[float] = None
    dropoff_lon: Optional[float] = None

    service_type: ServiceType
    load_type: LoadType
    load_size: LoadSize = "small"

    item_count: int = Field(1, ge=1, le=100)
    has_stairs: bool = False
    floor_count: int = Field(0, ge=0, le=20)
    access_difficulty: AccessDifficulty = "easy"
    urgency: Urgency = "standard"

    is_fragile: str = "no"
    notes: Optional[str] = None

class QuoteResponse(BaseModel):
    quote_number: str
    quote_date: str
    valid_until: str
    customer_name: str
    customer_phone: str
    pickup: str
    dropoff: str
    service_type: str
    customer_service_label: str
    load_type: str
    distance_km: float
    operational_distance_km: float
    dead_mileage_km: float
    chargeable_distance_km: float
    billing_distance_km: float
    status: str = "Draft"
    estimated_duration_minutes: Optional[int]
    recommended_vehicle: str
    effort_level: str
    helpers_required: int
    internal_breakdown: Dict[str, Any]
    expected_internal_notes: str
    estimated_quote: float
    currency: str = "ZAR"
    disclaimer: str
    pdf_url: str
    whatsapp_url: str

@app.get("/health")
def health():
    return {"status": "ok", "service": "moveango-internal-quote-tool", "version": "1.7.0"}

@app.get("/config")
def config():
    return {
        "service_types": SERVICE_TYPES,
        "load_types": LOAD_TYPES,
        "pricing": PRICING_CONFIG,
    }

@app.get("/address-suggest")
def address_suggest(q: str = Query(..., min_length=3)):
    return {"query": q, "suggestions": suggest_addresses(q)}


@app.get("/address-debug")
def address_debug(q: str = Query(..., min_length=3)):
    return provider_diagnostics(q)



def normalize_sa_phone(phone: str) -> str:
    digits = "".join(ch for ch in (phone or "") if ch.isdigit())

    if not digits:
        return ""

    if digits.startswith("00"):
        digits = digits[2:]

    if digits.startswith("27"):
        return digits

    if digits.startswith("0") and len(digits) == 10:
        return "27" + digits[1:]

    if len(digits) == 9:
        return "27" + digits

    return digits


def next_quote_number() -> str:
    stamp = datetime.now().strftime("%Y%m%d%H%M%S")
    return f"MVQ-{stamp}"

@app.post("/quote", response_model=QuoteResponse)
def quote(request: QuoteRequest):
    depot_to_pickup = calculate_route_between(
        origin=DEPOT_ADDRESS,
        destination=request.pickup,
        origin_lat=DEPOT_LAT,
        origin_lon=DEPOT_LON,
        destination_lat=request.pickup_lat,
        destination_lon=request.pickup_lon,
    )

    pickup_to_dropoff = calculate_route_between(
        origin=request.pickup,
        destination=request.dropoff,
        origin_lat=request.pickup_lat,
        origin_lon=request.pickup_lon,
        destination_lat=request.dropoff_lat,
        destination_lon=request.dropoff_lon,
    )

    dropoff_to_depot = calculate_route_between(
        origin=request.dropoff,
        destination=DEPOT_ADDRESS,
        origin_lat=request.dropoff_lat,
        origin_lon=request.dropoff_lon,
        destination_lat=DEPOT_LAT,
        destination_lon=DEPOT_LON,
    )

    for label, route_result in [
        ("Depot to pickup", depot_to_pickup),
        ("Pickup to delivery", pickup_to_dropoff),
        ("Delivery to depot", dropoff_to_depot),
    ]:
        if not route_result.get("success"):
            raise HTTPException(
                status_code=400,
                detail=f"{label} route failed: {route_result.get('error', 'Could not calculate route distance.')}"
            )

    customer_distance_km = pickup_to_dropoff["distance_km"]
    operational_distance_km = round(
        depot_to_pickup["distance_km"]
        + pickup_to_dropoff["distance_km"]
        + dropoff_to_depot["distance_km"],
        1,
    )
    dead_mileage_km = round(operational_distance_km - customer_distance_km, 1)

    # Safety guard: for any non-depot job, empty driving should not be zero.
    # If it is zero, it usually means the fallback provider used the same approximate coordinates.
    if dead_mileage_km <= 0 and customer_distance_km > 0:
        dead_mileage_km = 1.0
        operational_distance_km = round(customer_distance_km + dead_mileage_km, 1)

    route = {
        "success": True,
        "provider": pickup_to_dropoff.get("provider"),
        "customer_distance_km": customer_distance_km,
        "operational_distance_km": operational_distance_km,
        "dead_mileage_km": dead_mileage_km,
        "duration_minutes": (
            depot_to_pickup.get("duration_minutes", 0)
            + pickup_to_dropoff.get("duration_minutes", 0)
            + dropoff_to_depot.get("duration_minutes", 0)
        ),
        "legs": {
            "depot_to_pickup": depot_to_pickup,
            "pickup_to_delivery": pickup_to_dropoff,
            "delivery_to_depot": dropoff_to_depot,
        },
    }

    calculated = calculate_quote(request.model_dump(), route)

    today = datetime.now()
    quote_data = {
        **calculated,
        "quote_number": next_quote_number(),
        "quote_date": today.strftime("%d %b %Y"),
        "valid_until": (today + timedelta(days=7)).strftime("%d %b %Y"),
        "customer_name": request.customer_name or "Customer",
        "customer_phone": request.customer_phone or "Not provided",
        "notes": request.notes or "",
        "status": "Draft",
    }

    pdf_url = generate_quote_pdf(quote_data)
    quote_data["pdf_url"] = pdf_url
    save_quote(quote_data)

    message = (
    f"Hi {request.customer_name or 'there'}, please find your Moveango quote attached.\n\n"
    f"Quote Number: {quote_data['quote_number']}\n"
    f"Total Service Fee: R{quote_data['estimated_quote']}\n\n"
    f"To accept this quotation simply reply:\n\n"
    f"ACCEPT \n\n"
    "Please review the PDF and let us know if you would like any changes.\n\n"
    "Moveango\n"
    "Collect. Deliver. Move."
)

    normalized_phone = normalize_sa_phone(request.customer_phone)
    whatsapp_url = f"https://wa.me/{normalized_phone}?text={quote_plus(message)}" if normalized_phone else ""

    return {
        **quote_data,
        "internal_breakdown": quote_data["breakdown"],
        "expected_internal_notes": (
            "Vehicle, helper count, route distance and pricing breakdown are internal Moveango operational details. "
            "They are intentionally hidden from the customer PDF."
        ),
        "pdf_url": pdf_url,
        "whatsapp_url": whatsapp_url,
    }


@app.get("/quotes-list")
def quotes_list(search: str | None = None, limit: int = 100):
    return {"quotes": list_quotes(limit=limit, search=search)}

@app.get("/quotes-list/{quote_number}")
def quote_detail(quote_number: str):
    quote = get_quote(quote_number)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")
    return quote

@app.patch("/quotes-list/{quote_number}/status")
def quote_status_update(quote_number: str, status: str):
    allowed = {"Draft", "Sent", "Accepted", "Declined", "Completed", "Cancelled"}
    if status not in allowed:
        raise HTTPException(status_code=400, detail=f"Invalid status. Allowed: {', '.join(sorted(allowed))}")

    quote = update_quote_status(quote_number, status)
    if not quote:
        raise HTTPException(status_code=404, detail="Quote not found")

    return quote
