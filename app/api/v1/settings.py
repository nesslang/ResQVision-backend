"""
ResQVision 2.0 — Settings API

Provides:
    GET  /api/v1/settings/app
    GET  /api/v1/settings/thresholds
    GET  /api/v1/settings/weights

    GET  /api/v1/settings/preferences
    PUT  /api/v1/settings/preferences
    POST /api/v1/settings/preferences/reset

User preferences are persisted locally in:
    data/settings_preferences.json
"""

from pathlib import Path
from typing import Any

from fastapi import APIRouter
from pydantic import BaseModel, Field

from app.core.config import get_settings


# ============================================================
# ROUTER
# ============================================================

router = APIRouter(
    prefix="/settings",
    tags=["Settings"],
)


# ============================================================
# PERSISTENCE
# ============================================================

BASE_DIR = Path(__file__).resolve().parents[3]

DATA_DIR = BASE_DIR / "data"

PREFERENCES_FILE = DATA_DIR / "settings_preferences.json"


# ============================================================
# DEFAULT PREFERENCES
# ============================================================

DEFAULT_PREFERENCES = {
    "notifications": True,
    "critical_alerts": True,
    "auto_refresh": True,
    "refresh_interval": 30,
    "map_mode": "Risk Zones",
}


# ============================================================
# PYDANTIC MODEL
# ============================================================

class SettingsPreferences(BaseModel):
    """
    Frontend dashboard preferences.

    These values are intentionally separate from the application's
    environment/configuration settings in app/core/config.py.
    """

    notifications: bool = True

    critical_alerts: bool = True

    auto_refresh: bool = True

    refresh_interval: int = Field(
        default=30,
        ge=15,
        le=3600,
    )

    map_mode: str = "Risk Zones"


# ============================================================
# FILE HELPERS
# ============================================================

def ensure_data_directory() -> None:
    """
    Make sure the backend data directory exists.
    """
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


def read_preferences() -> dict[str, Any]:
    """
    Read persisted preferences.

    If the file doesn't exist or contains invalid JSON,
    default preferences are returned.
    """

    ensure_data_directory()

    if not PREFERENCES_FILE.exists():
        return DEFAULT_PREFERENCES.copy()

    try:
        import json

        with PREFERENCES_FILE.open(
            "r",
            encoding="utf-8",
        ) as file:
            data = json.load(file)

        if not isinstance(data, dict):
            return DEFAULT_PREFERENCES.copy()

        preferences = DEFAULT_PREFERENCES.copy()

        preferences.update(data)

        return preferences

    except (
        OSError,
        ValueError,
        TypeError,
    ):
        return DEFAULT_PREFERENCES.copy()


def write_preferences(
    preferences: dict[str, Any],
) -> None:
    """
    Persist preferences to JSON.
    """

    import json

    ensure_data_directory()

    temporary_file = PREFERENCES_FILE.with_suffix(
        ".tmp"
    )

    with temporary_file.open(
        "w",
        encoding="utf-8",
    ) as file:
        json.dump(
            preferences,
            file,
            indent=2,
        )

    temporary_file.replace(
        PREFERENCES_FILE
    )


# ============================================================
# APP SETTINGS
# ============================================================

@router.get("/app")
def get_app_settings():
    """
    Return application/runtime configuration.
    """

    settings = get_settings()

    return {
        "success": True,
        "data": {
            "app_name": settings.app_name,
            "debug": settings.debug,
            "model_dir": settings.model_dir,
            "model_cache_ttl": settings.model_cache_ttl,
            "max_upload_size_mb": (
                settings.max_upload_size_mb
            ),
            "allowed_extensions": (
                settings.allowed_extensions
            ),
            "optimization": {
                "max_iterations": (
                    settings.opt_max_iterations
                ),
                "time_limit_seconds": (
                    settings.opt_time_limit_seconds
                ),
            },
        },
    }


# ============================================================
# HAZARD / PRIORITY / PRESSURE THRESHOLDS
# ============================================================

@router.get("/thresholds")
def get_thresholds():
    """
    Return hazard, priority, pressure and capacity thresholds.
    """

    settings = get_settings()

    return {
        "success": True,
        "data": {
            "hazard": {
                "safe_max": (
                    settings.hazard_safe_max
                ),
                "warning_max": (
                    settings.hazard_warning_max
                ),
                "red_min": (
                    settings.hazard_red_min
                ),
            },
            "priority": {
                "immediate_min": (
                    settings.priority_immediate_min
                ),
                "short_term_min": (
                    settings.priority_short_term_min
                ),
            },
            "pressure": {
                "low_max": (
                    settings.pressure_low_max
                ),
                "moderate_max": (
                    settings.pressure_moderate_max
                ),
                "high_max": (
                    settings.pressure_high_max
                ),
                "critical_max": (
                    settings.pressure_critical_max
                ),
            },
            "capacity": {
                "safety_margin": (
                    settings.capacity_safety_margin
                ),
            },
        },
    }


# ============================================================
# WEIGHTS
# ============================================================

@router.get("/weights")
def get_weights():
    """
    Return site suitability and relocation priority weights.
    """

    settings = get_settings()

    return {
        "success": True,
        "data": {
            "suitability": (
                settings.suitability_weights
            ),
            "priority": (
                settings.priority_weights
            ),
        },
    }


# ============================================================
# FRONTEND PREFERENCES — GET
# ============================================================

@router.get("/preferences")
def get_preferences():
    """
    Return persisted frontend/dashboard preferences.
    """

    preferences = read_preferences()

    # Validate persisted data through Pydantic.
    validated = SettingsPreferences(
        **preferences
    )

    return {
        "success": True,
        "data": validated.model_dump(),
    }


# ============================================================
# FRONTEND PREFERENCES — PUT
# ============================================================

@router.put("/preferences")
def update_preferences(
    preferences: SettingsPreferences,
):
    """
    Save frontend/dashboard preferences.

    The request body is validated by Pydantic before
    this function receives it.
    """

    validated = SettingsPreferences(
        **preferences.model_dump()
    )

    data = validated.model_dump()

    write_preferences(data)

    return {
        "success": True,
        "message": "Settings saved successfully.",
        "data": data,
    }


# ============================================================
# FRONTEND PREFERENCES — RESET
# ============================================================

@router.post("/preferences/reset")
def reset_preferences():
    """
    Reset frontend/dashboard preferences to defaults.
    """

    preferences = SettingsPreferences(
        **DEFAULT_PREFERENCES
    )

    data = preferences.model_dump()

    write_preferences(data)

    return {
        "success": True,
        "message": "Settings reset to defaults.",
        "data": data,
    }