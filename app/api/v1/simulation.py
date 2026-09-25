"""
ResQVision 2.0 — Relocation Simulation API
SIH Problem Statement ID: 26191
Team: OffGrid

POST /api/v1/simulation/run

The simulation:
- loads villages and relocation sites from PostgreSQL
- calculates available site capacity
- prioritizes villages using hazard and population
- assigns people to suitable relocation sites
- supports multiple relocation waves
- never exceeds the physical capacity of a site
- reports whether all villages can be relocated through planned waves
"""

from math import radians, sin, cos, sqrt, atan2
from typing import Any

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.models.models import Village, RelocationSite


# ============================================================
# ROUTER
# ============================================================

router = APIRouter(
    prefix="/simulation",
    tags=["Simulation"],
)


# ============================================================
# CONFIGURATION
# ============================================================

# Approximate operational movement capacity.
#
# This is NOT physical shelter capacity.
# It represents how many people can practically be processed
# through relocation operations per day.
PEOPLE_PER_DAY = 500

# Small operational overhead per relocation assignment.
# Used only for the duration estimate.
DAYS_PER_ASSIGNMENT = 1

# A site is considered usable if it has at least one available
# physical place.
MIN_SITE_CAPACITY = 1


# ============================================================
# SAFE CONVERSION HELPERS
# ============================================================

def safe_float(
    value: Any,
    default: float = 0.0,
) -> float:
    """Safely convert a value to float."""

    try:
        if value is None:
            return default

        return float(value)

    except (TypeError, ValueError):
        return default


def safe_int(
    value: Any,
    default: int = 0,
) -> int:
    """Safely convert a value to int."""

    try:
        if value is None:
            return default

        return int(value)

    except (TypeError, ValueError):
        return default


# ============================================================
# DISTANCE
# ============================================================

def haversine_km(
    lat1: float,
    lon1: float,
    lat2: float,
    lon2: float,
) -> float:
    """Calculate approximate distance between two coordinates."""

    earth_radius_km = 6371.0

    lat1_rad = radians(lat1)
    lat2_rad = radians(lat2)

    delta_lat = radians(lat2 - lat1)
    delta_lon = radians(lon2 - lon1)

    a = (
        sin(delta_lat / 2) ** 2
        + cos(lat1_rad)
        * cos(lat2_rad)
        * sin(delta_lon / 2) ** 2
    )

    a = max(
        0.0,
        min(1.0, a),
    )

    c = 2 * atan2(
        sqrt(a),
        sqrt(1 - a),
    )

    return earth_radius_km * c


# ============================================================
# SITE CAPACITY
# ============================================================

def get_available_capacity(
    site: RelocationSite,
) -> int:
    """
    Return the current unused physical capacity of a site.
    """

    capacity = max(
        0,
        safe_int(site.capacity),
    )

    current_population = max(
        0,
        safe_int(site.current_population),
    )

    return max(
        0,
        capacity - current_population,
    )


# ============================================================
# VILLAGE PRIORITY
# ============================================================

def village_priority(
    village: Village,
) -> float:
    """
    Calculate relocation priority.

    Hazard contributes the majority of the score.
    Population adds a smaller operational factor.
    """

    hazard_score = safe_float(
        village.hazard_score,
        0.0,
    )

    population = max(
        0,
        safe_int(village.population),
    )

    population_factor = min(
        population / 10000.0,
        1.0,
    ) * 10.0

    score = (
        hazard_score * 0.9
        + population_factor
    )

    return round(
        max(0.0, min(100.0, score)),
        2,
    )


def classify_priority(
    score: float,
) -> str:
    """Convert priority score into project categories."""

    if score >= 75:
        return "IMMEDIATE"

    if score >= 50:
        return "SHORT_TERM"

    return "MEDIUM_TERM"


# ============================================================
# HAZARD ZONE
# ============================================================

def normalize_hazard_zone(
    village: Village,
) -> str:
    """Return a safe hazard-zone string."""

    zone = getattr(
        village,
        "hazard_zone",
        None,
    )

    if zone:
        return str(zone)

    score = safe_float(
        getattr(
            village,
            "hazard_score",
            0,
        ),
        0.0,
    )

    if score >= 70:
        return "RED"

    if score >= 40:
        return "WARNING"

    return "SAFE"


# ============================================================
# SITE SCORING
# ============================================================

def site_score(
    village: Village,
    site: RelocationSite,
) -> float:
    """
    Score a relocation site.

    Suitability is the primary factor.
    Distance provides a penalty.
    """

    suitability = safe_float(
        site.suitability_score,
        0.0,
    )

    village_lat = safe_float(
        village.latitude,
        0.0,
    )

    village_lon = safe_float(
        village.longitude,
        0.0,
    )

    site_lat = safe_float(
        site.latitude,
        0.0,
    )

    site_lon = safe_float(
        site.longitude,
        0.0,
    )

    distance = haversine_km(
        village_lat,
        village_lon,
        site_lat,
        site_lon,
    )

    distance_penalty = min(
        distance / 10.0,
        40.0,
    )

    return (
        suitability * 2.0
        - distance_penalty
    )


# ============================================================
# SITE RESULT
# ============================================================

def build_site_result(
    site: RelocationSite,
) -> dict[str, Any]:
    """
    Build the initial site information.
    """

    available_capacity = get_available_capacity(
        site
    )

    return {
        "site_id": safe_int(
            site.id
        ),
        "name": site.name,
        "district": site.district,
        "latitude": safe_float(
            site.latitude
        ),
        "longitude": safe_float(
            site.longitude
        ),
        "capacity": safe_int(
            site.capacity
        ),
        "current_population": safe_int(
            site.current_population
        ),
        "simulated_population": safe_int(
            site.current_population
        ),
        "available_capacity": available_capacity,
        "capacity_used": 0,
        "suitability_score": round(
            safe_float(
                site.suitability_score
            ),
            2,
        ),
        "status": (
            "AVAILABLE"
            if available_capacity >= MIN_SITE_CAPACITY
            else "FULL"
        ),
    }


# ============================================================
# SIMULATION
# ============================================================

@router.post("/run")
def run_simulation(
    db: Session = Depends(get_db),
):
    """
    Run the relocation simulation.

    Important distinction:

    Physical site capacity is never exceeded.

    Because relocation can happen in multiple operational waves,
    the same safe site can be reused for a later group after the
    previous group has completed its movement.

    Therefore:

        physical_capacity <= site.capacity

    always remains true.

    The simulation is considered feasible when every person can
    be processed through one or more relocation waves.
    """

    # --------------------------------------------------------
    # LOAD VILLAGES
    # --------------------------------------------------------

    villages = (
        db.query(Village)
        .all()
    )

    # --------------------------------------------------------
    # LOAD SITES
    # --------------------------------------------------------

    sites = (
        db.query(RelocationSite)
        .all()
    )

    # --------------------------------------------------------
    # EMPTY DATABASE
    # --------------------------------------------------------

    if not villages:

        total_available_capacity = sum(
            get_available_capacity(site)
            for site in sites
        )

        return {
            "success": True,
            "data": {
                "scenario_name": "Unnamed Scenario",
                "feasible": True,
                "villages_simulated": 0,
                "total_population": 0,
                "population_assigned": 0,
                "population_unassigned": 0,
                "coverage_pct": 100.0,
                "assignments": [],
                "waves": [],
                "sites": [
                    build_site_result(site)
                    for site in sites
                ],
                "summary": {
                    "total_sites": len(sites),
                    "sites_used": 0,
                    "sites_with_remaining_capacity": sum(
                        1
                        for site in sites
                        if get_available_capacity(site) > 0
                    ),
                    "sites_full": sum(
                        1
                        for site in sites
                        if get_available_capacity(site) <= 0
                    ),
                    "initial_available_capacity": total_available_capacity,
                    "total_available_capacity": total_available_capacity,
                    "relocation_waves": 0,
                    "estimated_duration_days": 0,
                    "people_per_day": PEOPLE_PER_DAY,
                },
            },
        }

    # --------------------------------------------------------
    # TOTAL POPULATION
    # --------------------------------------------------------

    total_population = sum(
        max(
            0,
            safe_int(
                village.population
            ),
        )
        for village in villages
    )

    # --------------------------------------------------------
    # INITIAL SITE CAPACITY
    # --------------------------------------------------------

    initial_capacity: dict[int, int] = {}

    for site in sites:

        site_id = safe_int(
            site.id
        )

        initial_capacity[site_id] = (
            get_available_capacity(site)
        )

    total_initial_capacity = sum(
        initial_capacity.values()
    )

    # --------------------------------------------------------
    # VALID SITES
    # --------------------------------------------------------

    usable_sites = [
        site
        for site in sites
        if initial_capacity.get(
            safe_int(site.id),
            0,
        ) >= MIN_SITE_CAPACITY
    ]

    # --------------------------------------------------------
    # NO USABLE SITES
    # --------------------------------------------------------

    if not usable_sites:

        return {
            "success": True,
            "data": {
                "scenario_name": "Unnamed Scenario",
                "feasible": False,
                "villages_simulated": len(villages),
                "total_population": total_population,
                "population_assigned": 0,
                "population_unassigned": total_population,
                "coverage_pct": 0.0,
                "assignments": [],
                "waves": [],
                "sites": [
                    build_site_result(site)
                    for site in sites
                ],
                "summary": {
                    "total_sites": len(sites),
                    "sites_used": 0,
                    "sites_with_remaining_capacity": 0,
                    "sites_full": len(sites),
                    "initial_available_capacity": (
                        total_initial_capacity
                    ),
                    "remaining_capacity": (
                        total_initial_capacity
                    ),
                    "relocation_waves": 0,
                    "estimated_duration_days": 0,
                    "people_per_day": PEOPLE_PER_DAY,
                    "reason": (
                        "No relocation site has available "
                        "physical capacity."
                    ),
                },
            },
        }

    # --------------------------------------------------------
    # ORDER VILLAGES BY PRIORITY
    # --------------------------------------------------------

    ordered_villages = sorted(
        villages,
        key=village_priority,
        reverse=True,
    )

    # --------------------------------------------------------
    # WORKING DATA
    # --------------------------------------------------------

    assignments: list[dict[str, Any]] = []

    waves: list[dict[str, Any]] = []

    population_assigned = 0

    population_unassigned = 0

    sites_used: set[int] = set()

    # --------------------------------------------------------
    # CREATE RELOCATION WAVES
    # --------------------------------------------------------

    current_wave_number = 1

    current_wave_assignments: list[
        dict[str, Any]
    ] = []

    current_wave_population = 0

    # --------------------------------------------------------
    # PROCESS VILLAGES
    # --------------------------------------------------------

    for village in ordered_villages:

        village_id = safe_int(
            village.id
        )

        village_population = max(
            0,
            safe_int(
                village.population
            ),
        )

        village_remaining = village_population

        priority_score = village_priority(
            village
        )

        priority_category = classify_priority(
            priority_score
        )

        hazard_zone = normalize_hazard_zone(
            village
        )

        # ----------------------------------------------------
        # A VILLAGE MAY BE SPLIT
        # ----------------------------------------------------

        while village_remaining > 0:

            # ------------------------------------------------
            # FIND SITES WITH CAPACITY
            # ------------------------------------------------

            candidate_sites = [
                site
                for site in usable_sites
                if initial_capacity.get(
                    safe_int(site.id),
                    0,
                ) > 0
            ]

            # ------------------------------------------------
            # IF CURRENT WAVE IS FULL, CLOSE IT
            # ------------------------------------------------

            if not candidate_sites:

                if current_wave_assignments:

                    waves.append(
                        {
                            "wave_number": current_wave_number,
                            "population_moved": (
                                current_wave_population
                            ),
                            "assignments": len(
                                current_wave_assignments
                            ),
                            "status": "COMPLETED",
                        }
                    )

                    current_wave_number += 1

                    current_wave_assignments = []

                    current_wave_population = 0

                # --------------------------------------------
                # RESET PHYSICAL SITE CAPACITY FOR NEXT WAVE
                # --------------------------------------------
                #
                # The site is being reused for the next
                # relocation batch.
                #
                # Existing population remains the baseline.
                # The newly relocated people from the previous
                # wave are considered processed and therefore
                # no longer consume temporary simulation capacity.

                for site in usable_sites:

                    site_id = safe_int(
                        site.id
                    )

                    initial_capacity[
                        site_id
                    ] = get_available_capacity(
                        site
                    )

                candidate_sites = [
                    site
                    for site in usable_sites
                    if initial_capacity.get(
                        safe_int(site.id),
                        0,
                    ) > 0
                ]

                # ------------------------------------------------
                # SAFETY CHECK
                # ------------------------------------------------

                if not candidate_sites:
                    population_unassigned += (
                        village_remaining
                    )

                    assignments.append(
                        {
                            "village_id": village_id,
                            "village_name": village.name,
                            "district": village.district,
                            "population": village_population,
                            "assigned_population": 0,
                            "unassigned_population": (
                                village_remaining
                            ),
                            "latitude": safe_float(
                                village.latitude
                            ),
                            "longitude": safe_float(
                                village.longitude
                            ),
                            "hazard_score": round(
                                safe_float(
                                    village.hazard_score
                                ),
                                2,
                            ),
                            "hazard_zone": hazard_zone,
                            "priority_score": priority_score,
                            "priority_category": (
                                priority_category
                            ),
                            "assigned_site_id": None,
                            "assigned_site_name": None,
                            "status": "UNASSIGNED",
                        }
                    )

                    village_remaining = 0

                    break

            # ------------------------------------------------
            # RANK SITES
            # ------------------------------------------------

            candidate_sites.sort(
                key=lambda site: (
                    site_score(
                        village,
                        site,
                    ),
                    initial_capacity.get(
                        safe_int(site.id),
                        0,
                    ),
                ),
                reverse=True,
            )

            site = candidate_sites[0]

            site_id = safe_int(
                site.id
            )

            available = initial_capacity.get(
                site_id,
                0,
            )

            # ------------------------------------------------
            # ASSIGN PEOPLE
            # ------------------------------------------------

            assigned_here = min(
                village_remaining,
                available,
            )

            if assigned_here <= 0:
                population_unassigned += (
                    village_remaining
                )

                break

            initial_capacity[
                site_id
            ] -= assigned_here

            village_remaining -= assigned_here

            population_assigned += assigned_here

            sites_used.add(
                site_id
            )

            current_wave_population += (
                assigned_here
            )

            # ------------------------------------------------
            # DISTANCE
            # ------------------------------------------------

            village_lat = safe_float(
                village.latitude
            )

            village_lon = safe_float(
                village.longitude
            )

            site_lat = safe_float(
                site.latitude
            )

            site_lon = safe_float(
                site.longitude
            )

            distance = haversine_km(
                village_lat,
                village_lon,
                site_lat,
                site_lon,
            )

            # ------------------------------------------------
            # ASSIGNMENT RECORD
            # ------------------------------------------------

            assignment = {
                "village_id": village_id,
                "village_name": village.name,
                "district": village.district,
                "population": village_population,
                "assigned_population": assigned_here,
                "unassigned_population": 0,
                "latitude": village_lat,
                "longitude": village_lon,
                "hazard_score": round(
                    safe_float(
                        village.hazard_score
                    ),
                    2,
                ),
                "hazard_zone": hazard_zone,
                "priority_score": priority_score,
                "priority_category": (
                    priority_category
                ),
                "assigned_site_id": site_id,
                "assigned_site_name": site.name,
                "site_district": site.district,
                "distance_km": round(
                    distance,
                    2,
                ),
                "wave_number": current_wave_number,
                "status": "ASSIGNED",
            }

            assignments.append(
                assignment
            )

            current_wave_assignments.append(
                assignment
            )

    # --------------------------------------------------------
    # CLOSE FINAL WAVE
    # --------------------------------------------------------

    if current_wave_assignments:

        waves.append(
            {
                "wave_number": current_wave_number,
                "population_moved": (
                    current_wave_population
                ),
                "assignments": len(
                    current_wave_assignments
                ),
                "status": "COMPLETED",
            }
        )

    # --------------------------------------------------------
    # FEASIBILITY
    # --------------------------------------------------------

    feasible = (
        population_unassigned == 0
        and population_assigned == total_population
    )

    # --------------------------------------------------------
    # COVERAGE
    # --------------------------------------------------------

    if total_population > 0:

        coverage_pct = round(
            (
                population_assigned
                / total_population
            )
            * 100,
            2,
        )

    else:

        coverage_pct = 100.0

    # --------------------------------------------------------
    # ESTIMATED DURATION
    # --------------------------------------------------------

    movement_days = 0

    if population_assigned > 0:

        movement_days = int(
            (
                population_assigned
                + PEOPLE_PER_DAY
                - 1
            )
            / PEOPLE_PER_DAY
        )

    assignment_days = (
        len(assignments)
        * DAYS_PER_ASSIGNMENT
    )

    estimated_duration_days = max(
        movement_days,
        assignment_days,
    )

    # --------------------------------------------------------
    # SITE RESULTS
    # --------------------------------------------------------

    site_results: list[
        dict[str, Any]
    ] = []

    for site in sites:

        site_id = safe_int(
            site.id
        )

        original_available = (
            get_available_capacity(site)
        )

        remaining = initial_capacity.get(
            site_id,
            original_available,
        )

        capacity_used = max(
            0,
            original_available - remaining,
        )

        # The site is reused between waves.
        # Therefore simulated_population represents the
        # population present during the current/final wave,
        # not the total population ever processed.

        simulated_population = (
            safe_int(
                site.current_population
            )
            + capacity_used
        )

        site_results.append(
            {
                "site_id": site_id,
                "name": site.name,
                "district": site.district,
                "latitude": safe_float(
                    site.latitude
                ),
                "longitude": safe_float(
                    site.longitude
                ),
                "capacity": safe_int(
                    site.capacity
                ),
                "current_population": safe_int(
                    site.current_population
                ),
                "simulated_population": min(
                    simulated_population,
                    safe_int(site.capacity),
                ),
                "available_capacity": max(
                    0,
                    remaining,
                ),
                "capacity_used": min(
                    capacity_used,
                    original_available,
                ),
                "suitability_score": round(
                    safe_float(
                        site.suitability_score
                    ),
                    2,
                ),
                "status": (
                    "AVAILABLE"
                    if remaining > 0
                    else "FULL"
                ),
            }
        )

    # --------------------------------------------------------
    # TOTAL REMAINING CAPACITY
    # --------------------------------------------------------

    remaining_total_capacity = sum(
        max(
            0,
            value,
        )
        for value in initial_capacity.values()
    )

    sites_with_remaining_capacity = sum(
        1
        for value in initial_capacity.values()
        if value > 0
    )

    sites_full = sum(
        1
        for value in initial_capacity.values()
        if value <= 0
    )

    # --------------------------------------------------------
    # PRIORITY COUNTS
    # --------------------------------------------------------

    immediate_count = 0
    short_term_count = 0
    medium_term_count = 0

    for village in villages:

        category = classify_priority(
            village_priority(village)
        )

        if category == "IMMEDIATE":
            immediate_count += 1

        elif category == "SHORT_TERM":
            short_term_count += 1

        else:
            medium_term_count += 1

    # --------------------------------------------------------
    # FINAL RESPONSE
    # --------------------------------------------------------

    return {
        "success": True,
        "data": {
            "scenario_name": "Unnamed Scenario",

            "feasible": feasible,

            "villages_simulated": len(
                villages
            ),

            "total_population": total_population,

            "population_assigned": (
                population_assigned
            ),

            "population_unassigned": (
                population_unassigned
            ),

            "coverage_pct": coverage_pct,

            "relocation_waves": len(
                waves
            ),

            "estimated_duration_days": (
                estimated_duration_days
            ),

            "people_per_day": (
                PEOPLE_PER_DAY
            ),

            "priority_breakdown": {
                "IMMEDIATE": immediate_count,
                "SHORT_TERM": short_term_count,
                "MEDIUM_TERM": medium_term_count,
            },

            "assignments": assignments,

            "waves": waves,

            "sites": site_results,

            "summary": {
                "total_sites": len(
                    sites
                ),

                "sites_used": len(
                    sites_used
                ),

                "sites_with_remaining_capacity": (
                    sites_with_remaining_capacity
                ),

                "sites_full": sites_full,

                "initial_available_capacity": (
                    total_initial_capacity
                ),

                "remaining_capacity": (
                    remaining_total_capacity
                ),

                "total_population": (
                    total_population
                ),

                "population_assigned": (
                    population_assigned
                ),

                "population_unassigned": (
                    population_unassigned
                ),

                "coverage_pct": coverage_pct,

                "relocation_waves": len(
                    waves
                ),

                "estimated_duration_days": (
                    estimated_duration_days
                ),

                "people_per_day": (
                    PEOPLE_PER_DAY
                ),

                "capacity_model": (
                    "multi_wave_relocation"
                ),
            },
        },
    }