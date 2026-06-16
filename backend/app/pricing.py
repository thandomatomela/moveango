from urllib.parse import quote_plus
from math import ceil

WHATSAPP_NUMBER = "27817108229"

SERVICE_TYPES = {
    "purchase_collection": "Purchase Collection",
    "store_pickup": "Store Pickup",
    "document_courier": "Document Courier Services",
    "furniture_appliance_delivery": "Furniture & Appliance Deliveries",
    "home_office_relocation": "Home & Office Relocations",
    "same_day_delivery": "Same-Day Deliveries",
}

LOAD_TYPES = {
    "documents": "Documents",
    "small_parcel": "Small Parcel",
    "retail_bags": "Retail Bags",
    "single_small_item": "Single Small Item",
    "single_large_item": "Single Large Item",
    "multiple_items": "Multiple Items",
    "appliance": "Appliance",
    "furniture": "Furniture",
    "home_office_load": "Home / Office Load",
}

PRICING_CONFIG = {
    "vehicles": {
        "bike": {
            "label": "Bike Courier",
            "base_fee": 40,
            "rate_per_km": 4.50,
            "minimum_charge": 80,
},
        "np200": {
            "label": "NP200",
            "base_fee": 220,
            "rate_per_km": 8,
            "minimum_charge": 300,
        },
        "np200_trailer_hired": {
            "label": "NP200 + Hired Trailer",
            "base_fee": 480,
            "rate_per_km": 10,
            "minimum_charge": 600,
            "trailer_hire_buffer": 250,
        },
        "outsourced_truck": {
            "label": "Outsourced Truck",
            "base_fee": 950,
            "rate_per_km": 14,
            "minimum_charge": 1200,
            "outsourcing_buffer": 300,
        },
    },
    "effort_fees": {
        "low": 0,
        "medium": 100,
        "high": 220,
        "heavy": 450,
    },
    "urgency_fees": {
        "standard": 0,
        "same_day": 120,
        "immediate": 250,
    },
    "helper_fee_per_person": 180,
    "fragile_handling_fee": 100,
    "platform_margin": 0.10,
    "global_minimum_job_charge": 0,
}


def round_currency(amount: float) -> float:
    return round(amount, 2)


def determine_vehicle(data: dict) -> str:
    service_type = data["service_type"]
    load_type = data["load_type"]
    load_size = data["load_size"]
    item_count = data["item_count"]
    has_stairs = data["has_stairs"]
    floor_count = data["floor_count"]
    access_difficulty = data["access_difficulty"]

    if load_size == "extra_large":
        return "outsourced_truck"

    if service_type == "home_office_relocation":
        if load_size in ["small", "medium"] and item_count <= 8:
            return "np200_trailer_hired"
        return "outsourced_truck"

    if load_type == "home_office_load":
        if load_size in ["large", "extra_large"]:
            return "outsourced_truck"
        return "np200_trailer_hired"

    if load_type in ["furniture", "appliance"]:
        if load_size == "large" or item_count >= 3:
            return "np200_trailer_hired"

        if has_stairs and floor_count >= 2:
            return "np200_trailer_hired"

        if access_difficulty == "difficult":
            return "np200_trailer_hired"

        return "np200"

    if service_type in ["document_courier", "same_day_delivery"]:
        if (
            load_type in ["documents", "small_parcel", "retail_bags"]
            and load_size in ["small", "medium"]
            and item_count <= 3
        ):
            return "bike"

        return "np200"

    if service_type == "store_pickup":
        if (
            load_type in ["documents", "small_parcel", "retail_bags"]
            and load_size == "small"
            and item_count <= 4
        ):
            return "bike"

        if load_size in ["small", "medium"]:
            return "np200"

        return "np200_trailer_hired"

    if service_type == "purchase_collection":
        if (
            load_type in ["documents", "small_parcel", "retail_bags"]
            and load_size == "small"
            and item_count <= 3
        ):
            return "bike"

        if load_size in ["small", "medium"] and item_count <= 2:
            return "np200"

        if load_size == "large" or item_count <= 8:
            return "np200_trailer_hired"

        return "outsourced_truck"

    if load_size in ["large", "extra_large"] or item_count >= 5:
        return "np200_trailer_hired"

    return "np200"


def customer_service_level(data: dict, vehicle_key: str, effort_level: str) -> str:
    service_type = data["service_type"]
    load_size = data["load_size"]

    if service_type == "document_courier":
        return "Document Courier Service"

    if service_type == "store_pickup":
        return "Store Pickup & Delivery"

    if service_type == "same_day_delivery":
        return "Same-Day Collection & Delivery"

    if service_type == "home_office_relocation":
        return "Home & Office Relocation Service"

    if service_type == "furniture_appliance_delivery":
        return "Furniture & Appliance Delivery"

    if service_type == "purchase_collection":
        if load_size in ["small", "medium"]:
            return "Purchase Collection & Delivery"

        return "Large Item Collection & Delivery"

    return SERVICE_TYPES.get(service_type, "Collection & Delivery Service")


def determine_effort(data: dict, vehicle_key: str) -> str:
    load_type = data["load_type"]
    load_size = data["load_size"]
    item_count = data["item_count"]
    has_stairs = data["has_stairs"]
    floor_count = data["floor_count"]
    access_difficulty = data["access_difficulty"]

    score = 0

    if load_size == "medium":
        score += 1
    elif load_size == "large":
        score += 2
    elif load_size == "extra_large":
        score += 3

    if item_count >= 3:
        score += 1

    if item_count >= 8:
        score += 2

    if load_type in ["appliance", "furniture", "home_office_load"]:
        score += 1

    if has_stairs:
        score += 1

    if floor_count >= 2:
        score += 1

    if floor_count >= 4:
        score += 2

    if access_difficulty == "moderate":
        score += 1
    elif access_difficulty == "difficult":
        score += 2

    if vehicle_key in ["np200_trailer_hired", "outsourced_truck"]:
        score += 1

    if score <= 1:
        return "low"

    if score <= 3:
        return "medium"

    if score <= 5:
        return "high"

    return "heavy"


def determine_helpers(data: dict, vehicle_key: str, effort_level: str) -> int:
    load_type = data["load_type"]
    load_size = data["load_size"]

    if vehicle_key == "bike":
        return 0

    if effort_level == "low":
        if load_type in ["furniture", "appliance"]:
            return 1
        return 0

    if effort_level == "medium":
        return 1

    if effort_level == "high":
        return 2

    if effort_level == "heavy":
        if load_size == "extra_large":
            return 3
        return 2

    return 1


def calculate_dead_mileage_recovery(dead_mileage_km: float, effort_level: str) -> dict:
    if dead_mileage_km <= 0:
        return {
            "dead_mileage_recovery_km": 0,
            "dead_mileage_recovery_rule": "No empty driving recovery",
        }

    if effort_level == "low":
        recovery = min(dead_mileage_km * 0.25, 3)
        rule = "Low effort: recover 25% of empty driving, capped at 3 km"

    elif effort_level == "medium":
        recovery = min(dead_mileage_km * 0.35, 6)
        rule = "Medium effort: recover 35% of empty driving, capped at 6 km"

    elif effort_level == "high":
        recovery = min(dead_mileage_km * 0.50, 10)
        rule = "High effort: recover 50% of empty driving, capped at 10 km"

    else:
        recovery = min(dead_mileage_km * 0.60, 15)
        rule = "Heavy effort: recover 60% of empty driving, capped at 15 km"

    return {
        "dead_mileage_recovery_km": round(recovery, 1),
        "dead_mileage_recovery_rule": rule,
    }


def estimate_internal_cost(
    vehicle_key: str,
    operational_distance_km: float,
    helpers_required: int,
    trailer_hire_buffer: float,
    outsourcing_buffer: float,
) -> dict:
    vehicle_cost_per_km = {
        # Big Boy Velocity 150 / 150cc bike estimate.
        # Fuel cost is much lower than NP200.
        # R1.20/km includes fuel, oil, tyres, service and wear allowance.
        "bike": 1.20,
        "np200": 4.50,
        "np200_trailer_hired": 5.50,
        "outsourced_truck": 10.00,
    }

    driver_allowance = {
        "bike": 50,
        "np200": 180,
        "np200_trailer_hired": 220,
        "outsourced_truck": 0,
    }

    helper_internal_cost = 160

    distance_cost = operational_distance_km * vehicle_cost_per_km.get(vehicle_key, 5)
    driver_cost = driver_allowance.get(vehicle_key, 180)
    helper_cost = helpers_required * helper_internal_cost

    total_cost = (
        distance_cost
        + driver_cost
        + helper_cost
        + trailer_hire_buffer
        + outsourcing_buffer
    )

    return {
        "distance_cost": round(distance_cost, 2),
        "driver_cost": driver_cost,
        "helper_cost": helper_cost,
        "trailer_hire_cost": trailer_hire_buffer,
        "outsourcing_cost": outsourcing_buffer,
        "estimated_total_cost": round(total_cost, 2),
    }


def calculate_quote(data: dict, route: dict) -> dict:
    customer_distance_km = route["customer_distance_km"]
    operational_distance_km = route["operational_distance_km"]
    dead_mileage_km = route["dead_mileage_km"]

    vehicle_key = determine_vehicle(data)
    vehicle = PRICING_CONFIG["vehicles"][vehicle_key]

    effort_level = determine_effort(data, vehicle_key)
    helpers_required = determine_helpers(data, vehicle_key, effort_level)

    recovery = calculate_dead_mileage_recovery(
        dead_mileage_km=dead_mileage_km,
        effort_level=effort_level,
    )

    dead_mileage_recovery_km = recovery["dead_mileage_recovery_km"]

    billing_distance_km = round(
        customer_distance_km + dead_mileage_recovery_km,
        1,
    )

    base_fee = vehicle["base_fee"]
    distance_charge = billing_distance_km * vehicle["rate_per_km"]
    effort_fee = PRICING_CONFIG["effort_fees"][effort_level]
    urgency_fee = PRICING_CONFIG["urgency_fees"][data["urgency"]]
    labour_fee = helpers_required * PRICING_CONFIG["helper_fee_per_person"]

    fragile_value = data.get("is_fragile", "no")
    fragile_fee = (
        PRICING_CONFIG["fragile_handling_fee"]
        if fragile_value in [True, "yes", "mixed"]
        else 0
    )

    trailer_hire_buffer = vehicle.get("trailer_hire_buffer", 0)
    outsourcing_buffer = vehicle.get("outsourcing_buffer", 0)

    subtotal = (
        base_fee
        + distance_charge
        + effort_fee
        + urgency_fee
        + labour_fee
        + fragile_fee
        + trailer_hire_buffer
        + outsourcing_buffer
    )

    platform_margin = subtotal * PRICING_CONFIG["platform_margin"]

    final_total = round_currency(
    max(
        subtotal + platform_margin,
        vehicle["minimum_charge"],
        PRICING_CONFIG["global_minimum_job_charge"],
    )
)

    service_label = SERVICE_TYPES[data["service_type"]]
    load_label = LOAD_TYPES[data["load_type"]]

    internal_costs = estimate_internal_cost(
        vehicle_key=vehicle_key,
        operational_distance_km=operational_distance_km,
        helpers_required=helpers_required,
        trailer_hire_buffer=trailer_hire_buffer,
        outsourcing_buffer=outsourcing_buffer,
    )

    estimated_profit = final_total - internal_costs["estimated_total_cost"]

    estimated_margin_percent = (
        estimated_profit / final_total * 100
        if final_total > 0
        else 0
    )

    message = (
        "Hi Moveango, I would like to book this quote.\n\n"
        f"Pickup: {data['pickup']}\n"
        f"Dropoff: {data['dropoff']}\n"
        f"Service: {service_label}\n"
        f"Load: {load_label}\n"
        f"Estimated Quote: R{final_total}\n"
    )

    return {
        "pickup": data["pickup"],
        "dropoff": data["dropoff"],
        "service_type": service_label,
        "customer_service_label": customer_service_level(
            data,
            vehicle_key,
            effort_level,
        ),
        "load_type": load_label,
        "distance_km": customer_distance_km,
        "operational_distance_km": operational_distance_km,
        "dead_mileage_km": dead_mileage_km,
        "chargeable_distance_km": billing_distance_km,
        "billing_distance_km": billing_distance_km,
        "estimated_duration_minutes": route.get("duration_minutes"),
        "recommended_vehicle": vehicle["label"],
        "effort_level": effort_level,
        "helpers_required": helpers_required,
        "estimated_quote": final_total,
        "currency": "ZAR",
        "breakdown": {
            "base_fee": base_fee,
            "customer_distance_km": customer_distance_km,
            "operational_distance_km": operational_distance_km,
            "dead_mileage_km": dead_mileage_km,
            "dead_mileage_recovery_km": dead_mileage_recovery_km,
            "dead_mileage_recovery_rule": recovery["dead_mileage_recovery_rule"],
            "billing_distance_km": billing_distance_km,
            "distance_charge": round(distance_charge, 2),
            "effort_level": effort_level,
            "effort_fee": effort_fee,
            "urgency_fee": urgency_fee,
            "labour_fee": labour_fee,
            "fragile_handling_fee": fragile_fee,
            "trailer_hire_buffer": trailer_hire_buffer,
            "outsourcing_buffer": outsourcing_buffer,
            "platform_margin": round(platform_margin, 2),
            "minimum_charge": vehicle["minimum_charge"],
            "global_minimum_job_charge": PRICING_CONFIG["global_minimum_job_charge"],
            "distance_provider": route.get("provider"),
            "internal_costs": internal_costs,
            "estimated_profit": round(estimated_profit, 2),
            "estimated_margin_percent": round(estimated_margin_percent, 1),
        },
        "disclaimer": (
            "This is a provisional estimate generated from customer specifications. "
            "Final pricing may change after review if item size, access, timing, "
            "waiting time or availability differs from the details provided."
        ),
        "whatsapp_url": f"https://wa.me/{WHATSAPP_NUMBER}?text={quote_plus(message)}",
    }