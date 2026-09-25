"""
ResQVision 2.0 — Hazard API
SIH Problem Statement ID: 26191
Team: OffGrid

Provides habitation-level hazard assessments from PostgreSQL.

Endpoints:

GET /api/v1/hazards/
GET /api/v1/hazards/{village_id}
GET /api/v1/hazards/geojson/zones
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Village, HazardAssessment


router = APIRouter(
    prefix="/hazards",
    tags=["Hazards"],
)


# ============================================================
# HELPERS
# ============================================================

def safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value, default=0):
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def normalize_zone(value):
    """
    Normalize database zone values into:

    SAFE
    WARNING
    RED
    """

    if value is None:
        return "SAFE"

    zone = str(value).strip().upper()

    if zone in {"RED", "HIGH", "CRITICAL"}:
        return "RED"

    if zone in {
        "WARNING",
        "WARN",
        "MEDIUM",
        "MODERATE",
    }:
        return "WARNING"

    return "SAFE"


def get_latest_hazard_rows(db: Session):
    """
    Return one latest hazard assessment per village.

    This protects the frontend from duplicate villages if the
    database contains multiple historical hazard assessments
    for the same habitation.

    Higher assessment IDs are treated as newer records.
    """

    rows = (
        db.query(HazardAssessment, Village)
        .join(
            Village,
            HazardAssessment.village_id == Village.id,
        )
        .order_by(
            HazardAssessment.village_id.asc(),
            HazardAssessment.id.desc(),
        )
        .all()
    )

    latest = {}
    for hazard, village in rows:
        if village.id not in latest:
            latest[village.id] = (hazard, village)

    return list(latest.values())


def serialize_hazard(hazard, village):
    """
    Convert a database hazard assessment into the API format
    consumed by the React frontend.
    """

    zone = normalize_zone(hazard.zone)

    return {
        "id": safe_int(hazard.id),
        "village_id": safe_int(village.id),

        "village_name": village.name,
        "district": village.district,

        "population": safe_int(village.population),
        "elderly": safe_int(village.elderly),
        "children": safe_int(village.children),
        "disabled": safe_int(village.disabled),

        "latitude": safe_float(village.latitude),
        "longitude": safe_float(village.longitude),

        # HazardAssessment is the authoritative hazard source.
        "hazard_score": safe_float(hazard.hazard_score),
        "zone": zone,

        "flood_risk": safe_float(hazard.flood_risk),
        "landslide_risk": safe_float(hazard.landslide_risk),
        "earthquake_risk": safe_float(hazard.earthquake_risk),
        "drought_risk": safe_float(hazard.drought_risk),
        "cyclone_risk": safe_float(hazard.cyclone_risk),

        "rainfall": safe_float(hazard.rainfall),
        "elevation": safe_float(hazard.elevation),
        "slope": safe_float(hazard.slope),
        "distance_from_river": safe_float(
            hazard.distance_from_river
        ),

        "created_at": (
            hazard.created_at.isoformat()
            if hazard.created_at
            else None
        ),
    }


# ============================================================
# LIST HAZARD ASSESSMENTS
# ============================================================

@router.get("/")
def list_hazard_assessments(
    zone: Optional[str] = Query(
        None,
        description="Filter by hazard zone: SAFE|WARNING|RED",
    ),
    district: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Return latest hazard assessment for each village.
    """

    rows = get_latest_hazard_rows(db)

    if zone:
        requested_zone = normalize_zone(zone)

        rows = [
            (hazard, village)
            for hazard, village in rows
            if normalize_zone(hazard.zone) == requested_zone
        ]

    if district:
        requested_district = district.strip().lower()

        rows = [
            (hazard, village)
            for hazard, village in rows
            if str(village.district).strip().lower()
            == requested_district
        ]

    total = len(rows)

    rows = rows[offset : offset + limit]

    items = [
        serialize_hazard(hazard, village)
        for hazard, village in rows
    ]

    return {
        "success": True,
        "data": {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        },
    }


# ============================================================
# GEOJSON
# ============================================================

# IMPORTANT:
# This route is intentionally BEFORE /{village_id}.
# Static paths must be declared before dynamic paths.
@router.get("/geojson/zones")
def get_hazard_zones_geojson(
    db: Session = Depends(get_db),
):
    """
    Return latest hazard assessment for each village
    as GeoJSON points.
    """

    rows = get_latest_hazard_rows(db)

    features = []

    for hazard, village in rows:

        latitude = safe_float(village.latitude)
        longitude = safe_float(village.longitude)

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
                    "id": safe_int(village.id),
                    "village_id": safe_int(village.id),

                    "name": village.name,
                    "district": village.district,

                    "population": safe_int(
                        village.population
                    ),

                    "hazard_score": safe_float(
                        hazard.hazard_score
                    ),

                    "zone": normalize_zone(
                        hazard.zone
                    ),

                    "flood_risk": safe_float(
                        hazard.flood_risk
                    ),

                    "landslide_risk": safe_float(
                        hazard.landslide_risk
                    ),

                    "earthquake_risk": safe_float(
                        hazard.earthquake_risk
                    ),

                    "drought_risk": safe_float(
                        hazard.drought_risk
                    ),

                    "cyclone_risk": safe_float(
                        hazard.cyclone_risk
                    ),
                },
            }
        )

    return {
        "type": "FeatureCollection",
        "features": features,
    }


# ============================================================
# SINGLE VILLAGE HAZARD
# ============================================================

@router.get("/{village_id}")
def get_hazard_assessment(
    village_id: int,
    db: Session = Depends(get_db),
):
    """
    Return the latest hazard assessment for one village.
    """

    result = (
        db.query(HazardAssessment, Village)
        .join(
            Village,
            HazardAssessment.village_id == Village.id,
        )
        .filter(
            Village.id == village_id
        )
        .order_by(
            HazardAssessment.id.desc()
        )
        .first()
    )

    if not result:
        return {
            "success": False,
            "data": None,
            "message": "Hazard assessment not found",
        }

    hazard, village = result

    data = serialize_hazard(
        hazard,
        village,
    )

    data["composite_score"] = data["hazard_score"]

    return {
        "success": True,
        "data": data,
    }