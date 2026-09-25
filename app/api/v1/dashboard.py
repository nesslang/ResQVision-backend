"""
ResQVision 2.0 — Dashboard API
SIH Problem Statement ID: 26191
Team: OffGrid

Provides live dashboard statistics from PostgreSQL.

GET /api/v1/dashboard/summary
GET /api/v1/dashboard/alerts
GET /api/v1/dashboard/recent-activity
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import (
    Village,
    HazardAssessment,
    RelocationSite,
)


router = APIRouter(
    prefix="/dashboard",
    tags=["Dashboard"],
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


def normalize_zone(value):
    """
    Normalize hazard zones into:

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

    This keeps Dashboard and Hazard Analysis synchronized
    when historical assessments exist.
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
            latest[village.id] = (
                hazard,
                village,
            )

    return list(latest.values())


def get_priority_category(
    hazard_score,
    population,
):
    """
    Calculate relocation priority from current
    hazard assessment and population.
    """

    hazard_score = safe_float(
        hazard_score
    )

    population = safe_int(
        population
    )

    population_factor = min(
        population / 10000.0,
        1.0,
    ) * 10.0

    score = (
        hazard_score * 0.9
        + population_factor
    )

    if score >= 75:
        return "IMMEDIATE"

    if score >= 50:
        return "SHORT_TERM"

    return "MEDIUM_TERM"


# ============================================================
# SUMMARY
# ============================================================

@router.get("/summary")
def get_dashboard_summary(
    db: Session = Depends(get_db),
):
    """
    Return live dashboard KPIs directly from PostgreSQL.

    Hazard information comes from HazardAssessment so that
    Dashboard and Hazard Analysis use the same source.
    """

    hazard_rows = get_latest_hazard_rows(db)

    sites = (
        db.query(RelocationSite)
        .all()
    )

    total_villages = len(hazard_rows)
    total_sites = len(sites)

    # --------------------------------------------------------
    # POPULATION
    # --------------------------------------------------------

    total_population = sum(
        max(
            0,
            safe_int(
                village.population
            ),
        )
        for _, village in hazard_rows
    )

    # --------------------------------------------------------
    # HAZARD ZONES
    # --------------------------------------------------------

    hazard_zones = {
        "SAFE": 0,
        "WARNING": 0,
        "RED": 0,
    }

    population_at_risk = 0

    for hazard, village in hazard_rows:

        zone = normalize_zone(
            hazard.zone
        )

        hazard_zones[zone] += 1

        population = max(
            0,
            safe_int(
                village.population
            ),
        )

        if zone in {
            "WARNING",
            "RED",
        }:
            population_at_risk += population

    # --------------------------------------------------------
    # RELOCATION PRIORITY
    # --------------------------------------------------------

    priority_breakdown = {
        "IMMEDIATE": 0,
        "SHORT_TERM": 0,
        "MEDIUM_TERM": 0,
    }

    for hazard, village in hazard_rows:

        category = get_priority_category(
            hazard.hazard_score,
            village.population,
        )

        priority_breakdown[category] += 1

    # --------------------------------------------------------
    # RELOCATION SITES
    # --------------------------------------------------------

    total_capacity = sum(
        max(
            0,
            safe_int(
                site.capacity
            ),
        )
        for site in sites
    )

    current_site_population = sum(
        max(
            0,
            safe_int(
                site.current_population
            ),
        )
        for site in sites
    )

    total_available_capacity = sum(
        max(
            0,
            safe_int(site.capacity)
            - safe_int(
                site.current_population
            ),
        )
        for site in sites
    )

    # --------------------------------------------------------
    # RELOCATION COVERAGE
    # --------------------------------------------------------

    relocation_coverage_pct = 0.0

    if population_at_risk > 0:

        covered_population = min(
            total_available_capacity,
            population_at_risk,
        )

        relocation_coverage_pct = round(
            (
                covered_population
                / population_at_risk
            )
            * 100,
            2,
        )

    return {
        "success": True,

        "data": {
            "total_villages": total_villages,

            "hazard_zones": hazard_zones,

            "priority_breakdown": priority_breakdown,

            "total_sites": total_sites,

            "total_capacity": total_capacity,

            "total_available_capacity": (
                total_available_capacity
            ),

            "current_site_population": (
                current_site_population
            ),

            "total_displaced": population_at_risk,

            "population_at_risk": population_at_risk,

            "total_population": total_population,

            "relocation_coverage_pct": (
                relocation_coverage_pct
            ),
        },
    }


# ============================================================
# ALERTS
# ============================================================

@router.get("/alerts")
def get_active_alerts(
    db: Session = Depends(get_db),
):
    """
    Generate dashboard alerts from the current
    HazardAssessment records.
    """

    hazard_rows = get_latest_hazard_rows(db)

    alerts = []

    for hazard, village in hazard_rows:

        hazard_score = safe_float(
            hazard.hazard_score
        )

        zone = normalize_zone(
            hazard.zone
        )

        population = safe_int(
            village.population
        )

        village_id = safe_int(
            village.id
        )

        village_name = village.name

        district = village.district

        if (
            zone == "RED"
            or hazard_score >= 75
        ):

            alerts.append(
                {
                    "village_id": village_id,

                    "village_name": village_name,

                    "district": district,

                    "severity": "CRITICAL",

                    "hazard_score": round(
                        hazard_score,
                        2,
                    ),

                    "population": population,

                    "message": (
                        f"{village_name} "
                        "requires immediate attention."
                    ),
                }
            )

        elif (
            zone == "WARNING"
            or hazard_score >= 50
        ):

            alerts.append(
                {
                    "village_id": village_id,

                    "village_name": village_name,

                    "district": district,

                    "severity": "WARNING",

                    "hazard_score": round(
                        hazard_score,
                        2,
                    ),

                    "population": population,

                    "message": (
                        f"{village_name} "
                        "requires monitoring and preparedness."
                    ),
                }
            )

    alerts.sort(
        key=lambda item: (
            item["hazard_score"],
            item["population"],
        ),
        reverse=True,
    )

    alerts = alerts[:20]

    return {
        "success": True,

        "data": {
            "alerts": alerts,
            "total": len(alerts),
        },
    }


# ============================================================
# RECENT ACTIVITY
# ============================================================

@router.get("/recent-activity")
def get_recent_activity(
    limit: int = Query(
        10,
        ge=1,
        le=50,
    ),
    db: Session = Depends(get_db),
):
    """
    Return latest hazard assessment activity.
    """

    hazard_rows = get_latest_hazard_rows(
        db
    )

    hazard_rows.sort(
        key=lambda row: safe_float(
            row[0].hazard_score
        ),
        reverse=True,
    )

    hazard_rows = hazard_rows[:limit]

    activities = []

    for hazard, village in hazard_rows:

        village_id = safe_int(
            village.id
        )

        village_name = village.name

        district = village.district

        hazard_score = safe_float(
            hazard.hazard_score
        )

        zone = normalize_zone(
            hazard.zone
        )

        activities.append(
            {
                "type": "HAZARD_ASSESSMENT",

                "village_id": village_id,

                "village_name": village_name,

                "district": district,

                "zone": zone,

                "hazard_score": round(
                    hazard_score,
                    2,
                ),

                "message": (
                    f"Hazard assessment recorded "
                    f"for {village_name}."
                ),
            }
        )

    return {
        "success": True,

        "data": {
            "activities": activities,

            "total": len(activities),
        },
    }