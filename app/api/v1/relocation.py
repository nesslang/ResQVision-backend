"""
Relocation router — /api/v1/relocation

Provides:
- Relocation plans
- Relocation assignments
- Village relocation priority
- Relocation flow GeoJSON
"""

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional

from app.core.database import get_db
from app.models.models import Village

router = APIRouter(prefix="/relocation", tags=["Relocation"])


@router.get("/priority")
def list_relocation_priority(
    category: Optional[str] = Query(
        None,
        description="Filter by priority category: IMMEDIATE|SHORT_TERM|MEDIUM_TERM",
    ),
    district: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """
    Return villages ordered by relocation priority.

    Priority is calculated/stored on the Village model using:
    - priority_score
    - priority_category
    """

    query = db.query(Village)

    if category:
        query = query.filter(
            Village.priority_category == category.upper()
        )

    if district:
        query = query.filter(
            Village.district.ilike(f"%{district}%")
        )

    total = query.count()

    villages = (
        query
        .order_by(Village.priority_score.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    items = []

    for village in villages:
        items.append(
            {
                "id": village.id,
                "village_id": village.id,
                "village_name": village.name,
                "district": village.district,

                "population": village.population,
                "elderly": village.elderly,
                "children": village.children,
                "disabled": village.disabled,

                "latitude": village.latitude,
                "longitude": village.longitude,

                "hazard_score": village.hazard_score,
                "hazard_zone": village.hazard_zone,

                "vulnerability_score": village.vulnerability_score,

                "priority_score": village.priority_score,
                "priority_category": village.priority_category,

                "created_at": (
                    village.created_at.isoformat()
                    if village.created_at
                    else None
                ),
            }
        )

    return {
        "success": True,
        "data": {
            "items": items,
            "total": total,
            "limit": limit,
            "offset": offset,
        },
    }


@router.get("/plans")
def list_relocation_plans(
    status: Optional[str] = Query(
        None,
        description="DRAFT|APPROVED|IN_PROGRESS|COMPLETED",
    ),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
):
    """List all relocation plans with optional status filter."""

    return {
        "success": True,
        "data": {
            "items": [],
            "total": 0,
            "limit": limit,
            "offset": offset,
        },
    }


@router.post("/plans")
def create_relocation_plan(
    payload: dict,
    db: Session = Depends(get_db),
):
    """Create a new relocation plan."""

    return {
        "success": True,
        "data": {
            "plan_id": None,
            "name": payload.get("name", "New Plan"),
            "status": "DRAFT",
            "total_villages": 0,
            "total_persons": 0,
        },
    }


@router.get("/plans/{plan_id}")
def get_relocation_plan(
    plan_id: int,
    db: Session = Depends(get_db),
):
    """Return full relocation plan detail."""

    return {
        "success": True,
        "data": {
            "plan_id": plan_id,
            "assignments": [],
            "status": "not_found",
        },
    }


@router.put("/plans/{plan_id}/status")
def update_plan_status(
    plan_id: int,
    payload: dict,
    db: Session = Depends(get_db),
):
    """Transition a relocation plan through its lifecycle states."""

    new_status = payload.get("status")

    allowed = {
        "DRAFT",
        "APPROVED",
        "IN_PROGRESS",
        "COMPLETED",
        "CANCELLED",
    }

    if new_status not in allowed:
        return {
            "success": False,
            "error": {
                "code": "INVALID_STATUS",
                "message": f"Status must be one of {allowed}",
            },
        }

    return {
        "success": True,
        "data": {
            "plan_id": plan_id,
            "status": new_status,
        },
    }


@router.get("/assignments")
def list_assignments(
    plan_id: Optional[int] = Query(None),
    village_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """List village-to-site relocation assignments."""

    return {
        "success": True,
        "data": {
            "items": [],
            "total": 0,
        },
    }


@router.get("/geojson/flow")
def get_relocation_flow_geojson(
    plan_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
):
    """Return relocation flow lines as GeoJSON."""

    return {
        "type": "FeatureCollection",
        "features": [],
    }