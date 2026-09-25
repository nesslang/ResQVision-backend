from datetime import datetime

from sqlalchemy import Column, Integer, Float, String, DateTime, ForeignKey, Text
from sqlalchemy.orm import relationship

from app.core.database import Base


class Village(Base):
    __tablename__ = "villages"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    district = Column(String(100), nullable=False)

    population = Column(Integer, default=0)
    elderly = Column(Integer, default=0)
    children = Column(Integer, default=0)
    disabled = Column(Integer, default=0)

    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)

    hazard_score = Column(Float, default=0.0)
    hazard_zone = Column(String(20), default="SAFE")

    vulnerability_score = Column(Float, default=0.0)
    priority_score = Column(Float, default=0.0)
    priority_category = Column(String(30), default="MEDIUM_TERM")

    created_at = Column(DateTime, default=datetime.utcnow)

    hazards = relationship(
        "HazardAssessment",
        back_populates="village",
        cascade="all, delete-orphan",
    )


class HazardAssessment(Base):
    __tablename__ = "hazard_assessments"

    id = Column(Integer, primary_key=True, index=True)
    village_id = Column(Integer, ForeignKey("villages.id"), nullable=False)

    hazard_score = Column(Float, default=0.0)
    zone = Column(String(20), default="SAFE")

    flood_risk = Column(Float, default=0.0)
    landslide_risk = Column(Float, default=0.0)
    earthquake_risk = Column(Float, default=0.0)
    drought_risk = Column(Float, default=0.0)
    cyclone_risk = Column(Float, default=0.0)

    rainfall = Column(Float, default=0.0)
    elevation = Column(Float, default=0.0)
    slope = Column(Float, default=0.0)
    distance_from_river = Column(Float, default=0.0)

    created_at = Column(DateTime, default=datetime.utcnow)

    village = relationship("Village", back_populates="hazards")


class RelocationSite(Base):
    __tablename__ = "relocation_sites"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(150), nullable=False)
    district = Column(String(100), nullable=False)

    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)

    capacity = Column(Integer, default=0)
    current_population = Column(Integer, default=0)

    suitability_score = Column(Float, default=0.0)

    safety_score = Column(Float, default=0.0)
    infrastructure_score = Column(Float, default=0.0)
    land_score = Column(Float, default=0.0)
    accessibility_score = Column(Float, default=0.0)
    water_score = Column(Float, default=0.0)
    healthcare_score = Column(Float, default=0.0)
    population_pressure_score = Column(Float, default=0.0)

    created_at = Column(DateTime, default=datetime.utcnow)


class RelocationAssignment(Base):
    __tablename__ = "relocation_assignments"

    id = Column(Integer, primary_key=True, index=True)

    village_id = Column(Integer, ForeignKey("villages.id"), nullable=False)
    site_id = Column(Integer, ForeignKey("relocation_sites.id"), nullable=False)

    persons = Column(Integer, default=0)
    status = Column(String(30), default="PLANNED")

    created_at = Column(DateTime, default=datetime.utcnow)