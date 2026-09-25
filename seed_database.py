import random
from datetime import datetime

from app.core.database import SessionLocal, create_tables
from app.models import (
    Village,
    HazardAssessment,
    RelocationSite,
    RelocationAssignment,
)


random.seed(42)


# ---------------------------------------------------------
# Maharashtra development locations
# ---------------------------------------------------------

DISTRICTS = {
    "Ratnagiri": (16.9944, 73.3000),
    "Raigad": (18.5158, 73.1822),
    "Sindhudurg": (16.3492, 73.5594),
    "Kolhapur": (16.7050, 74.2433),
    "Satara": (17.6805, 74.0183),
    "Pune": (18.5204, 73.8567),
    "Nashik": (19.9975, 73.7898),
    "Palghar": (19.6967, 72.7699),
    "Thane": (19.2183, 72.9781),
    "Ahmednagar": (19.0948, 74.7480),
}


VILLAGE_PREFIXES = [
    "Shiv",
    "Ganesh",
    "Krishna",
    "Sahyadri",
    "Mangal",
    "Jai",
    "Mahalaxmi",
    "Pragati",
    "Vijay",
    "Nandan",
]


def clamp(value, minimum=0, maximum=100):
    return max(minimum, min(maximum, value))


def hazard_zone(score):
    if score >= 70:
        return "RED"
    elif score >= 40:
        return "WARNING"
    return "SAFE"


def priority_category(score):
    if score >= 75:
        return "IMMEDIATE"
    elif score >= 50:
        return "SHORT_TERM"
    return "MEDIUM_TERM"


def generate_villages(count=100):
    villages = []

    district_names = list(DISTRICTS.keys())

    for i in range(count):
        district = random.choice(district_names)
        base_lat, base_lon = DISTRICTS[district]

        population = random.randint(300, 5000)

        elderly = int(population * random.uniform(0.06, 0.15))
        children = int(population * random.uniform(0.12, 0.25))
        disabled = int(population * random.uniform(0.01, 0.05))

        # Synthetic hazard components
        flood = random.uniform(5, 95)
        landslide = random.uniform(5, 90)
        earthquake = random.uniform(10, 75)
        drought = random.uniform(5, 90)
        cyclone = random.uniform(5, 80)

        hazard_score = (
            flood * 0.30
            + landslide * 0.20
            + earthquake * 0.15
            + drought * 0.20
            + cyclone * 0.15
        )

        hazard_score = round(clamp(hazard_score), 2)

        vulnerability = (
            (elderly / population) * 100 * 0.25
            + (children / population) * 100 * 0.25
            + (disabled / population) * 100 * 0.20
            + random.uniform(20, 80) * 0.30
        )

        vulnerability = round(clamp(vulnerability), 2)

        priority_score = (
            hazard_score * 0.60
            + vulnerability * 0.40
        )

        priority_score = round(clamp(priority_score), 2)

        village = Village(
            name=f"{random.choice(VILLAGE_PREFIXES)} Nagar {i + 1}",
            district=district,
            population=population,
            elderly=elderly,
            children=children,
            disabled=disabled,
            latitude=base_lat + random.uniform(-0.20, 0.20),
            longitude=base_lon + random.uniform(-0.20, 0.20),
            hazard_score=hazard_score,
            hazard_zone=hazard_zone(hazard_score),
            vulnerability_score=vulnerability,
            priority_score=priority_score,
            priority_category=priority_category(priority_score),
        )

        villages.append(village)

    return villages


def generate_hazard(village):
    score = village.hazard_score

    return HazardAssessment(
        village_id=village.id,
        hazard_score=score,
        zone=village.hazard_zone,
        flood_risk=round(random.uniform(10, 95), 2),
        landslide_risk=round(random.uniform(5, 90), 2),
        earthquake_risk=round(random.uniform(10, 75), 2),
        drought_risk=round(random.uniform(5, 90), 2),
        cyclone_risk=round(random.uniform(5, 80), 2),
        rainfall=round(random.uniform(500, 3500), 2),
        elevation=round(random.uniform(5, 1200), 2),
        slope=round(random.uniform(1, 45), 2),
        distance_from_river=round(random.uniform(0.2, 25), 2),
    )


def generate_sites(count=20):
    sites = []

    district_names = list(DISTRICTS.keys())

    for i in range(count):
        district = random.choice(district_names)
        base_lat, base_lon = DISTRICTS[district]

        capacity = random.randint(500, 5000)
        current_population = random.randint(
            0,
            max(0, int(capacity * 0.55))
        )

        safety = random.uniform(50, 98)
        infrastructure = random.uniform(40, 95)
        land = random.uniform(40, 95)
        accessibility = random.uniform(40, 95)
        water = random.uniform(40, 95)
        healthcare = random.uniform(30, 95)

        population_pressure = clamp(
            (current_population / capacity) * 100
        )

        suitability = (
            safety * 0.25
            + infrastructure * 0.15
            + land * 0.10
            + accessibility * 0.15
            + water * 0.15
            + healthcare * 0.10
            + (100 - population_pressure) * 0.10
        )

        site = RelocationSite(
            name=f"Relocation Site {i + 1}",
            district=district,
            latitude=base_lat + random.uniform(-0.15, 0.15),
            longitude=base_lon + random.uniform(-0.15, 0.15),
            capacity=capacity,
            current_population=current_population,
            suitability_score=round(clamp(suitability), 2),
            safety_score=round(safety, 2),
            infrastructure_score=round(infrastructure, 2),
            land_score=round(land, 2),
            accessibility_score=round(accessibility, 2),
            water_score=round(water, 2),
            healthcare_score=round(healthcare, 2),
            population_pressure_score=round(population_pressure, 2),
        )

        sites.append(site)

    return sites


def seed_database():
    create_tables()

    db = SessionLocal()

    try:
        # Prevent duplicate seed data
        db.query(RelocationAssignment).delete()
        db.query(HazardAssessment).delete()
        db.query(RelocationSite).delete()
        db.query(Village).delete()

        db.commit()

        # -------------------------------------------------
        # Villages
        # -------------------------------------------------

        villages = generate_villages(100)

        db.add_all(villages)
        db.commit()

        # Refresh IDs
        for village in villages:
            db.refresh(village)

        # -------------------------------------------------
        # Hazard assessments
        # -------------------------------------------------

        hazards = [
            generate_hazard(village)
            for village in villages
        ]

        db.add_all(hazards)

        # -------------------------------------------------
        # Relocation sites
        # -------------------------------------------------

        sites = generate_sites(20)

        db.add_all(sites)
        db.commit()

        for site in sites:
            db.refresh(site)

        # -------------------------------------------------
        # Relocation assignments
        # -------------------------------------------------

        assignment_count = 0

        # Assign higher-priority villages first
        priority_villages = sorted(
            villages,
            key=lambda v: v.priority_score or 0,
            reverse=True,
        )

        for village in priority_villages[:30]:

            suitable_sites = [
                site
                for site in sites
                if site.capacity - site.current_population
                >= village.population
            ]

            if not suitable_sites:
                continue

            site = max(
                suitable_sites,
                key=lambda s: s.suitability_score or 0
            )

            assignment = RelocationAssignment(
                village_id=village.id,
                site_id=site.id,
                persons=village.population,
                status="PLANNED",
            )

            db.add(assignment)

            site.current_population += village.population

            assignment_count += 1

        db.commit()

        # -------------------------------------------------
        # Summary
        # -------------------------------------------------

        print()
        print("=" * 50)
        print("RESQVISION DATABASE SEEDED")
        print("=" * 50)
        print(f"Villages:              {len(villages)}")
        print(f"Hazard assessments:    {len(hazards)}")
        print(f"Relocation sites:      {len(sites)}")
        print(f"Assignments:           {assignment_count}")
        print("=" * 50)

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


if __name__ == "__main__":
    seed_database()