"""
Data management router — /api/v1/data
Handles CSV/GeoJSON ingestion, validation, and synthetic data generation.
"""
from fastapi import APIRouter, Depends, UploadFile, File, HTTPException, status
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.config import get_settings

router = APIRouter(prefix="/data", tags=["Data Management"])


def _validate_extension(filename: str) -> str:
    """Return the extension if allowed, else raise 400."""
    settings = get_settings()
    ext = filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if ext not in settings.allowed_extensions:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"File type '.{ext}' not allowed. Allowed: {settings.allowed_extensions}",
        )
    return ext


@router.post("/upload/villages")
async def upload_village_data(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload village demographics and infrastructure CSV/GeoJSON."""
    _validate_extension(file.filename)
    settings = get_settings()
    content = await file.read()
    size_mb = len(content) / (1024 * 1024)
    if size_mb > settings.max_upload_size_mb:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail=f"File too large: {size_mb:.1f} MB (max {settings.max_upload_size_mb} MB)",
        )
    return {
        "success": True,
        "data": {
            "filename": file.filename,
            "size_mb": round(size_mb, 3),
            "rows_imported": 0,
            "errors": [],
        },
    }


@router.post("/upload/sites")
async def upload_site_data(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload candidate relocation site data."""
    _validate_extension(file.filename)
    content = await file.read()
    return {
        "success": True,
        "data": {"filename": file.filename, "rows_imported": 0, "errors": []},
    }


@router.post("/upload/hazards")
async def upload_hazard_data(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
):
    """Upload historical hazard event data."""
    _validate_extension(file.filename)
    content = await file.read()
    return {
        "success": True,
        "data": {"filename": file.filename, "rows_imported": 0, "errors": []},
    }


@router.post("/generate/synthetic")
def generate_synthetic_data(payload: dict, db: Session = Depends(get_db)):
    """
    Generate synthetic village/site data for development and testing.

    Payload:
        n_villages: int (default 100)
        n_sites: int (default 20)
        seed: int (default 42)
        save_to_db: bool (default False)
    """
    return {
        "success": True,
        "data": {
            "n_villages": payload.get("n_villages", 100),
            "n_sites": payload.get("n_sites", 20),
            "seed": payload.get("seed", 42),
            "saved_to_db": False,
            "message": "Synthetic data generation will be available in Phase 2",
        },
    }


@router.get("/status")
def get_data_status(db: Session = Depends(get_db)):
    """Return counts of records currently loaded in the database."""
    return {
        "success": True,
        "data": {
            "villages": 0,
            "sites": 0,
            "hazard_assessments": 0,
            "relocation_plans": 0,
            "last_updated": None,
        },
    }
