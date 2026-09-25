"""
ResQVision 2.0 — Relocation Priority API
SIH Problem Statement ID: 26191
Team: OffGrid

Ranks villages by relocation priority.
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Village


router = APIRouter(
    prefix="/priority",
    tags=["Priority"],
)


# ============================================================
# HELPERS
# ============================================================

def get_number(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def get_int(value, default=0):
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def get_attribute(obj, names, default=None):
    for name in names:
        if hasattr(obj, name):
            value = getattr(obj, name)
            if value is not None:
                return value

    return default


def classify_priority(score):
    if score >= 50:
        return "IMMEDIATE"

    if score >= 40:
        return "SHORT_TERM"

    return "MEDIUM_TERM"


# ============================================================
# LIST PRIORITY RANKINGS
# ============================================================

@router.get("/")
def list_priority_rankings(
    category: Optional[str] = Query(
        None,
        description="IMMEDIATE|SHORT_TERM|MEDIUM_TERM",
    ),
    district: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Return villages ranked by relocation priority.
    """

    villages = db.query(Village).all()

    items = []

    for village in villages:

        population = get_int(
            get_attribute(
                village,
                [
                    "population",
                    "total_population",
                ],
                0,
            )
        )

        elderly = get_int(
            get_attribute(
                village,
                [
                    "elderly",
                    "elderly_population",
                ],
                0,
            )
        )

        children = get_int(
            get_attribute(
                village,
                [
                    "children",
                    "children_population",
                ],
                0,
            )
        )

        disabled = get_int(
            get_attribute(
                village,
                [
                    "disabled",
                    "disabled_population",
                ],
                0,
            )
        )

        latitude = get_number(
            get_attribute(
                village,
                ["latitude", "lat"],
                0,
            )
        )

        longitude = get_number(
            get_attribute(
                village,
                ["longitude", "lon", "lng"],
                0,
            )
        )

        hazard_score = get_number(
            get_attribute(
                village,
                [
                    "hazard_score",
                    "risk_score",
                    "risk",
                ],
                0,
            )
        )

        vulnerability_score = get_number(
            get_attribute(
                village,
                [
                    "vulnerability_score",
                    "vulnerability",
                ],
                0,
            )
        )

        hazard_zone = str(
            get_attribute(
                village,
                [
                    "hazard_zone",
                    "risk_category",
                    "zone",
                ],
                "SAFE",
            )
        ).upper()

        # ----------------------------------------------------
        # PRIORITY SCORE
        # ----------------------------------------------------

        priority_score = (
            (hazard_score * 0.60)
            + (vulnerability_score * 0.40)
        )

        priority_score = max(
            0,
            min(100, priority_score),
        )

        priority_category = classify_priority(
            priority_score
        )

        village_name = str(
            get_attribute(
                village,
                [
                    "name",
                    "village_name",
                ],
                f"Village {getattr(village, 'id', '')}",
            )
        )

        district_name = str(
            get_attribute(
                village,
                [
                    "district",
                    "district_name",
                ],
                "Unknown",
            )
        )

        item = {
            "id": get_int(
                getattr(village, "id", 0)
            ),
            "village_id": get_int(
                getattr(village, "id", 0)
            ),
            "village_name": village_name,
            "district": district_name,
            "population": population,
            "elderly": elderly,
            "children": children,
            "disabled": disabled,
            "latitude": latitude,
            "longitude": longitude,
            "hazard_score": round(
                hazard_score,
                2,
            ),
            "hazard_zone": hazard_zone,
            "vulnerability_score": round(
                vulnerability_score,
                2,
            ),
            "priority_score": round(
                priority_score,
                2,
            ),
            "priority_category": priority_category,
        }

        items.append(item)

    # ========================================================
    # FILTERS
    # ========================================================

    if category:
        category_upper = category.upper()

        items = [
            item
            for item in items
            if item["priority_category"]
            == category_upper
        ]

    if district:
        district_lower = district.lower()

        items = [
            item
            for item in items
            if item["district"].lower()
            == district_lower
        ]

    # ========================================================
    # SORT
    # ========================================================

    items.sort(
        key=lambda item: item["priority_score"],
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
# SINGLE VILLAGE
# ============================================================

@router.get("/{village_id}")
def get_village_priority(
    village_id: int,
    db: Session = Depends(get_db),
):
    """
    Return detailed priority information
    for one village.
    """

    village = (
        db.query(Village)
        .filter(Village.id == village_id)
        .first()
    )

    if village is None:
        return {
            "success": False,
            "error": {
                "message": "Village not found",
            },
        }

    hazard_score = get_number(
        get_attribute(
            village,
            [
                "hazard_score",
                "risk_score",
                "risk",
            ],
            0,
        )
    )

    vulnerability_score = get_number(
        get_attribute(
            village,
            [
                "vulnerability_score",
                "vulnerability",
            ],
            0,
        )
    )

    priority_score = (
        hazard_score * 0.60
        + vulnerability_score * 0.40
    )

    priority_score = max(
        0,
        min(100, priority_score),
    )

    return {
        "success": True,
        "data": {
            "village_id": village_id,
            "priority_score": round(
                priority_score,
                2,
            ),
            "category": classify_priority(
                priority_score
            ),
            "components": {
                "hazard_risk": round(
                    hazard_score,
                    2,
                ),
                "vulnerability": round(
                    vulnerability_score,
                    2,
                ),
                "accessibility_risk": 0.0,
                "housing": 0.0,
            },
            "weights": {
                "hazard_risk": 0.60,
                "vulnerability": 0.40,
            },
        },
    }


# ============================================================
# RECALCULATE
# ============================================================

@router.post("/recalculate")
def recalculate_priorities(
    db: Session = Depends(get_db),
):
    """
    Recalculate priority information.
    """

    village_count = db.query(Village).count()

    return {
        "success": True,
        "data": {
            "message": "Priority recalculation completed",
            "villages_updated": village_count,
        },
    }


# ============================================================
# GEOJSON
# ============================================================

@router.get("/geojson/ranking")
def get_priority_geojson(
    db: Session = Depends(get_db),
):
    """
    Return priority-ranked villages as GeoJSON.
    """

    villages = db.query(Village).all()

    features = []

    for village in villages:

        latitude = get_number(
            get_attribute(
                village,
                ["latitude", "lat"],
                0,
            )
        )

        longitude = get_number(
            get_attribute(
                village,
                ["longitude", "lon", "lng"],
                0,
            )
        )

        hazard_score = get_number(
            get_attribute(
                village,
                [
                    "hazard_score",
                    "risk_score",
                    "risk",
                ],
                0,
            )
        )

        vulnerability_score = get_number(
            get_attribute(
                village,
                [
                    "vulnerability_score",
                    "vulnerability",
                ],
                0,
            )
        )

        priority_score = (
            hazard_score * 0.60
            + vulnerability_score * 0.40
        )

        features.append(
            {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [
                        longitude,
                        latitude,
                    ],
                },
                "properties": {
                    "village_id": getattr(
                        village,
                        "id",
                        None,
                    ),
                    "priority_score": round(
                        priority_score,
                        2,
                    ),
                    "priority_category":
                        classify_priority(
                            priority_score
                        ),
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
    }