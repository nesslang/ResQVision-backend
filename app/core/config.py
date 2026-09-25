from functools import lru_cache
from typing import List
from pydantic_settings import BaseSettings
from pydantic import field_validator
import json


class Settings(BaseSettings):
    # App
    app_name: str = "ResQVision 2.0"
    debug: bool = False
    cors_origins: List[str] = ["http://localhost:3000", "http://localhost:5173", "http://localhost:8080"]

    # Database
    database_url: str = "postgresql://resqvision:resqvision@localhost:5432/resqvision"
    dev_database_url: str = "sqlite:///./resqvision_dev.db"
    use_dev_db: bool = False

    # Security
    secret_key: str = "dev-secret-key-change-in-production-minimum-32-chars"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 1440

    # ML
    model_dir: str = "app/ml/models"
    model_cache_ttl: int = 3600

    # Hazard thresholds
    hazard_safe_max: float = 39.0
    hazard_warning_max: float = 69.0
    hazard_red_min: float = 70.0

    # Priority thresholds
    priority_immediate_min: float = 80.0
    priority_short_term_min: float = 60.0

    # Site suitability weights
    weight_safety: float = 0.35
    weight_infrastructure: float = 0.25
    weight_land: float = 0.15
    weight_accessibility: float = 0.10
    weight_water: float = 0.05
    weight_healthcare: float = 0.05
    weight_population_pressure: float = 0.05

    # Priority score weights
    weight_hazard_risk: float = 0.40
    weight_vulnerability: float = 0.35
    weight_accessibility_risk: float = 0.15
    weight_housing: float = 0.10

    # Capacity
    capacity_safety_margin: float = 0.85

    # Pressure thresholds
    pressure_low_max: float = 50.0
    pressure_moderate_max: float = 75.0
    pressure_high_max: float = 90.0
    pressure_critical_max: float = 100.0

    # Optimization
    opt_max_iterations: int = 50
    opt_time_limit_seconds: int = 30

    # File upload
    max_upload_size_mb: int = 100
    allowed_extensions: List[str] = ["csv", "json", "geojson", "xlsx"]

    # Logging
    log_level: str = "INFO"
    log_format: str = "json"

    @field_validator("cors_origins", mode="before")
    @classmethod
    def parse_cors_origins(cls, v):
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
            # comma-separated fallback
            return [origin.strip() for origin in v.split(",") if origin.strip()]
        return v

    @field_validator("allowed_extensions", mode="before")
    @classmethod
    def parse_allowed_extensions(cls, v):
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list):
                    return parsed
            except json.JSONDecodeError:
                pass
            return [ext.strip() for ext in v.split(",") if ext.strip()]
        return v

    @property
    def active_database_url(self) -> str:
        return self.dev_database_url if self.use_dev_db else self.database_url

    def classify_hazard(self, score: float) -> str:
        """Classify a 0-100 hazard score into a zone label."""
        if score <= self.hazard_safe_max:
            return "SAFE"
        elif score <= self.hazard_warning_max:
            return "WARNING"
        return "RED"

    def classify_priority(self, score: float) -> str:
        """Classify a 0-100 priority score into a relocation urgency label."""
        if score >= self.priority_immediate_min:
            return "IMMEDIATE"
        elif score >= self.priority_short_term_min:
            return "SHORT_TERM"
        return "MEDIUM_TERM"

    def classify_pressure(self, pct: float) -> str:
        """Classify infrastructure utilisation percentage into a pressure label."""
        if pct <= self.pressure_low_max:
            return "LOW"
        elif pct <= self.pressure_moderate_max:
            return "MODERATE"
        elif pct <= self.pressure_high_max:
            return "HIGH"
        elif pct <= self.pressure_critical_max:
            return "CRITICAL"
        return "OVERCAPACITY"

    @property
    def suitability_weights(self) -> dict:
        """Return site-suitability weight dict for use in scoring functions."""
        return {
            "safety": self.weight_safety,
            "infrastructure": self.weight_infrastructure,
            "land": self.weight_land,
            "accessibility": self.weight_accessibility,
            "water": self.weight_water,
            "healthcare": self.weight_healthcare,
            "population_pressure": self.weight_population_pressure,
        }

    @property
    def priority_weights(self) -> dict:
        """Return priority-score weight dict for use in ranking functions."""
        return {
            "hazard_risk": self.weight_hazard_risk,
            "vulnerability": self.weight_vulnerability,
            "accessibility_risk": self.weight_accessibility_risk,
            "housing": self.weight_housing,
        }

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """Return cached application settings (reads .env once)."""
    return Settings()
