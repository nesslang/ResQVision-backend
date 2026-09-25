"""
ResQVision 2.0 — Analytics Router
/api/v1/analytics

Provides database-backed:
- System overview
- Hazard trends
- Hazard correlation
- District comparison
- Feature importance placeholder
"""

from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import HazardAssessment
from app.models.models import (
    Village,

    RelocationSite,
    RelocationAssignment,
)

router = APIRouter(
    prefix="/analytics",
    tags=["Analytics"],
)


# ============================================================
# HELPERS
# ============================================================

def classify_hazard(score: float) -> str:
    """
    Convert a 0–100 hazard score into a risk zone.
    """

    if score >= 80:
        return "RED"

    if score >= 60:
        return "WARNING"

    return "SAFE"


def classify_priority(score: float) -> str:
    """
    Convert a 0–100 priority score into relocation priority.
    """

    if score >= 80:
        return "IMMEDIATE"

    if score >= 60:
        return "SHORT_TERM"

    return "MEDIUM_TERM"


def classify_pressure(utilisation: float) -> str:
    """
    Convert capacity utilisation percentage
    into pressure level.
    """

    if utilisation > 100:
        return "CRITICAL"

    if utilisation >= 85:
        return "CRITICAL"

    if utilisation >= 70:
        return "HIGH"

    if utilisation >= 40:
        return "MODERATE"

    return "LOW"


# ============================================================
# OVERVIEW
# ============================================================

@router.get("/overview")
def get_analytics_overview(
    db: Session = Depends(get_db),
):
    """
    Return system-wide analytics summary
    calculated from the database.
    """

    # --------------------------------------------------------
    # HAZARD DISTRIBUTION
    # --------------------------------------------------------

    hazard_distribution = {
        "SAFE": 0,
        "WARNING": 0,
        "RED": 0,
    }

    hazards = db.query(HazardAssessment).all()

    hazard_scores = []

    for hazard in hazards:

        # Hazard model normally contains risk_score.
        # Fall back to individual hazard components when needed.
        score = getattr(hazard, "risk_score", None)

        if score is None:
            components = [
                getattr(hazard, "flood_risk", 0) or 0,
                getattr(hazard, "landslide_risk", 0) or 0,
                getattr(hazard, "earthquake_risk", 0) or 0,
                getattr(hazard, "drought_risk", 0) or 0,
                getattr(hazard, "cyclone_risk", 0) or 0,
            ]

            score = max(components) if components else 0

        score = float(score or 0)

        hazard_scores.append(score)

        zone = classify_hazard(score)

        hazard_distribution[zone] += 1

    # --------------------------------------------------------
    # PRIORITY DISTRIBUTION
    # --------------------------------------------------------

    priority_distribution = {
        "IMMEDIATE": 0,
        "SHORT_TERM": 0,
        "MEDIUM_TERM": 0,
    }

    villages = db.query(Village).all()

    for village in villages:

        priority_score = getattr(
            village,
            "priority_score",
            None,
        )

        if priority_score is None:
            priority_score = getattr(
                village,
                "relocation_priority_score",
                None,
            )

        if priority_score is None:
            priority_score = getattr(
                village,
                "risk_score",
                None,
            )

        if priority_score is None:
            priority_score = 0

        priority_score = float(priority_score or 0)

        priority = classify_priority(
            priority_score
        )

        priority_distribution[priority] += 1

    # --------------------------------------------------------
    # CAPACITY PRESSURE
    # --------------------------------------------------------

    pressure_distribution = {
        "LOW": 0,
        "MODERATE": 0,
        "HIGH": 0,
        "CRITICAL": 0,
    }

    sites = db.query(RelocationSite).all()

    total_capacity_available = 0
    suitability_scores = []

    for site in sites:

        capacity = int(
            getattr(site, "capacity", 0) or 0
        )

        current_population = int(
            getattr(site, "current_population", 0) or 0
        )

        available = max(
            capacity - current_population,
            0,
        )

        total_capacity_available += available

        suitability_scores.append(
            float(
                getattr(
                    site,
                    "suitability_score",
                    0,
                )
                or 0
            )
        )

        if capacity > 0:
            utilisation = (
                current_population / capacity
            ) * 100
        else:
            utilisation = 0

        pressure = classify_pressure(
            utilisation
        )

        pressure_distribution[pressure] += 1

    # --------------------------------------------------------
    # AVERAGE SCORES
    # --------------------------------------------------------

    avg_hazard_score = (
        sum(hazard_scores) / len(hazard_scores)
        if hazard_scores
        else 0.0
    )

    avg_suitability_score = (
        sum(suitability_scores)
        / len(suitability_scores)
        if suitability_scores
        else 0.0
    )

    # --------------------------------------------------------
    # RELOCATION DEMAND
    # --------------------------------------------------------

    total_relocation_demand = 0

    for village in villages:

        population = getattr(
            village,
            "population",
            None,
        )

        if population is None:
            population = getattr(
                village,
                "total_population",
                0,
            )

        population = int(
            population or 0
        )

        # Count population in warning/red
        # villages as relocation demand.
        risk_score = getattr(
            village,
            "risk_score",
            None,
        )

        if risk_score is None:
            risk_score = getattr(
                village,
                "hazard_score",
                None,
            )

        if risk_score is None:
            risk_score = 0

        if float(risk_score or 0) >= 60:
            total_relocation_demand += population

    # --------------------------------------------------------
    # ASSIGNMENTS
    # --------------------------------------------------------

    assigned_population = 0

    try:
        assigned_population = int(
            db.query(
                func.coalesce(
                    func.sum(
                        RelocationAssignment.persons
                    ),
                    0,
                )
            ).scalar()
            or 0
        )
    except Exception:
        assigned_population = 0

    # --------------------------------------------------------
    # COVERAGE GAP
    # --------------------------------------------------------

    coverage_gap = max(
        total_relocation_demand
        - total_capacity_available
        - assigned_population,
        0,
    )

    # --------------------------------------------------------
    # RESPONSE
    # --------------------------------------------------------

    return {
        "success": True,
        "data": {
            "hazard_distribution": hazard_distribution,

            "priority_distribution": priority_distribution,

            "pressure_distribution": pressure_distribution,

            "avg_suitability_score": round(
                avg_suitability_score,
                2,
            ),

            "avg_hazard_score": round(
                avg_hazard_score,
                2,
            ),

            "total_capacity_available": (
                total_capacity_available
            ),

            "total_relocation_demand": (
                total_relocation_demand
            ),

            "coverage_gap": coverage_gap,
        },
    }


# ============================================================
# TRENDS
# ============================================================

@router.get("/trends")
def get_trends(
    metric: str = Query(
        "hazard_score",
        description="Metric to trend",
    ),
    period: str = Query(
        "30d",
        description="Time window: 7d|30d|90d|1y",
    ),
    db: Session = Depends(get_db),
):
    """
    Return time-series analytics.

    Uses Hazard.created_at and risk-related
    fields from the database.
    """

    # --------------------------------------------------------
    # PERIOD
    # --------------------------------------------------------

    period_days = {
        "7d": 7,
        "30d": 30,
        "90d": 90,
        "1y": 365,
    }

    days = period_days.get(
        period,
        30,
    )

    start_date = datetime.utcnow() - timedelta(
        days=days
    )

    # --------------------------------------------------------
    # FETCH HAZARDS
    # --------------------------------------------------------

    hazards = (
        db.query(HazardAssessment)
        .filter(
            HazardAssessment.created_at >= start_date
        )
        .order_by(
            HazardAssessment.created_at.asc()
        )
        .all()
    )

    # --------------------------------------------------------
    # GROUP BY DATE
    # --------------------------------------------------------

    daily_values = {}

    for hazard in hazards:

        created_at = getattr(
            hazard,
            "created_at",
            None,
        )

        if created_at is None:
            continue

        date_key = created_at.strftime(
            "%Y-%m-%d"
        )

        score = getattr(
            hazard,
            "risk_score",
            None,
        )

        if score is None:

            components = [
                getattr(
                    hazard,
                    "flood_risk",
                    0,
                )
                or 0,

                getattr(
                    hazard,
                    "landslide_risk",
                    0,
                )
                or 0,

                getattr(
                    hazard,
                    "earthquake_risk",
                    0,
                )
                or 0,

                getattr(
                    hazard,
                    "drought_risk",
                    0,
                )
                or 0,

                getattr(
                    hazard,
                    "cyclone_risk",
                    0,
                )
                or 0,
            ]

            score = (
                max(components)
                if components
                else 0
            )

        score = float(score or 0)

        if date_key not in daily_values:
            daily_values[date_key] = []

        daily_values[date_key].append(
            score
        )

    # --------------------------------------------------------
    # CREATE SERIES
    # --------------------------------------------------------

    series = []

    for date_key in sorted(
        daily_values.keys()
    ):

        values = daily_values[date_key]

        average = (
            sum(values) / len(values)
            if values
            else 0
        )

        series.append(
            {
                "date": date_key,
                "value": round(
                    average,
                    2,
                ),
            }
        )

    return {
        "success": True,
        "data": {
            "metric": metric,
            "period": period,
            "series": series,
        },
    }


# ============================================================
# HAZARD CORRELATION
# ============================================================

@router.get("/hazard-correlation")
def get_hazard_correlation(
    db: Session = Depends(get_db),
):
    """
    Return basic hazard subtype correlation data.

    This endpoint provides a lightweight matrix
    calculated from the hazard table.
    """

    hazards = db.query(HazardAssessment).all()

    labels = [
        "flood",
        "landslide",
        "earthquake",
        "drought",
        "cyclone",
    ]

    matrix = {}

    for label_a in labels:

        matrix[label_a] = {}

        for label_b in labels:

            values_a = []
            values_b = []

            for hazard in hazards:

                value_a = float(
                    getattr(
                        hazard,
                        f"{label_a}_risk",
                        0,
                    )
                    or 0
                )

                value_b = float(
                    getattr(
                        hazard,
                        f"{label_b}_risk",
                        0,
                    )
                    or 0
                )

                values_a.append(value_a)
                values_b.append(value_b)

            # Pearson correlation
            # calculated without numpy.
            if (
                len(values_a) < 2
                or len(values_b) < 2
            ):
                correlation = 0.0

            else:

                mean_a = (
                    sum(values_a)
                    / len(values_a)
                )

                mean_b = (
                    sum(values_b)
                    / len(values_b)
                )

                numerator = sum(
                    (
                        a - mean_a
                    )
                    * (
                        b - mean_b
                    )
                    for a, b in zip(
                        values_a,
                        values_b,
                    )
                )

                denominator_a = sum(
                    (
                        a - mean_a
                    ) ** 2
                    for a in values_a
                )

                denominator_b = sum(
                    (
                        b - mean_b
                    ) ** 2
                    for b in values_b
                )

                denominator = (
                    denominator_a
                    * denominator_b
                ) ** 0.5

                correlation = (
                    numerator / denominator
                    if denominator
                    else 0.0
                )

            matrix[label_a][label_b] = round(
                correlation,
                3,
            )

    return {
        "success": True,
        "data": {
            "matrix": matrix,
            "labels": labels,
        },
    }


# ============================================================
# FEATURE IMPORTANCE
# ============================================================

@router.get(
    "/feature-importance/{model_type}"
)
def get_feature_importance(
    model_type: str,
    method: str = Query(
        "shap",
        description="shap|native",
    ),
    db: Session = Depends(get_db),
):
    """
    Return feature importance information.

    If a trained ML model is not available,
    return the known ResQVision analytical features.
    """

    importance = {
        "flood_risk": 0.0,
        "landslide_risk": 0.0,
        "earthquake_risk": 0.0,
        "drought_risk": 0.0,
        "cyclone_risk": 0.0,
        "rainfall": 0.0,
        "elevation": 0.0,
        "slope": 0.0,
        "distance_from_river": 0.0,
    }

    return {
        "success": True,
        "data": {
            "model_type": model_type,
            "method": method,
            "importance": importance,
        },
    }


# ============================================================
# DISTRICT COMPARISON
# ============================================================

@router.get("/district-comparison")
def get_district_comparison(
    metric: str = Query(
        "hazard_score"
    ),
    db: Session = Depends(get_db),
):
    """
    Compare districts using village and hazard data.
    """

    villages = db.query(Village).all()

    district_data = {}

    for village in villages:

        district = getattr(
            village,
            "district",
            None,
        )

        if not district:
            district = getattr(
                village,
                "district_name",
                None,
            )

        if not district:
            district = "Unknown"

        population = getattr(
            village,
            "population",
            None,
        )

        if population is None:
            population = getattr(
                village,
                "total_population",
                0,
            )

        population = int(
            population or 0
        )

        risk = getattr(
            village,
            "risk_score",
            None,
        )

        if risk is None:
            risk = getattr(
                village,
                "hazard_score",
                None,
            )

        if risk is None:
            risk = 0

        risk = float(
            risk or 0
        )

        if district not in district_data:

            district_data[district] = {
                "name": district,
                "risk_values": [],
                "habitations": 0,
                "population": 0,
            }

        district_data[district][
            "risk_values"
        ].append(risk)

        district_data[district][
            "habitations"
        ] += 1

        district_data[district][
            "population"
        ] += population

    # --------------------------------------------------------
    # FORMAT RESPONSE
    # --------------------------------------------------------

    districts = []

    for data in district_data.values():

        risks = data["risk_values"]

        average_risk = (
            sum(risks)
            / len(risks)
            if risks
            else 0
        )

        districts.append(
            {
                "name": data["name"],
                "risk": round(
                    average_risk,
                    2,
                ),
                "habitations": data[
                    "habitations"
                ],
                "population": data[
                    "population"
                ],
            }
        )

    # Highest risk first.
    districts.sort(
        key=lambda item: item["risk"],
        reverse=True,
    )

    return {
        "success": True,
        "data": {
            "districts": districts,
            "metric": metric,
        },
    }