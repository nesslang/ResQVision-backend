"""
ResQVision 2.0 — Safe Sites API
SIH Problem Statement ID: 26191
Team: OffGrid

Manages candidate relocation sites and their suitability scores.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.config import get_settings
from app.models.models import RelocationSite


router = APIRouter(
    prefix="/sites",
    tags=["Sites"],
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


def get_available_capacity(site):
    """
    Return unused physical capacity for a relocation site.
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


def build_site_item(site):
    """
    Convert a RelocationSite database object into
    a frontend-friendly response object.
    """

    return {
        "id": site.id,
        "site_id": site.id,

        "name": site.name,
        "district": site.district,

        "latitude": safe_float(
            site.latitude
        ),
        "longitude": safe_float(
            site.longitude
        ),

        "capacity": max(
            safe_int(site.capacity),
            0,
        ),

        "current_population": max(
            safe_int(site.current_population),
            0,
        ),

        "available_capacity": get_available_capacity(
            site
        ),

        "suitability_score": round(
            safe_float(
                site.suitability_score
            ),
            2,
        ),

        "safety_score": round(
            safe_float(
                site.safety_score
            ),
            2,
        ),

        "infrastructure_score": round(
            safe_float(
                site.infrastructure_score
            ),
            2,
        ),

        "land_score": round(
            safe_float(
                site.land_score
            ),
            2,
        ),

        "accessibility_score": round(
            safe_float(
                site.accessibility_score
            ),
            2,
        ),

        "water_score": round(
            safe_float(
                site.water_score
            ),
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
    }


# ============================================================
# LIST SAFE SITES
# ============================================================

@router.get("/")
def list_sites(
    suitable_only: bool = Query(
        False,
        description="Return only sites with suitability >= 60",
    ),
    district: Optional[str] = Query(
        None,
        description="Filter by district",
    ),
    min_score: float = Query(
        0.0,
        ge=0.0,
        le=100.0,
        description="Minimum suitability score",
    ),
    min_available_capacity: int = Query(
        0,
        ge=0,
        description="Minimum available capacity",
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
    List candidate relocation sites.

    Sites are ordered by suitability score,
    highest first.
    """

    sites = (
        db.query(RelocationSite)
        .all()
    )

    items = []

    district_filter = (
        district.lower()
        if district
        else None
    )

    for site in sites:

        item = build_site_item(site)

        # ----------------------------------------------------
        # DISTRICT FILTER
        # ----------------------------------------------------

        if district_filter:
            site_district = str(
                item["district"]
            ).lower()

            if district_filter not in site_district:
                continue

        # ----------------------------------------------------
        # MINIMUM SCORE FILTER
        # ----------------------------------------------------

        if (
            item["suitability_score"]
            < min_score
        ):
            continue

        # ----------------------------------------------------
        # SUITABLE ONLY
        # ----------------------------------------------------

        if suitable_only:
            if item["suitability_score"] < 60:
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
            item["suitability_score"],
            item["available_capacity"],
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
# GEOJSON
# ============================================================

@router.get("/geojson/all")
def get_sites_geojson(
    db: Session = Depends(get_db),
):
    """
    Return all relocation sites as GeoJSON.

    Coordinates follow GeoJSON convention:
    [longitude, latitude]
    """

    sites = (
        db.query(RelocationSite)
        .order_by(
            RelocationSite.suitability_score.desc()
        )
        .all()
    )

    features = []

    for site in sites:

        item = build_site_item(site)

        features.append(
            {
                "type": "Feature",

                "geometry": {
                    "type": "Point",
                    "coordinates": [
                        item["longitude"],
                        item["latitude"],
                    ],
                },

                "properties": {
                    "id": item["id"],
                    "site_id": item["site_id"],
                    "name": item["name"],
                    "district": item["district"],

                    "capacity": item["capacity"],
                    "current_population": (
                        item["current_population"]
                    ),
                    "available_capacity": (
                        item["available_capacity"]
                    ),

                    "suitability_score": (
                        item["suitability_score"]
                    ),

                    "safety_score": (
                        item["safety_score"]
                    ),

                    "infrastructure_score": (
                        item["infrastructure_score"]
                    ),

                    "land_score": (
                        item["land_score"]
                    ),

                    "accessibility_score": (
                        item["accessibility_score"]
                    ),

                    "water_score": (
                        item["water_score"]
                    ),

                    "healthcare_score": (
                        item["healthcare_score"]
                    ),
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
    }


# ============================================================
# SINGLE SITE
# ============================================================

@router.get("/{site_id}")
def get_site(
    site_id: int,
    db: Session = Depends(get_db),
):
    """
    Return the full suitability profile
    for one relocation site.
    """

    site = (
        db.query(RelocationSite)
        .filter(
            RelocationSite.id == site_id
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

    settings = get_settings()

    item = build_site_item(site)

    return {
        "success": True,

        "data": {
            **item,

            "scores": {
                "safety": item["safety_score"],
                "infrastructure": (
                    item["infrastructure_score"]
                ),
                "land": item["land_score"],
                "accessibility": (
                    item["accessibility_score"]
                ),
                "water": item["water_score"],
                "healthcare": (
                    item["healthcare_score"]
                ),
                "population_pressure": (
                    item["population_pressure_score"]
                ),
            },

            "weights": settings.suitability_weights,

            "geometry": {
                "type": "Point",
                "coordinates": [
                    item["longitude"],
                    item["latitude"],
                ],
            },
        },
    }


# ============================================================
# SCORE SITE
# ============================================================

@router.post("/score")
def score_site(
    payload: dict,
    db: Session = Depends(get_db),
):
    """
    Calculate a weighted suitability score.

    Expected payload:

    {
        "scores": {
            "safety": 90,
            "infrastructure": 80,
            "land": 75,
            "accessibility": 85,
            "water": 90,
            "healthcare": 70,
            "population_pressure": 60
        }
    }
    """

    settings = get_settings()

    weights = settings.suitability_weights

    scores = payload.get(
        "scores",
        {},
    )

    total = 0.0

    for key, weight in weights.items():

        score = safe_float(
            scores.get(key),
            0.0,
        )

        score = max(
            0.0,
            min(100.0, score),
        )

        total += (
            safe_float(weight)
            * score
        )

    return {
        "success": True,
        "data": {
            "suitability_score": round(
                total,
                4,
            ),
            "weights_used": weights,
        },
    }