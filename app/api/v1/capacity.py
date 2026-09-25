"""
ResQVision 2.0 — Carrying Capacity API
SIH Problem Statement ID: 26191
Team: OffGrid

Provides carrying-capacity assessments for relocation sites.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import get_settings
from app.models.models import RelocationSite


router = APIRouter(
    prefix="/capacity",
    tags=["Capacity"],
)


# ============================================================
# HELPERS
# ============================================================

def safe_int(value, default=0):
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def calculate_available_capacity(site):
    """
    Calculate currently available physical capacity.
    """
    capacity = max(
        safe_int(site.capacity),
        0,
    )

    current_population = max(
        safe_int(site.current_population),
        0,
    )

    return max(
        capacity - current_population,
        0,
    )


def calculate_effective_capacity(site, safety_margin):
    """
    Apply the configured safety margin to physical capacity.
    """
    raw_capacity = max(
        safe_int(site.capacity),
        0,
    )

    effective_capacity = int(
        raw_capacity * safety_margin
    )

    return raw_capacity, effective_capacity


def calculate_utilisation(site, effective_capacity):
    """
    Calculate utilisation percentage using effective capacity.
    """
    current_population = max(
        safe_int(site.current_population),
        0,
    )

    if effective_capacity <= 0:
        return 100.0 if current_population > 0 else 0.0

    utilisation = (
        current_population
        / effective_capacity
    ) * 100

    return max(
        0.0,
        min(100.0, utilisation),
    )


def classify_pressure(utilisation_pct):
    """
    Classify site pressure based on utilisation.

    Uses the application's configured thresholds when
    available.
    """

    settings = get_settings()

    try:
        return settings.classify_pressure(
            utilisation_pct
        )
    except Exception:
        pass

    if utilisation_pct <= 50:
        return "LOW"

    if utilisation_pct <= 70:
        return "MODERATE"

    if utilisation_pct <= 90:
        return "HIGH"

    if utilisation_pct <= 100:
        return "CRITICAL"

    return "OVERCAPACITY"


def build_capacity_dimensions(site, effective_capacity):
    """
    Build infrastructure dimensions.

    The current RelocationSite model stores an overall
    capacity rather than separate physical capacities
    for water, sanitation, shelter, healthcare and land.

    Therefore the available site capacity is exposed as
    the baseline for each dimension, while the detailed
    suitability scores remain available through /sites.
    """

    capacity = max(
        safe_int(effective_capacity),
        0,
    )

    return {
        "water_supply": {
            "capacity": capacity,
            "unit": "persons",
        },
        "sanitation": {
            "capacity": capacity,
            "unit": "persons",
        },
        "shelter": {
            "capacity": capacity,
            "unit": "persons",
        },
        "healthcare": {
            "capacity": capacity,
            "unit": "persons",
        },
        "land_area": {
            "capacity": capacity,
            "unit": "persons",
        },
    }


def build_capacity_item(site):
    """
    Convert a RelocationSite database object into
    a capacity assessment response.
    """

    settings = get_settings()

    safety_margin = safe_float(
        settings.capacity_safety_margin,
        0.85,
    )

    raw_capacity, effective_capacity = (
        calculate_effective_capacity(
            site,
            safety_margin,
        )
    )

    current_population = max(
        safe_int(site.current_population),
        0,
    )

    available_capacity = max(
        effective_capacity - current_population,
        0,
    )

    utilisation_pct = calculate_utilisation(
        site,
        effective_capacity,
    )

    pressure_level = classify_pressure(
        utilisation_pct
    )

    return {
        "id": site.id,
        "site_id": site.id,
        "name": site.name,
        "district": site.district,
        "latitude": site.latitude,
        "longitude": site.longitude,

        "raw_capacity": raw_capacity,
        "effective_capacity": effective_capacity,

        "capacity": raw_capacity,
        "current_population": current_population,
        "available_capacity": available_capacity,

        "safety_margin": safety_margin,
        "utilisation_pct": round(
            utilisation_pct,
            2,
        ),
        "pressure_level": pressure_level,

        "limiting_factor": "site_capacity",

        "suitability_score": round(
            safe_float(site.suitability_score),
            2,
        ),

        "safety_score": round(
            safe_float(site.safety_score),
            2,
        ),

        "infrastructure_score": round(
            safe_float(
                site.infrastructure_score
            ),
            2,
        ),

        "land_score": round(
            safe_float(site.land_score),
            2,
        ),

        "accessibility_score": round(
            safe_float(
                site.accessibility_score
            ),
            2,
        ),

        "water_score": round(
            safe_float(site.water_score),
            2,
        ),

        "healthcare_score": round(
            safe_float(
                site.healthcare_score
            ),
            2,
        ),

        "population_pressure_score": round(
            safe_float(
                site.population_pressure_score
            ),
            2,
        ),

        "dimensions": build_capacity_dimensions(
            site,
            effective_capacity,
        ),
    }


# ============================================================
# PRESSURE OVERVIEW
# ============================================================

@router.get(
    "/pressure/overview"
)
def get_pressure_overview(
    db: Session = Depends(get_db),
):
    """
    Return the number of relocation sites
    at each carrying-capacity pressure level.
    """

    sites = (
        db.query(RelocationSite)
        .all()
    )

    overview = {
        "LOW": 0,
        "MODERATE": 0,
        "HIGH": 0,
        "CRITICAL": 0,
        "OVERCAPACITY": 0,
    }

    for site in sites:
        item = build_capacity_item(site)

        pressure = item[
            "pressure_level"
        ]

        if pressure not in overview:
            overview[pressure] = 0

        overview[pressure] += 1

    return {
        "success": True,
        "data": overview,
    }


# ============================================================
# LIST CAPACITY ASSESSMENTS
# ============================================================

@router.get("/")
def list_capacities(
    pressure_level: Optional[str] = Query(
        None,
        description=(
            "LOW|MODERATE|HIGH|CRITICAL|OVERCAPACITY"
        ),
    ),
    district: Optional[str] = Query(
        None
    ),
    min_available_capacity: int = Query(
        0,
        ge=0,
    ),
    limit: int = Query(
        50,
        ge=1,
        le=500,
    ),
    offset: int = Query(
        0,
        ge=0,
    ),
    db: Session = Depends(get_db),
):
    """
    List carrying-capacity assessments
    for all relocation sites.
    """

    sites = (
        db.query(RelocationSite)
        .all()
    )

    items = []

    requested_pressure = (
        pressure_level.upper()
        if pressure_level
        else None
    )

    requested_district = (
        district.lower()
        if district
        else None
    )

    for site in sites:

        item = build_capacity_item(site)

        # ----------------------------------------------------
        # PRESSURE FILTER
        # ----------------------------------------------------

        if requested_pressure:
            if (
                item["pressure_level"]
                != requested_pressure
            ):
                continue

        # ----------------------------------------------------
        # DISTRICT FILTER
        # ----------------------------------------------------

        if requested_district:
            site_district = (
                str(item["district"])
                .lower()
            )

            if (
                requested_district
                not in site_district
            ):
                continue

        # ----------------------------------------------------
        # AVAILABLE CAPACITY FILTER
        # ----------------------------------------------------

        if (
            item["available_capacity"]
            < min_available_capacity
        ):
            continue

        items.append(item)

    # ========================================================
    # SORT
    # ========================================================

    items.sort(
        key=lambda item: (
            item["available_capacity"],
            item["suitability_score"],
        ),
        reverse=True,
    )

    total = len(items)

    # ========================================================
    # PAGINATION
    # ========================================================

    paginated_items = items[
        offset:offset + limit
    ]

    return {
        "success": True,
        "data": {
            "items": paginated_items,
            "total": total,
            "limit": limit,
            "offset": offset,
        },
    }


# ============================================================
# SINGLE SITE CAPACITY
# ============================================================

@router.get(
    "/{site_id}"
)
def get_site_capacity(
    site_id: int,
    db: Session = Depends(get_db),
):
    """
    Return the full carrying-capacity breakdown
    for one relocation site.
    """

    site = (
        db.query(RelocationSite)
        .filter(
            RelocationSite.id
            == site_id
        )
        .first()
    )

    if site is None:
        return {
            "success": False,
            "error": {
                "code": "SITE_NOT_FOUND",
                "message": (
                    f"Relocation site "
                    f"{site_id} was not found."
                ),
            },
        }

    item = build_capacity_item(site)

    return {
        "success": True,
        "data": item,
    }


# ============================================================
# CALCULATE CAPACITY
# ============================================================

@router.post(
    "/calculate"
)
def calculate_capacity(
    payload: dict,
    db: Session = Depends(get_db),
):
    """
    Calculate carrying capacity from supplied
    infrastructure dimensions.

    Uses the limiting-factor principle:
    effective capacity = minimum dimension capacity
    multiplied by the configured safety margin.
    """

    settings = get_settings()

    dimensions = payload.get(
        "dimensions",
        {},
    )

    if not dimensions:
        return {
            "success": False,
            "error": {
                "code": "NO_DATA",
                "message": (
                    "No dimension data provided."
                ),
            },
        }

    valid_dimensions = {}

    for key, value in dimensions.items():

        if not isinstance(value, dict):
            continue

        capacity = safe_int(
            value.get("capacity"),
            0,
        )

        if capacity >= 0:
            valid_dimensions[key] = {
                "capacity": capacity,
                "unit": value.get(
                    "unit",
                    "persons",
                ),
            }

    if not valid_dimensions:
        return {
            "success": False,
            "error": {
                "code": "INVALID_DATA",
                "message": (
                    "No valid capacity "
                    "dimensions were provided."
                ),
            },
        }

    limiting_dimension = min(
        valid_dimensions,
        key=lambda key:
            valid_dimensions[key]["capacity"],
    )

    raw_capacity = valid_dimensions[
        limiting_dimension
    ]["capacity"]

    safety_margin = safe_float(
        settings.capacity_safety_margin,
        0.85,
    )

    effective_capacity = int(
        raw_capacity
        * safety_margin
    )

    return {
        "success": True,
        "data": {
            "raw_capacity": raw_capacity,
            "effective_capacity": (
                effective_capacity
            ),
            "safety_margin": safety_margin,
            "limiting_factor": (
                limiting_dimension
            ),
            "dimensions": valid_dimensions,
        },
    }